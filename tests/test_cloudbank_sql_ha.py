from __future__ import annotations

import base64
import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from lightyear_data.cloudbank_journeys import ACK, JourneyFailure, Response, SERVICES
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.cloudbank_sql_ha import DATABASE_SERVICES, HaRuntime, SqlHa, ha_profile
from lightyear_data.cloudbank_sql_recovery import verified, write_signed
from test_cloudbank_journeys import StatefulRuntime
from test_cloudbank_sql_recovery import instance


def regional():
    row = instance()
    row.update(instanceType="CLOUD_SQL_INSTANCE", connectionName="test-project:us-west1:source",
               gceZone="us-west1-a", secondaryGceZone="us-west1-b")
    row["settings"].update(availabilityType="REGIONAL", settingsVersion="12")
    return row


def done(name="failover-one", **extra):
    return {"name": name, "targetId": "source", "targetProject": "test-project", "status": "DONE",
            "operationType": "FAILOVER", "startTime": "2026-09-06T16:00:00Z", "endTime": "2026-09-06T16:00:41Z", **extra}


class Clock:
    value = 0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class HaDouble(StatefulRuntime):
    """Business semantics with explicit failure injection; never native evidence."""
    def __init__(self, root):
        super().__init__()
        self.project, self.region, self.context = "test-project", "us-west1", "gke_test-project_us-west1_test-cluster"
        self.namespace, self.run_id, self.output = "test-ns", "sql-ha-test-run", root
        self.images = {s: "private/" + s + "@sha256:" + "a" * 64 for s in SERVICES}
        self.probe_image = "private/probe@sha256:" + "b" * 64
        self.forwards, self.original, self.transfers = {}, {}, {}
        self.checks_delivery = None
        self.events, self.process_version = [], 1
        self.progress = lambda _: None
        self.recovery_checkpoint = lambda: None

    def request(self, service, method, path, role, body=None, headers=None):
        self.events.append((service, method, path))
        key = (headers or {}).get("Idempotency-Key")
        if service == "transfer" and key in self.transfers and self.fault != "transfer-replay":
            return self.transfers[key]
        result = super().request(service, method, path, role, body, headers)
        if service == "transfer" and result.status == 200:
            self.transfers[key] = result
        return result

    def process_identities(self):
        return {s: str(self.process_version) * 64 for s in SERVICES}

    def datasource_bindings(self, profile):
        return {s: {"jdbc_url_sha256": "c" * 64} for s in DATABASE_SERVICES}, "jdbc:postgresql://10.20.0.2/cloudbank"

    def create_probe(self, **kwargs):
        self.events.append(("probe", "CREATE", kwargs))

    def close(self):
        self.closed = True
        self.events.append(("probe", "DELETE", None))
        return {"status": "restored", "remaining_stopped_services": [], "errors": []}


class HaTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = HaDouble(self.root)
        self.drill = SqlHa(self.runtime, "source", "test-key", "test-operator")
        self.source, self.calls, self.clock = regional(), [], Clock()
        self.failover_seconds = 41
        self.after_failover = lambda: None
        self.drill.cloud = self.cloud

    def cloud(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ("instances", "describe"):
            return copy.deepcopy(self.source)
        if args[:2] == ("operations", "list"):
            return []
        if args[:2] == ("instances", "failover"):
            saved = verified(json.loads((self.root / "sql-ha-state.json").read_text()), "test-key")
            self.assertIsNone(saved["operation"]["name"])
            self.source["gceZone"], self.source["secondaryGceZone"] = self.source["secondaryGceZone"], self.source["gceZone"]
            self.after_failover()
            self.clock.advance(self.failover_seconds)
            return {"name": "failover-one"}
        if args[:2] == ("operations", "describe"):
            return done()
        raise AssertionError(args)

    def execute(self, **kwargs):
        with patch("lightyear_data.cloudbank_sql_ha.time.monotonic", self.clock), patch("lightyear_data.cloudbank_sql_ha.time.sleep", self.clock.advance):
            return self.drill.execute(**kwargs)

    def test_pass_requires_business_validation_and_exactly_one_failover(self):
        result = self.execute()
        self.assertEqual(result["status"], "passed-cloud-sql-ha-failover")
        self.assertEqual(result["recovery_seconds"], 41)
        self.assertEqual([c for c in self.calls if c[:2] == ("instances", "failover")],
                         [("instances", "failover", "source", "--async")])
        self.assertTrue(result["after"]["acknowledged_state_matches"])
        self.assertTrue(result["after"]["transfer_replay_no_extra_effects"])
        self.assertEqual(len(self.runtime.messages), 4)
        self.assertEqual(len(self.runtime.accounts), 3)
        self.assertTrue(self.runtime.closed)
        for milestone in ("ms65_complete", "ms66_complete", "ms67_complete"):
            self.assertFalse(result[milestone])
        verified(json.loads((self.root / "sql-ha.json").read_text()), "test-key")

    def test_preflight_has_no_probe_business_or_source_mutations(self):
        result = self.execute(preflight_only=True)
        self.assertEqual(result["status"], "preflight-passed")
        self.assertEqual(self.runtime.events, [])
        self.assertFalse(self.runtime.closed)
        self.assertFalse(any(c[:2] == ("instances", "failover") for c in self.calls))

    def test_recovery_limit_uses_entire_interval(self):
        self.failover_seconds = 601
        result = self.execute()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "ha-application-recovery-exceeds-600-seconds")
        self.assertEqual(result["recovery_seconds"], 601)
        self.assertTrue(result["after"]["acknowledged_state_matches"])
        self.assertEqual(result["recovery"]["status"], "restored")

    def test_exact_600_seconds_passes(self):
        self.failover_seconds = 600
        self.assertEqual(self.execute()["status"], "passed-cloud-sql-ha-failover")

    def test_application_restart_cannot_pass_automatic_reconnection(self):
        self.after_failover = lambda: setattr(self.runtime, "process_version", 2)
        result = self.execute()
        self.assertEqual(result["reason"], "application-process-changed-during-ha-drill")
        self.assertEqual(len(self.runtime.messages), 2)
        self.assertEqual(result["recovery"]["status"], "restored")

    def test_acknowledged_data_loss_fails_before_new_writes(self):
        def lose_balance():
            next(iter(self.runtime.accounts.values()))["accountBalance"] += 1
        self.after_failover = lose_balance
        result = self.execute()
        self.assertEqual(result["reason"], "ha-acknowledged-account-state-lost")
        self.assertEqual(len(self.runtime.messages), 2)

    def test_message_loss_fails(self):
        self.after_failover = lambda: next(iter(self.runtime.messages.values())).update(state="READY")
        self.assertEqual(self.execute()["reason"], "ha-acknowledged-message-state-lost")

    def test_duplicate_transfer_effects_fail(self):
        self.runtime.fault = "transfer-replay"
        self.assertEqual(self.execute()["reason"], "ha-transfer-replay-created-extra-effects")

    def test_customer_loss_is_not_recreated(self):
        self.after_failover = lambda: setattr(self.runtime, "customer_row", None)
        self.assertEqual(self.execute()["reason"], "ha-customer-read-failed")
        self.assertEqual(sum(s == "customer" and method == "POST" for s, method, _ in self.runtime.events), 1)

    def test_unknown_business_write_failure_is_not_retried_or_logged_raw(self):
        original = self.runtime.request
        def request(service, method, *args, **kwargs):
            if service == "account" and method == "POST":
                raise ValueError("PASSWORD=never-persist-this")
            return original(service, method, *args, **kwargs)
        self.runtime.request = Mock(side_effect=request)
        result = self.execute()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_stage"], "synthetic-checkpoint")
        self.assertIsNone(self.drill.state["operation"])
        self.assertEqual(sum(c.args[:2] == ("account", "POST") for c in self.runtime.request.call_args_list), 1)
        self.assertNotIn("never-persist-this", (self.root / "sql-ha.json").read_text())

    def test_transient_read_recovers_without_repeating_writes(self):
        original = self.runtime.request
        remaining = [1]
        def request(service, method, *args, **kwargs):
            if self.clock.value and remaining[0] and service == "account" and method == "GET":
                remaining[0] -= 1
                raise JourneyFailure("ha-transient-read-failed")
            return original(service, method, *args, **kwargs)
        self.runtime.request = request
        result = self.execute()
        self.assertEqual(result["status"], "passed-cloud-sql-ha-failover")
        self.assertEqual(result["recovery_seconds"], 46)
        self.assertEqual(len(self.runtime.accounts), 3)
        self.assertEqual(len(self.runtime.transfers), 2)

    def test_interruption_retains_intent_and_never_resubmits(self):
        self.after_failover = Mock(side_effect=KeyboardInterrupt())
        result = self.execute()
        self.assertEqual(result["reason"], "operator-interrupted")
        self.assertIsNone(self.drill.state["operation"]["name"])
        self.assertEqual(result["recovery"]["status"], "failed")
        with self.assertRaisesRegex(JourneyFailure, "intent-already-exists"):
            self.drill.submit()
        self.assertEqual(sum(c[:2] == ("instances", "failover") for c in self.calls), 1)

    def test_cleanup_cannot_convert_failed_drill_into_pass(self):
        self.runtime.fault = "transfer-replay"
        self.execute()
        original = (self.root / "sql-ha.json").read_bytes()
        self.drill.observation = None
        recovery = self.drill.cleanup(observe_operation=True)
        self.assertEqual(recovery["status"], "restored")
        self.assertEqual((self.root / "sql-ha.json").read_bytes(), original)
        self.assertEqual(sum(c[:2] == ("instances", "failover") for c in self.calls), 1)

    def test_cleanup_failure_blocks_pass(self):
        self.runtime.close = Mock(return_value={"status": "failed"})
        result = self.execute()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["recovery"]["errors"][0]["reason"], "ha-probe-or-tunnel-cleanup-failed")

    def test_region_primary_private_network_and_standby_guards(self):
        for mutate in (lambda r: r.update(instanceType="READ_REPLICA_INSTANCE"),
                       lambda r: r.update(masterInstanceName="another"),
                       lambda r: r.update(secondaryGceZone="us-west1-a"),
                       lambda r: r.update(gceZone="us-east1-a"),
                       lambda r: r.update(failoverReplica={"available": False}),
                       lambda r: r["settings"].update(availabilityType="ZONAL"),
                       lambda r: r["settings"]["ipConfiguration"].update(ipv4Enabled=True)):
            row = regional()
            mutate(row)
            with self.subTest(row=row), self.assertRaises(JourneyFailure):
                ha_profile(row, "test-project", "us-west1", "source")

    def test_active_operation_or_source_change_blocks_submission(self):
        self.drill.preflight()
        self.source["settings"]["settingsVersion"] = "13"
        with self.assertRaisesRegex(JourneyFailure, "source-changed"):
            self.drill.submit()
        self.assertIsNone(self.drill.state["operation"])
        self.drill.cloud = Mock(return_value=[{"status": "RUNNING"}])
        with self.assertRaisesRegex(JourneyFailure, "active-operations"):
            self.drill.idle()

    def test_promotion_and_endpoint_identity_required(self):
        self.drill.preflight()
        with self.assertRaisesRegex(JourneyFailure, "promotion-not-observed"):
            self.drill.promoted()
        self.source["createTime"] = "2026-09-06T17:00:00Z"
        with self.assertRaisesRegex(JourneyFailure, "identity-changed"):
            self.drill.promoted()

    def test_two_status_retries_keep_same_operation_and_deadline(self):
        self.drill.state["operation"] = {"name": "failover-one"}
        error = JourneyFailure("operator-command-failed-unavailable")
        self.drill.cloud = Mock(side_effect=[error, done(status="RUNNING"), error, done()])
        with patch("lightyear_data.cloudbank_sql_ha.time.monotonic", self.clock), patch("lightyear_data.cloudbank_sql_ha.time.sleep", self.clock.advance):
            self.drill.wait_operation()
        self.assertEqual(self.clock.value, 16)
        self.assertEqual([c.args for c in self.drill.cloud.call_args_list], [("operations", "describe", "failover-one")] * 4)
        saved = verified(json.loads((self.root / "sql-ha-state.json").read_text()), "test-key")
        self.assertEqual(saved["operation"]["status_read_failures"]["count"], 2)

    def test_read_budget_does_not_reset_after_valid_running_status(self):
        self.drill.state["operation"] = {"name": "failover-one"}
        error = JourneyFailure("operator-command-failed-exit-1")
        self.drill.cloud = Mock(side_effect=[error, done(status="RUNNING"), error, done(status="RUNNING"), error])
        with patch("lightyear_data.cloudbank_sql_ha.time.sleep"), self.assertRaises(JourneyFailure):
            self.drill.wait_operation()
        self.assertEqual(self.drill.cloud.call_count, 5)
        self.assertFalse(self.drill.state["operation"]["status_read_failures"]["recent"][-1]["retry_scheduled"])

    def test_permission_and_provider_failures_are_not_retried(self):
        self.drill.state["operation"] = {"name": "failover-one"}
        for value in (JourneyFailure("operator-command-failed-permission-denied"), done(error={"code": "INTERNAL"}),
                      done(targetId="other"), done(targetProject="other"), done(operationType="CLONE"), done(name="other")):
            self.drill.cloud = Mock(side_effect=value) if isinstance(value, Exception) else Mock(return_value=value)
            with self.subTest(value=value), patch("lightyear_data.cloudbank_sql_ha.time.sleep") as pause, self.assertRaises(JourneyFailure):
                self.drill.wait_operation()
            self.drill.cloud.assert_called_once()
            pause.assert_not_called()

    def test_slow_status_response_cannot_extend_wait_deadline(self):
        self.drill.state["operation"] = {"name": "failover-one"}
        def delayed(*args, **kwargs):
            self.clock.advance(11)
            return done()
        self.drill.cloud = delayed
        with patch("lightyear_data.cloudbank_sql_ha.time.monotonic", self.clock), self.assertRaisesRegex(JourneyFailure, "operation-timeout"):
            self.drill.wait_operation(timeout=10)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = HaRuntime(project="test-project", region="us-west1", cluster="test-cluster", namespace="test-ns",
            images={s: "private/" + s + "@sha256:" + "a" * 64 for s in SERVICES},
            run_id="sql-ha-test", output=Path("/unused"))
        self.deploy = {"metadata": {"uid": "deployment"}, "spec": {"replicas": 2, "template": {}}}
        self.pods = [{"metadata": {"uid": "pod" + str(i)}, "spec": {"containers": []},
            "status": {"containerStatuses": [{"name": "account", "containerID": "container" + str(i),
                "restartCount": 0, "state": {"running": {"startedAt": "2026-09-06T16:00:00Z"}},
                "imageID": "private/account@sha256:" + "a" * 64}]}} for i in (1, 2)]

    def test_all_mutation_methods_and_recovery_intents_are_blocked(self):
        for method in ("stop", "start", "restart", "restart_all", "crash_stopped", "block_checks_delivery", "patch_checks_delivery"):
            with self.subTest(method=method), self.assertRaises(JourneyFailure):
                getattr(self.runtime, method)("account")
        self.runtime.stopped.add("account")
        with self.assertRaisesRegex(JourneyFailure, "must-not-contain-app-mutations"):
            self.runtime.close()

    def test_process_fingerprint_catches_same_pod_container_restart(self):
        self.runtime.deployment = Mock(return_value=self.deploy)
        self.runtime.pods = Mock(return_value=self.pods)
        with patch("lightyear_data.cloudbank_sql_ha.SERVICES", ("account",)):
            before = self.runtime.process_identities()
            for field, value in (("restartCount", 1), ("containerID", "replacement")):
                original = self.pods[0]["status"]["containerStatuses"][0][field]
                self.pods[0]["status"]["containerStatuses"][0][field] = value
                self.assertNotEqual(self.runtime.process_identities(), before)
                self.pods[0]["status"]["containerStatuses"][0][field] = original

    def test_retry_classification_never_retries_business_posts(self):
        with patch.object(GkeRuntime, "send", return_value=Response(503, b"", {})):
            with self.assertRaisesRegex(JourneyFailure, "transient-read"):
                self.runtime.send("account", "GET", "/api/v1/account/1", None, {})
            with self.assertRaisesRegex(JourneyFailure, "transient-read"):
                self.runtime.send("azn-server", "POST", "/oauth2/token", b"", {})
            self.assertEqual(self.runtime.send("transfer", "POST", "/transfer", b"", {}).status, 503)

    def test_probe_uses_bound_kubernetes_url_without_fetching_another_version(self):
        self.runtime.probe_image = "private/probe@sha256:" + "b" * 64
        self.runtime.recovery_checkpoint = Mock()
        self.runtime.secret_json = Mock(side_effect=AssertionError("must not fetch another URL"))
        self.runtime.kubectl = Mock(side_effect=[json.dumps({"metadata": {"uid": "probe"}}), "ready"])
        self.runtime.sql = Mock(return_value={"postgresql": True, "queue_present": True})
        self.runtime.create_probe(jdbc_url="jdbc:postgresql://10.20.0.2/cloudbank")
        pod = json.loads(self.runtime.kubectl.call_args_list[0].kwargs["data"])
        env = {e["name"]: e for e in pod["spec"]["containers"][0]["env"]}
        self.assertEqual(env["PGHOST"]["value"], "10.20.0.2")
        self.assertIn("secretKeyRef", env["PGPASSWORD"]["valueFrom"])
        self.assertIn("default_transaction_read_only=on", env["PGOPTIONS"]["value"])

    def test_datasource_requires_source_private_ip_and_running_secret_reference(self):
        secrets = {}
        pods = {}
        for service in SERVICES:
            name = "cloudbank-" + service + "-external"
            data = {k: base64.b64encode(v.encode()).decode() for k, v in {
                "SPRING_DATASOURCE_URL": "jdbc:postgresql://10.20.0.2/cloudbank",
                "SPRING_DATASOURCE_USERNAME": "synthetic", "SPRING_DATASOURCE_PASSWORD": "never-persist"}.items()}
            secrets[name] = {"metadata": {"uid": name}, "data": data if service in DATABASE_SERVICES else {}}
            pods[service] = [{"metadata": {"name": service + "-pod"}, "spec": {
                "containers": [{"name": service, "envFrom": [{"secretRef": {"name": name}}]}]}}] * 2
        self.runtime.get = lambda kind, name: secrets[name]
        self.runtime.pods = lambda service: pods[service]
        self.runtime.kubectl = Mock(return_value="jdbc:postgresql://10.20.0.2/cloudbank\n")
        profile = {"private_ip": "10.20.0.2"}
        result, url = self.runtime.datasource_bindings(profile)
        self.assertEqual(set(result), DATABASE_SERVICES)
        self.assertNotIn("never-persist", json.dumps(result))
        self.assertEqual(url, "jdbc:postgresql://10.20.0.2/cloudbank")
        with self.assertRaisesRegex(JourneyFailure, "source-binding-invalid"):
            self.runtime.datasource_bindings({"private_ip": "10.20.0.3"})
        self.runtime.kubectl.return_value = "jdbc:postgresql://10.20.0.3/cloudbank\n"
        with self.assertRaisesRegex(JourneyFailure, "differs-from-synced-secret"):
            self.runtime.datasource_bindings(profile)
        self.runtime.kubectl.return_value = url + "\n"
        pods["account"][0]["spec"]["containers"][0]["env"] = [{"name": "SPRING_DATASOURCE_URL", "value": url}]
        with self.assertRaisesRegex(JourneyFailure, "override-not-supported"):
            self.runtime.datasource_bindings(profile)

    def test_probe_cleanup_observes_deletion_and_cannot_hide_a_stuck_pod(self):
        clock = Clock()
        with patch.object(GkeRuntime, "close", return_value={"status": "restored"}):
            self.runtime.kubectl = Mock(side_effect=['{"metadata":{}}', ''])
            with patch("lightyear_data.cloudbank_sql_ha.time.sleep", clock.advance), patch("lightyear_data.cloudbank_sql_ha.time.monotonic", clock):
                self.assertEqual(self.runtime.close()["status"], "restored")
            self.runtime.kubectl = Mock(return_value='{"metadata":{}}')
            with patch("lightyear_data.cloudbank_sql_ha.time.sleep", clock.advance), patch("lightyear_data.cloudbank_sql_ha.time.monotonic", clock), \
                    self.assertRaisesRegex(JourneyFailure, "deletion-not-observed"):
                self.runtime.close()


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(cls.project / "tools"))
        spec = importlib.util.spec_from_file_location("ha_cli", cls.project / "tools/cloudbank_sql_ha.py")
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)
        sys.path.pop(0)

    def args(self, action):
        return [action, "--project", "test-project", "--region", "us-west1", "--cluster", "test-cluster",
                "--namespace", "test-ns", "--source-instance", "source", "--signer", "test-operator",
                "--evidence-bucket", "gs://private-test/ha"]

    def test_mutation_ack_required_before_credentials_or_cloud_calls(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(self.cli, "invoke") as invoke, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.cli.main(self.args("run")), 1)
        self.assertIn("non-production-mutation-ack-required", out.getvalue())
        invoke.assert_not_called()

    def test_read_only_preflight_does_not_require_mutation_ack(self):
        with patch.dict(os.environ, {"LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY": "test-key"}, clear=True), \
                patch.object(self.cli, "load_bound_inputs", side_effect=JourneyFailure("test-input-admission-reached")), \
                redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.cli.main(self.args("preflight")), 1)
        self.assertIn("test-input-admission-reached", out.getvalue())

    def test_recover_rejects_signed_application_mutation_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_signed(root / "sql-ha-state.json", {}, "test-key", "operator")
            write_signed(root / "recovery-state.json", {"stopped_services": ["account"]}, "test-key", "operator")
            with patch.dict(os.environ, {"LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY": "test-key", "LIGHTYEAR_NON_PRODUCTION_ACK": ACK}), \
                    patch.object(self.cli, "HaRuntime") as runtime, redirect_stdout(io.StringIO()) as out:
                self.assertEqual(self.cli.main(self.args("recover") + ["--recovery-root", str(root)]), 1)
            runtime.assert_not_called()
            self.assertIn("must-not-contain-app-mutations", out.getvalue())

    def test_successful_cleanup_preserves_original_failure_and_uploads_only_whitelist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = HaDouble(root)
            environment = {"project": "test-project"}
            runtime.environment = Mock(return_value=environment)
            drill = SqlHa(runtime, "source", "test-key", "operator")
            drill.state["bindings"] = {"environment": environment}
            write_signed(root / "sql-ha-state.json", drill.state, "test-key", "operator")
            write_signed(root / "recovery-state.json", {"stopped_services": [], "checks_delivery": None}, "test-key", "operator")
            original = b'{"status":"failed"}\n'
            (root / "sql-ha.json").write_bytes(original)
            with patch.dict(os.environ, {"LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY": "test-key", "LIGHTYEAR_NON_PRODUCTION_ACK": ACK}), \
                    patch.object(self.cli, "HaRuntime", return_value=runtime), patch.object(self.cli, "restore_state"), \
                    patch.object(self.cli, "upload") as upload, redirect_stdout(io.StringIO()) as out:
                self.assertEqual(self.cli.main(self.args("recover") + ["--recovery-root", str(root)]), 0)
            self.assertIn("MS67_SQL_HA_RECOVER=PASSED", out.getvalue())
            self.assertNotIn("MS67_SQL_HA_RUN=PASSED", out.getvalue())
            self.assertEqual((root / "sql-ha.json").read_bytes(), original)
            self.assertEqual(set(upload.call_args.kwargs["file_names"]), {"sql-ha-state.json", "sql-ha.json", "recovery-state.json", "ha-cleanup.json"})
            self.assertEqual(upload.call_args.kwargs["marker"], "MS67_SQL_HA")
            verified(json.loads((root / "ha-cleanup.json").read_text()), "test-key")

    def test_tampered_recovery_signature_is_rejected_before_runtime_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_signed(root / "sql-ha-state.json", {"source": "source"}, "test-key", "operator")
            value = json.loads((root / "sql-ha-state.json").read_text())
            value["source"] = "production"
            (root / "sql-ha-state.json").write_text(json.dumps(value))
            with patch.dict(os.environ, {"LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY": "test-key", "LIGHTYEAR_NON_PRODUCTION_ACK": ACK}), \
                    patch.object(self.cli, "HaRuntime") as runtime, redirect_stdout(io.StringIO()) as out:
                self.assertEqual(self.cli.main(self.args("recover") + ["--recovery-root", str(root)]), 1)
            self.assertIn("evidence-content-or-signature-invalid", out.getvalue())
            runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
