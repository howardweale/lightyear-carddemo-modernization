from __future__ import annotations

import copy
from contextlib import redirect_stdout
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_sql_recovery import (
    SNAPSHOT_SQL, SqlRecovery, epoch, invoke, normalize_snapshot, recovery_point_age, select_recovery_point,
    source_profile, verified, write_signed,
)
from lightyear_data.contracts import sign, verify_signature


def instance(name="source", address="10.20.0.2"):
    return {"name": name, "project": "test-project", "region": "us-west1", "state": "RUNNABLE",
        "databaseVersion": "POSTGRES_16", "createTime": "2026-09-06T01:00:01Z",
        "ipAddresses": [{"type": "PRIVATE", "ipAddress": address}],
        "settings": {"ipConfiguration": {"ipv4Enabled": False, "privateNetwork": "projects/test-project/global/networks/test"},
                     "backupConfiguration": {"enabled": True, "pointInTimeRecoveryEnabled": True}}}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = GkeRuntime(project="test-project", region="us-west1", cluster="test-cluster",
            namespace="test-ns", images={s: "private/" + s + "@sha256:" + "a" * 64 for s in SERVICES},
            run_id="test-run", output=self.root, signing_key="test-key", signer="test-operator",
            probe_image="private/probe@sha256:" + "b" * 64)
        self.drill = SqlRecovery(self.runtime, "source", "test-key", "test-operator")

    def test_profile_rejects_public_and_wrong_instance(self):
        for field, value in (("name", "other"), ("project", "prod"), ("state", "PENDING_CREATE"),
                             ("databaseVersion", "POSTGRES_15")):
            row = instance()
            row[field] = value
            with self.subTest(field=field), self.assertRaises(JourneyFailure):
                source_profile(row, "test-project", "us-west1", "source")
        row = instance()
        row["settings"]["ipConfiguration"]["ipv4Enabled"] = True
        with self.assertRaisesRegex(JourneyFailure, "private-only"):
            source_profile(row, "test-project", "us-west1", "source")

    def test_target_does_not_need_its_own_backup_schedule(self):
        row = instance()
        row["settings"].pop("backupConfiguration")
        with self.assertRaisesRegex(JourneyFailure, "pitr-required"):
            source_profile(row, "test-project", "us-west1", "source")
        self.assertEqual(source_profile(row, "test-project", "us-west1", "source", require_backups=False)["name"], "source")

    def test_signed_checkpoint_rejects_corrupt_content_even_with_signature(self):
        value = sign({"state": "ready"}, "test-key", "test-operator")
        verified(value, "test-key")
        value["state"] = "mutated"
        with self.assertRaises(JourneyFailure):
            verified(value, "test-key")
        write_signed(self.root / "state.json", {"state": "ready"}, "test-key", "test-operator")
        self.assertTrue(verify_signature(json.loads((self.root / "state.json").read_text()), "test-key"))

    def test_source_cannot_be_restore_target(self):
        state = copy.deepcopy(self.drill.state)
        state["target"] = "source"
        with self.assertRaisesRegex(JourneyFailure, "isolated-target"):
            SqlRecovery(self.runtime, "source", "test-key", "test-operator", state=state)

    def test_uncertain_clone_never_triggers_blind_delete(self):
        self.drill.state["operations"]["pitr"] = {"name": None}
        self.drill.remove_resources = Mock()
        self.drill.cloud = Mock()
        with self.assertRaisesRegex(JourneyFailure, "submission-uncertain"):
            self.drill.cleanup()
        self.drill.cloud.assert_not_called()

    def test_target_recreation_blocks_delete(self):
        self.drill.state["target_create_time"] = "2026-09-06T01:00:01Z"
        replacement = instance(self.drill.state["target"])
        replacement["createTime"] = "2026-09-06T02:00:00Z"
        self.drill.instance = Mock(return_value=replacement)
        with self.assertRaisesRegex(JourneyFailure, "identity-drift"):
            self.drill.target_guard()

    def test_claim_requires_correct_creation_operation_and_time(self):
        self.drill.state["operations"]["pitr"] = {"name": "operation", "requested_at": "2026-09-06T01:00:00Z"}
        self.drill.wait_operation = Mock(return_value={"operationType": "CLONE", "endTime": "2026-09-06T01:05:00Z"})
        self.drill.instance = Mock(return_value=instance(self.drill.state["target"]))
        self.drill.claim_target()
        self.drill.instance.return_value["createTime"] = "2026-09-06T01:06:00Z"
        with self.assertRaisesRegex(JourneyFailure, "ownership-not-proven"):
            self.drill.claim_target()

    def test_operation_errors_and_wrong_project_fail(self):
        for response in ({"targetId": "target", "targetProject": "other", "status": "DONE"},
                         {"targetId": "target", "targetProject": "test-project", "status": "DONE", "error": {"errors": []}}):
            self.drill.cloud = Mock(return_value=response)
            with self.assertRaises(JourneyFailure):
                self.drill.wait_operation("operation", "target")

    def test_operation_intent_saved_before_submission_and_not_retried(self):
        def fail(*args):
            state = json.loads((self.root / "sql-recovery-state.json").read_text())
            self.assertIsNone(state["operations"]["pitr"]["name"])
            self.assertTrue(verify_signature(state, "test-key"))
            raise JourneyFailure("network-timeout")
        self.drill.cloud = Mock(side_effect=fail)
        with self.assertRaisesRegex(JourneyFailure, "network-timeout"):
            self.drill.operation("pitr", self.drill.state["target"], "instances", "clone")
        with self.assertRaisesRegex(JourneyFailure, "already-exists"):
            self.drill.operation("pitr", self.drill.state["target"], "instances", "clone")
        self.assertEqual(self.drill.cloud.call_count, 1)

    def test_error_redaction_preserves_only_bounded_reason(self):
        fake = subprocess.CompletedProcess([], 1, "secret-body", "PERMISSION_DENIED password=super-secret\nprivate-sql-row")
        with patch("lightyear_data.cloudbank_sql_recovery.subprocess.run", return_value=fake):
            with self.assertRaisesRegex(JourneyFailure, "permission-denied") as exc:
                invoke(["gcloud", "sql", "instances", "list"])
            self.assertNotIn("super-secret", str(exc.exception))
            with self.assertRaisesRegex(JourneyFailure, "database-or-secret-access"):
                invoke(["psql"], sensitive=True)

    def test_probe_cleanup_refuses_foreign_uid(self):
        self.drill.state["resources"] = [{"kind": "pod", "name": "probe", "uid": "owned"}]
        self.runtime.kubectl = Mock(return_value=json.dumps({"metadata": {"uid": "foreign", "labels": {"lightyear.run": "test-run"}}}))
        with self.assertRaisesRegex(JourneyFailure, "identity-drift"):
            self.drill.remove_resources()
        self.assertFalse(any("delete" in call.args for call in self.runtime.kubectl.call_args_list))

    def probe_cluster(self):
        """Stateful API double; replacement enforces the observed UID and version."""
        self.drill.databases = {"application": "cloudbank-customer-external"}
        objects, created = {}, []
        def kubectl(*args, data=None, **kwargs):
            if args[0] == "create":
                manifest = json.loads(data)
                created.append(copy.deepcopy(manifest))
                key = (manifest["kind"].lower(), manifest["metadata"]["name"])
                self.assertNotIn(key, objects)
                manifest["metadata"].update(uid="uid-" + str(len(created)), resourceVersion="1")
                if manifest["kind"] == "Pod":
                    manifest["status"] = {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}
                objects[key] = manifest
                return json.dumps(manifest)
            if args[0] == "wait":
                return "ready"
            if args[0] == "replace":
                manifest = json.loads(data)
                key = (manifest["kind"].lower(), manifest["metadata"]["name"])
                for field in ("uid", "resourceVersion"):
                    self.assertEqual(manifest["metadata"][field], objects[key]["metadata"][field])
                manifest["metadata"]["resourceVersion"] = str(int(manifest["metadata"]["resourceVersion"]) + 1)
                objects[key] = manifest
                return json.dumps(manifest)
            if args[0] == "get":
                row = objects.get((args[1], args[2]))
                return json.dumps(row) if row else ""
            if args[0] == "delete":
                del objects[(args[1], args[2])]
                return "deleted"
            self.fail("unexpected API action: " + args[0])
        self.runtime.kubectl = Mock(side_effect=kubectl)
        self.runtime.get = Mock(side_effect=lambda kind, name: copy.deepcopy(objects[(kind, name)]))
        raw = "\n".join(map(json.dumps, [{"unsupported": 0},
            {"relation": "public.accounts", "rows": 3, "sha256": "a" * 64}, {"schema_sha256": "b" * 64}]))
        return objects, created, raw

    def test_snapshots_reuse_prepared_clients_with_exact_host_binding_and_final_cleanup(self):
        objects, created, raw = self.probe_cluster()
        with patch("lightyear_data.cloudbank_sql_recovery.invoke", return_value=raw) as query:
            outputs = [self.drill.snapshot(host) for host in ("10.20.0.2", "10.20.0.2", "10.20.0.2", "10.20.0.3", "10.20.0.3")]
        self.assertTrue(all(output == outputs[0] for output in outputs))
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0]["spec"]["egress"], [])
        pod = created[1]["spec"]
        self.assertEqual(pod["terminationGracePeriodSeconds"], 1)
        self.assertEqual(pod["securityContext"]["runAsUser"], 70)
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertTrue(pod["containers"][0]["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(pod["containers"][0]["image"], self.runtime.probe_image)
        self.assertEqual(pod["activeDeadlineSeconds"], 7200)
        self.assertEqual([a for call in query.call_args_list for a in call.args[0] if a.startswith("PGHOST=")],
                         ["PGHOST=10.20.0.2"] * 3 + ["PGHOST=10.20.0.3"] * 2)
        for call in query.call_args_list:
            self.assertEqual(call.kwargs["data"], SNAPSHOT_SQL)
            self.assertTrue(call.kwargs["sensitive"])
            self.assertNotIn("PGPASSWORD=", str(call.args))
        replacements = [c for c in self.runtime.kubectl.call_args_list if c.args[0] == "replace"]
        self.assertEqual(len(replacements), 2)
        self.assertEqual(json.loads(replacements[-1].kwargs["data"])["spec"], self.drill.probe_policy_spec("10.20.0.3"))
        self.assertEqual(len(self.drill.state["resources"]), 2)
        saved = json.loads((self.root / "sql-recovery-state.json").read_text())
        resumed = SqlRecovery(self.runtime, "source", "test-key", "test-operator", state=verified(saved, "test-key"))
        resumed.cleanup()
        self.assertEqual(objects, {})
        self.assertEqual(resumed.state["resources"], [])

    def test_reused_probe_and_policy_drift_fail_before_database_access(self):
        for fault in ("pod-uid", "pod-image", "pod-env", "pod-not-ready", "policy-uid", "policy-egress"):
            with self.subTest(fault=fault):
                self.drill = SqlRecovery(self.runtime, "source", "test-key", "test-operator")
                objects, _, raw = self.probe_cluster()
                with patch("lightyear_data.cloudbank_sql_recovery.invoke", return_value=raw) as query:
                    self.drill.snapshot("10.20.0.2")
                    pod = next(v for k, v in objects.items() if k[0] == "pod")
                    policy = next(v for k, v in objects.items() if k[0] == "networkpolicy")
                    if fault == "pod-uid":
                        pod["metadata"]["uid"] = "replacement"
                    elif fault == "pod-image":
                        pod["spec"]["containers"][0]["image"] = "foreign/image"
                    elif fault == "pod-env":
                        pod["spec"]["containers"][0]["env"] = []
                    elif fault == "pod-not-ready":
                        pod["status"]["phase"] = "Failed"
                    elif fault == "policy-uid":
                        policy["metadata"]["uid"] = "replacement"
                    else:
                        policy["spec"]["egress"] = [{}]
                    query.reset_mock()
                    with self.assertRaises(JourneyFailure):
                        self.drill.snapshot("10.20.0.3")
                    query.assert_not_called()

    def test_read_only_policy_convergence_retries_are_bounded_and_validate_result(self):
        _, _, raw = self.probe_cluster()
        failure = JourneyFailure("operator-command-failed-database-or-secret-access")
        with patch("lightyear_data.cloudbank_sql_recovery.invoke", side_effect=[failure, raw]) as query, \
             patch("lightyear_data.cloudbank_sql_recovery.time.sleep") as pause:
            self.assertEqual(self.drill.snapshot("10.20.0.2")["databases"].popitem()[1]["row_count"], 3)
            self.assertEqual(query.call_count, 2)
            pause.assert_called_once_with(1)
        with patch("lightyear_data.cloudbank_sql_recovery.invoke", side_effect=failure) as query, \
             patch("lightyear_data.cloudbank_sql_recovery.time.sleep"):
            with self.assertRaises(JourneyFailure):
                self.drill.snapshot("10.20.0.3")
            self.assertEqual(query.call_count, 3)
        with patch("lightyear_data.cloudbank_sql_recovery.invoke", return_value="private-unexpected-data") as query:
            with self.assertRaises(ValueError):
                self.drill.snapshot("10.20.0.3")
            self.assertEqual(query.call_count, 1)

    def test_partial_pool_creation_is_journaled_for_cleanup(self):
        objects, _, _ = self.probe_cluster()
        original = self.runtime.kubectl.side_effect
        def fail_pod(*args, **kwargs):
            if args[0] == "create" and json.loads(kwargs["data"])["kind"] == "Pod":
                raise JourneyFailure("operator-command-failed")
            return original(*args, **kwargs)
        self.runtime.kubectl.side_effect = fail_pod
        with self.assertRaises(JourneyFailure):
            self.drill.snapshot("10.20.0.2")
        self.assertEqual(len(self.drill.state["resources"]), 2)
        self.assertIsNone(self.drill.state["resources"][-1]["uid"])
        self.drill.cleanup()
        self.assertEqual(objects, {})

    def test_snapshot_fails_closed_and_changes_digest(self):
        rows = [{"unsupported": 0}, {"relation": "public.accounts", "rows": 3, "sha256": "a" * 64}, {"schema_sha256": "b" * 64}]
        raw = lambda: "\n".join(map(json.dumps, rows))
        first = normalize_snapshot(raw())
        rows[1]["sha256"] = "c" * 64
        self.assertNotEqual(first["state_sha256"], normalize_snapshot(raw())["state_sha256"])
        rows[0]["unsupported"] = 1
        with self.assertRaises(JourneyFailure):
            normalize_snapshot(raw())

    def test_rpo_rejects_stale_future_and_pre_checkpoint_times(self):
        incident = "2026-09-06T01:05:00Z"
        self.assertEqual(recovery_point_age(incident, "2026-09-06T01:04:00Z", "2026-09-06T01:03:00Z"), 60)
        for point, checkpoint in (("2026-09-06T01:03:59Z", "2026-09-06T01:03:00Z"),
                                  ("2026-09-06T01:05:01Z", "2026-09-06T01:03:00Z"),
                                  ("2026-09-06T01:04:59Z", "2026-09-06T01:05:00Z")):
            with self.subTest(point=point), self.assertRaises(JourneyFailure):
                recovery_point_age(incident, point, checkpoint)

    def engine(self, *, mismatch=False, pitr_rto=30, backup_rto=30, interrupted=False, cleanup_failure=False,
               restore_wait_failure=False):
        seconds = [0]
        baseline = {"state_sha256": "a" * 64, "databases": {"b" * 64: {"table_count": 3}}}
        self.drill.discover = Mock(return_value=source_profile(instance(), "test-project", "us-west1", "source"))
        self.drill.state["coverage"] = {"database_count": 1}
        self.runtime.ready = Mock()
        self.drill.quiesce = Mock()
        self.drill.source_guard = Mock()
        restored = {**baseline, "state_sha256": "d" * 64} if mismatch else baseline
        snapshots = iter(enumerate([baseline, baseline, baseline, restored, baseline]))
        def snapshot(*args):
            index, value = next(snapshots)
            seconds[0] += pitr_rto if index == 3 else backup_rto if index == 4 else 0
            return value
        self.drill.snapshot = Mock(side_effect=snapshot)
        self.drill.operation = Mock(return_value="operation")
        if interrupted:
            self.drill.operation.side_effect = KeyboardInterrupt()
        self.drill.wait_operation = Mock()
        if restore_wait_failure:
            self.drill.wait_operation.side_effect = [None, JourneyFailure("operator-command-failed-exit-1")]
        backup = {"id": "123", "instance": "source", "description": "test-run", "type": "ON_DEMAND", "status": "SUCCESSFUL",
                  "startTime": "2026-09-06T01:01:00Z", "endTime": "2026-09-06T01:02:00Z"}
        def cloud(*args):
            if args[:2] == ("backups", "list"):
                seconds[0] = 60
                return [backup]
            self.assertEqual(args[:2], ("instances", "get-latest-recovery-time"))
            seconds[0] = 270
            return {"latestRecoveryTime": "2026-09-06T01:04:50Z"}
        self.drill.cloud = Mock(side_effect=cloud)
        self.drill.claim_target = Mock(return_value=instance(self.drill.state["target"], "10.20.0.3"))
        self.drill.target_guard = Mock(return_value=instance(self.drill.state["target"], "10.20.0.3"))
        self.drill.restore_apps = Mock()
        self.drill.cleanup = Mock(side_effect=JourneyFailure("cleanup-failed") if cleanup_failure else None)
        self.timeline = Mock()
        for name in ("snapshot", "cloud", "source_guard", "operation"):
            self.timeline.attach_mock(getattr(self.drill, name), name)
        def now():
            return datetime.fromtimestamp(epoch("2026-09-06T01:00:30Z") + seconds[0], timezone.utc).isoformat().replace("+00:00", "Z")
        with patch("lightyear_data.cloudbank_sql_recovery.utc", side_effect=now), \
             patch("lightyear_data.cloudbank_sql_recovery.time.monotonic", side_effect=lambda: seconds[0]):
            return self.drill.execute()

    def test_restore_poll_failure_preserves_pitr_and_identifies_stage(self):
        result = self.engine(restore_wait_failure=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_stage"], "backup-restore-completion")
        self.assertEqual(result["reason"], "operator-command-failed-exit-1")
        self.assertTrue(result["pitr"]["state_matches"])
        self.assertNotIn("backup_restore", result)
        row = next(r for r in result["phases"] if r["phase"] == "backup-restore-completion")
        self.assertEqual(row["status"], "failed")
        self.drill.cleanup.assert_called_once()

    def test_phase_duration_and_running_checkpoint_are_signed(self):
        result = self.engine()
        validation = next(r for r in result["phases"] if r["phase"] == "pitr-validation")
        self.assertEqual(validation["elapsed_seconds"], 30)
        self.assertEqual(validation["status"], "completed")
        self.drill.observation = {}
        with self.drill.phase("test-phase"):
            saved = verified(json.loads((self.root / "database-recovery.json").read_text()), "test-key")
            self.assertEqual(saved["phases"][-1]["status"], "running")
            self.assertNotIn("finished_at", saved)

    def test_unexpected_exception_and_operation_payloads_are_not_persisted(self):
        self.drill.observation = {}
        with self.assertRaises(ValueError), self.drill.phase("test-phase"):
            raise ValueError("private-row-and-password")
        saved = (self.root / "database-recovery.json").read_text()
        self.assertNotIn("private-row-and-password", saved)
        self.assertEqual(json.loads(saved)["failure_stage"], "test-phase")
        self.drill.state["operations"]["pitr"] = {"name": "operation"}
        self.drill.cloud = Mock(return_value={"targetId": "target", "targetProject": "test-project",
            "status": "DONE", "operationType": "CLONE", "endTime": "2026-09-06T01:05:00Z",
            "error": {"message": "private-server-error"}})
        with self.assertRaises(JourneyFailure):
            self.drill.wait_operation("operation", "target")
        saved = verified(json.loads((self.root / "sql-recovery-state.json").read_text()), "test-key")
        self.assertTrue(saved["operations"]["pitr"]["observation"]["has_error"])
        self.assertNotIn("private-server-error", json.dumps(saved))

    def test_drill_passes_only_isolated_scope(self):
        result = self.engine()
        self.assertEqual(result["status"], "passed-isolated-database-recovery")
        self.assertEqual(result["pitr"]["recovery_point_age_seconds"], 10)
        self.assertEqual(result["pitr"]["database_rto_seconds"], 30)
        self.assertIsNone(result["backup"]["managed_backup_bytes_sha256"])
        self.assertFalse(result["ms67_complete"])
        self.assertTrue(verify_signature(json.loads((self.root / "database-recovery.json").read_text()), "test-key"))

    def test_snapshot_precedes_single_timestamp_query_and_clone_rechecks_source_identity(self):
        result = self.engine()
        events = self.timeline.mock_calls
        queries = [i for i, event in enumerate(events) if event[0] == "cloud" and event.args[:2] == ("instances", "get-latest-recovery-time")]
        self.assertEqual(len(queries), 1)
        query_index = queries[0]
        clone_index = next(i for i, event in enumerate(events) if event[0] == "operation" and event.args[0] == "pitr")
        self.assertEqual(sum(event[0] == "snapshot" for event in events[:query_index]), 3)
        self.assertEqual(events[query_index - 1][0], "snapshot")
        self.assertEqual(events[query_index + 1][0], "source_guard")
        self.assertEqual(clone_index, query_index + 2)
        self.assertEqual(events[clone_index].args[-1], result["pitr"]["point_in_time"])
        diagnostic = result["pitr_preflight"]["recent_observations"][-1]
        self.assertEqual(diagnostic["latest_recovery_time"], result["pitr"]["point_in_time"])
        self.assertEqual(diagnostic["observed_at"], result["pitr"]["incident_declared_at"])
        self.assertEqual(diagnostic["recovery_point_age_seconds"], 10)

    def test_failed_window_retains_bounded_diagnostics_and_restores_without_clone(self):
        def fail_window(checkpoint, query, observe):
            for attempt in range(1, 8):
                observe({"attempt": attempt, "status": "timed-out" if attempt == 7 else "waiting",
                         "reason": "point-too-old", "recovery_point_age_seconds": 61 + attempt})
            raise JourneyFailure("pitr-recovery-window-timeout")
        with patch("lightyear_data.cloudbank_sql_recovery.select_recovery_point", side_effect=fail_window):
            result = self.engine()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["pitr_preflight"]["attempt_count"], 7)
        self.assertEqual([o["attempt"] for o in result["pitr_preflight"]["recent_observations"]], [3, 4, 5, 6, 7])
        self.assertEqual(result["recovery"]["validation_instance_state"], "not-requested")
        self.assertFalse(any(call.args[0] == "pitr" for call in self.drill.operation.call_args_list))
        self.drill.restore_apps.assert_called_once()
        saved = json.loads((self.root / "database-recovery.json").read_text())
        self.assertTrue(verify_signature(saved, "test-key"))
        self.assertEqual(saved["pitr_preflight"], result["pitr_preflight"])

    def test_changed_state_or_rto_overrun_or_cleanup_failure_cannot_pass(self):
        for fault in ({"mismatch": True}, {"pitr_rto": 601}, {"pitr_rto": 643}, {"backup_rto": 601}, {"cleanup_failure": True}):
            with self.subTest(fault=fault):
                result = self.engine(**fault)
                self.assertEqual(result["status"], "failed")
                self.drill.restore_apps.assert_called()
                self.drill.cleanup.assert_called_once()

    def test_restoration_failure_keeps_specific_bounded_error(self):
        self.drill.observation = {}
        self.runtime.close = Mock(return_value={"status": "failed", "errors": ["probe-cleanup-failed"], "remaining_stopped_services": []})
        self.runtime.ready = Mock()
        with self.assertRaisesRegex(JourneyFailure, "application-restoration-failed"), self.drill.phase("cleanup-application-restoration"):
            self.drill.restore_apps()
        saved = verified(json.loads((self.root / "database-recovery.json").read_text()), "test-key")
        self.assertEqual(saved["application_restoration_checks"][-1]["errors"], ["probe-cleanup-failed"])
        self.runtime.ready.assert_not_called()

    def test_sql_restoration_records_grouped_timings_and_still_requires_http_readiness(self):
        self.drill.observation = {}
        recovery = {"status": "restored", "errors": [], "remaining_stopped_services": [],
            "application_restoration": {"services": {"account": {"status": "ready", "elapsed_seconds": 80}}}}
        self.runtime.close = Mock(return_value=recovery)
        self.runtime.ready = Mock(side_effect=JourneyFailure("http-readiness-failed"))
        with self.assertRaisesRegex(JourneyFailure, "http-readiness-failed"), self.drill.phase("application-restoration-after-clone-submit"):
            self.drill.restore_apps()
        self.runtime.close.assert_called_once_with(grouped_restoration=True)
        self.runtime.ready.assert_called_once()
        saved = verified(json.loads((self.root / "database-recovery.json").read_text()), "test-key")
        self.assertEqual(saved["application_restoration_checks"], [recovery])
        self.assertEqual(saved["failure_stage"], "application-restoration-after-clone-submit")

    def test_interrupt_restores_apps_and_writes_failure(self):
        result = self.engine(interrupted=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "operator-interrupted")
        self.assertEqual(result["recovery"]["validation_instance_state"], "not-requested")
        self.drill.restore_apps.assert_called_once()
        self.drill.cleanup.assert_called_once()

    def test_cleanup_cli_does_not_emit_drill_pass_or_replace_failed_observation(self):
        tool = Path(__file__).resolve().parents[1] / "tools" / "cloudbank_sql_recovery.py"
        spec = importlib.util.spec_from_file_location("sql_recovery_cli_test", tool)
        cli = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(tool.parent), *sys.path]):
            spec.loader.exec_module(cli)
        environment = {"project": "test-project"}
        state = {**self.drill.state, "environment": environment}
        write_signed(self.root / "sql-recovery-state.json", state, "test-key", "test-operator")
        write_signed(self.root / "recovery-state.json", {}, "test-key", "test-operator")
        original = b'{"status":"failed"}\n'
        (self.root / "database-recovery.json").write_bytes(original)
        self.runtime.environment = Mock(return_value=environment)
        self.runtime.close = Mock(return_value={"status": "restored"})
        self.runtime.ready = Mock()
        captured = io.StringIO()
        with patch.dict(os.environ, {"LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY": "test-key",
                "LIGHTYEAR_NON_PRODUCTION_ACK": "I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS"}), \
             patch.object(cli, "GkeRuntime", return_value=self.runtime), patch.object(cli, "restore_state"), \
             patch.object(cli, "upload"), redirect_stdout(captured):
            code = cli.main(["recover", "--project", "test-project", "--region", "us-west1", "--cluster", "test-cluster",
                "--namespace", "test-ns", "--source-instance", "source", "--recovery-root", str(self.root),
                "--evidence-bucket", "gs://private-test", "--signer", "test-operator"])
        self.assertEqual(code, 0)
        self.assertIn("MS67_SQL_RECOVERY_CLEANUP=PASSED", captured.getvalue())
        self.assertNotIn("MS67_ISOLATED_SQL_RECOVERY=PASSED", captured.getvalue())
        self.assertEqual((self.root / "database-recovery.json").read_bytes(), original)


