from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_sql_recovery import (
    SNAPSHOT_SQL, SqlRecovery, epoch, invoke, normalize_snapshot, recovery_point_age, source_profile, verified, write_signed,
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

    def engine(self, *, mismatch=False, pitr_rto=30, backup_rto=30, interrupted=False, cleanup_failure=False):
        baseline = {"state_sha256": "a" * 64, "databases": {"b" * 64: {"table_count": 3}}}
        self.drill.discover = Mock(return_value=source_profile(instance(), "test-project", "us-west1", "source"))
        self.drill.state["coverage"] = {"database_count": 1}
        self.runtime.ready = Mock()
        self.drill.quiesce = Mock()
        self.drill.source_guard = Mock()
        restored = {**baseline, "state_sha256": "d" * 64} if mismatch else baseline
        self.drill.snapshot = Mock(side_effect=[baseline, baseline, baseline, restored, baseline])
        self.drill.operation = Mock(return_value="operation")
        if interrupted:
            self.drill.operation.side_effect = KeyboardInterrupt()
        self.drill.wait_operation = Mock()
        backup = {"id": "123", "instance": "source", "description": "test-run", "type": "ON_DEMAND", "status": "SUCCESSFUL",
                  "startTime": "2026-09-06T01:01:00Z", "endTime": "2026-09-06T01:02:00Z"}
        self.drill.cloud = Mock(side_effect=[[backup], {"latestRecoveryTime": "2026-09-06T01:04:50Z"},
                                           {"latestRecoveryTime": "2026-09-06T01:04:50Z"}])
        self.drill.claim_target = Mock(return_value=instance(self.drill.state["target"], "10.20.0.3"))
        self.drill.target_guard = Mock(return_value=instance(self.drill.state["target"], "10.20.0.3"))
        self.drill.restore_apps = Mock()
        self.drill.cleanup = Mock(side_effect=JourneyFailure("cleanup-failed") if cleanup_failure else None)
        with patch("lightyear_data.cloudbank_sql_recovery.utc", side_effect=["2026-09-06T01:00:30Z", "2026-09-06T01:05:00Z", "2026-09-06T01:10:00Z"]), \
             patch("lightyear_data.cloudbank_sql_recovery.time.time", return_value=epoch("2026-09-06T01:05:00Z")), \
             patch("lightyear_data.cloudbank_sql_recovery.time.monotonic", side_effect=[0, 100, 100 + pitr_rto, 1000, 1000 + backup_rto]):
            return self.drill.execute()

    def test_drill_passes_only_isolated_scope(self):
        result = self.engine()
        self.assertEqual(result["status"], "passed-isolated-database-recovery")
        self.assertEqual(result["pitr"]["recovery_point_age_seconds"], 10)
        self.assertEqual(result["pitr"]["database_rto_seconds"], 30)
        self.assertIsNone(result["backup"]["managed_backup_bytes_sha256"])
        self.assertFalse(result["ms67_complete"])
        self.assertTrue(verify_signature(json.loads((self.root / "database-recovery.json").read_text()), "test-key"))

    def test_changed_state_or_rto_overrun_or_cleanup_failure_cannot_pass(self):
        for fault in ({"mismatch": True}, {"pitr_rto": 601}, {"backup_rto": 601}, {"cleanup_failure": True}):
            with self.subTest(fault=fault):
                result = self.engine(**fault)
                self.assertEqual(result["status"], "failed")
                self.drill.restore_apps.assert_called()
                self.drill.cleanup.assert_called_once()

    def test_interrupt_restores_apps_and_writes_failure(self):
        result = self.engine(interrupted=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "operator-interrupted")
        self.drill.restore_apps.assert_called_once()
        self.drill.cleanup.assert_called_once()


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