class RecoveryWindowTests(unittest.TestCase):
    def setUp(self):
        self.seconds = 0
        self.base = epoch("2026-09-06T01:05:00Z")
        self.observations = []

    def timestamp(self, offset):
        return datetime.fromtimestamp(self.base + offset, timezone.utc).isoformat().replace("+00:00", "Z")

    def sleep(self, seconds):
        self.seconds += seconds

    def select(self, query, timeout=600):
        return select_recovery_point(self.timestamp(-60), query, self.observations.append,
            clock=lambda: self.seconds, now=lambda: self.timestamp(self.seconds), pause=self.sleep, timeout=timeout)

    def test_stale_future_and_pre_checkpoint_points_wait_until_valid(self):
        points = iter([self.timestamp(5), self.timestamp(-90), self.timestamp(-41), self.timestamp(20)])
        query = Mock(side_effect=lambda: next(points))
        point, incident, age, began = self.select(query)
        self.assertEqual([o["reason"] for o in self.observations],
                         ["point-in-future", "point-precedes-checkpoint", "point-too-old", "accepted"])
        self.assertEqual(point, self.timestamp(20))
        self.assertEqual(incident, self.timestamp(30))
        self.assertEqual((age, began), (10, 30))
        self.assertEqual(query.call_count, 4)

    def test_query_latency_is_counted_and_an_aged_response_is_retried(self):
        durations = iter([61, 2])
        def query():
            point = self.timestamp(self.seconds)
            self.seconds += next(durations)
            return point
        point, incident, age, began = self.select(query)
        self.assertEqual(self.observations[0]["reason"], "point-too-old")
        self.assertEqual(self.observations[0]["query_duration_seconds"], 61)
        self.assertEqual(self.observations[0]["recovery_point_age_seconds"], 61)
        self.assertEqual((point, incident, age, began), (self.timestamp(71), self.timestamp(73), 2, 73))

    def test_bounded_wait_saves_last_rejected_point(self):
        with self.assertRaisesRegex(JourneyFailure, "pitr-recovery-window-timeout"):
            self.select(lambda: self.timestamp(-100), timeout=20)
        self.assertEqual(self.seconds, 20)
        self.assertEqual(self.observations[-1]["status"], "timed-out")
        self.assertEqual(self.observations[-1]["reason"], "point-precedes-checkpoint")
        self.assertEqual(self.observations[-1]["wait_elapsed_seconds"], 20)

    def test_fresh_response_after_wait_deadline_does_not_pass(self):
        def query():
            self.seconds += 31
            return self.timestamp(self.seconds)
        with self.assertRaisesRegex(JourneyFailure, "pitr-recovery-window-timeout"):
            self.select(query, timeout=30)
        self.assertEqual(self.observations[-1]["status"], "timed-out")

    def test_malformed_response_is_not_persisted(self):
        with self.assertRaisesRegex(JourneyFailure, "pitr-recovery-time-response-invalid"):
            self.select(lambda: "unexpected-private-response")
        self.assertEqual(self.observations[-1]["reason"], "invalid-recovery-time-response")
        self.assertNotIn("unexpected-private-response", json.dumps(self.observations))


@unittest.skipUnless(os.environ.get("LIGHTYEAR_SQL_RECOVERY_TEST_CONTAINER"), "requires disposable PostgreSQL 16 CI container")
class NativeSnapshotTests(unittest.TestCase):
    def sql(self, sql, *, check=True, user="postgres"):
        return subprocess.run(["docker", "exec", "-i", os.environ["LIGHTYEAR_SQL_RECOVERY_TEST_CONTAINER"],
            "psql", "-U", user, "-d", "postgres", "-X", "-qAt", "--set=ON_ERROR_STOP=1"],
            input=sql, text=True, capture_output=True, check=check, timeout=90)

    def test_native_snapshot_handles_order_duplicates_schema_sequences_and_rls(self):
        self.sql("CREATE TABLE recovery_fixture(id int, balance numeric, detail jsonb); "
                 "INSERT INTO recovery_fixture VALUES (1,2.50,'{\"a\":1}'),(2,3.00,'{}'); CREATE SEQUENCE recovery_fixture_seq;")
        try:
            before = normalize_snapshot(self.sql(SNAPSHOT_SQL).stdout)
            self.sql("CREATE TEMP TABLE reordered AS SELECT * FROM recovery_fixture ORDER BY id DESC; "
                     "TRUNCATE recovery_fixture; INSERT INTO recovery_fixture SELECT * FROM reordered;")
            self.assertEqual(before, normalize_snapshot(self.sql(SNAPSHOT_SQL).stdout))
            self.sql("INSERT INTO recovery_fixture SELECT * FROM recovery_fixture WHERE id=1;")
            duplicate = normalize_snapshot(self.sql(SNAPSHOT_SQL).stdout)
            self.assertNotEqual(before["state_sha256"], duplicate["state_sha256"])
            self.sql("SELECT nextval('recovery_fixture_seq');")
            self.assertNotEqual(duplicate, normalize_snapshot(self.sql(SNAPSHOT_SQL).stdout))
            self.sql("CREATE ROLE recovery_reader LOGIN; GRANT SELECT ON ALL TABLES IN SCHEMA public TO recovery_reader; "
                     "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO recovery_reader; "
                     "ALTER TABLE recovery_fixture ENABLE ROW LEVEL SECURITY; "
                     "CREATE POLICY hide_rows ON recovery_fixture USING (id=2);")
            self.assertNotEqual(self.sql(SNAPSHOT_SQL, user="recovery_reader", check=False).returncode, 0)
        finally:
            self.sql("DROP TABLE recovery_fixture; DROP SEQUENCE recovery_fixture_seq; DROP ROLE IF EXISTS recovery_reader;")


if __name__ == "__main__":
    unittest.main()
