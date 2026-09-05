from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import os
from contextlib import redirect_stdout
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from lightyear_data.cloudbank_journeys import (
    JourneyFailure, Journeys, OBSERVATION_TYPE, Response, SCENARIOS, SERVICES, execute_journeys,
)
from lightyear_data.cloudbank_journeys_gke import GkeRuntime
from lightyear_data.contracts import sign, verify_signature


class StatefulRuntime:
    """Test double only: never used by the CLI or admitted as native evidence."""
    owner = "journey-owner"

    def __init__(self, fault=""):
        self.customer_row = None
        self.accounts, self.journals, self.messages = {}, [], {}
        self.stopped, self.blocked, self.closed = set(), False, False
        self.fault = fault
        self.lock = threading.Lock()

    def ready(self):
        if self.stopped:
            raise JourneyFailure("service-not-ready")
        return {s: {"ready_replicas": 2} for s in SERVICES}

    def authorize(self):
        return {"issued": True}

    def request(self, service, method, path, role, body=None, headers=None):
        with self.lock:
            return self.handle(service, method, path, role, body, headers or {})

    def handle(self, service, method, path, role, body, headers):
        def response(status, payload=None, headers=None):
            return Response(status, json.dumps(payload).encode(), headers or {})
        if role is None:
            return response(401)
        if service == "customer":
            if method == "POST":
                self.customer_row = body
                return response(201)
            if self.customer_row is None:
                return response(404)
            return response(200, [self.customer_row] if path == "/api/v1/customer" else self.customer_row)
        if service == "account":
            if method == "POST":
                identifier = len(self.accounts) + 101
                self.accounts[identifier] = {**body, "accountId": identifier}
                return response(201, headers={"location": f"/api/v1/account/{identifier}"})
            identifier = int(path.split("/")[4])
            return response(200, [r for r in self.journals if r["accountId"] == identifier]
                            if path.endswith("/journal") else self.accounts[identifier])
        if service == "transfer":
            if "account" in self.stopped:
                if self.fault == "interrupt-dependency":
                    raise KeyboardInterrupt()
                return response(503)
            query = parse_qs(urlsplit(path).query)
            source, target, amount = [int(query[k][0]) for k in ("fromAccount", "toAccount", "amount")]
            if amount <= 0:
                return response(400)
            if amount > self.accounts[source]["accountBalance"]:
                return response(500 if self.fault == "insufficient-500" else 400)
            if self.fault != "accepted-no-effects":
                self.accounts[source]["accountBalance"] -= amount
                self.accounts[target]["accountBalance"] += amount
                self.journal(source, "WITHDRAW", amount)
                self.journal(target, "DEPOSIT", amount)
            return response(200, {"accepted": True})
        if service == "testrunner":
            key = headers["Idempotency-Key"]
            if key in self.messages:
                if self.fault == "duplicate-effects" and "accountId" in body:
                    self.journal(body["accountId"], "PENDING", body["amount"])
                return response(200)
            self.messages[key] = {"state": "PROCESSING", "attempts": 1, "body": body}
            if not self.blocked:
                self.deliver(key)
            return response(201)
        if service == "creditscore":
            return response(200, {"Credit Score": "650"})
        if service == "chatbot":
            return Response(200, b"A checking account supports everyday payments.", {})
        raise AssertionError(service)

    def journal(self, account, kind, amount):
        self.journals.append({"journalId": 1000 + len(self.journals), "accountId": account,
                             "journalType": kind, "journalAmount": amount})

    def deliver(self, key):
        row = self.messages[key]
        body = row["body"]
        if "accountId" in body:
            self.journal(body["accountId"], "PENDING", body["amount"])
        elif self.fault != "clearance-no-effects":
            next(r for r in self.journals if r["journalId"] == body["journalId"])["journalType"] = "DEPOSIT"
        row["state"] = "PROCESSED"

    def queue(self, key):
        return {k: self.messages[key][k] for k in ("state", "attempts")}

    def stop(self, service):
        self.stopped.add(service)

    def start(self, service):
        self.stopped.discard(service)
        if service == "checks":
            for key, row in self.messages.items():
                if row["state"] == "PROCESSING":
                    if self.fault != "no-redelivery-attempt":
                        row["attempts"] += 1
                    self.deliver(key)

    def crash_stopped(self, service):
        if service not in self.stopped:
            raise AssertionError("crash before stopping")

    def block_checks_delivery(self):
        self.blocked = True

    def restore_checks_delivery(self):
        self.blocked = False

    def restart(self, service):
        self.stop(service)
        self.start(service)

    def restart_all(self):
        for service in SERVICES:
            self.restart(service)

    def close(self):
        self.closed = True
        self.blocked = False
        self.stopped.clear()
        return {"status": "failed" if self.fault == "cleanup-failed" else "restored"}


class JourneyTests(unittest.TestCase):
    def execute(self, fault="", **kwargs):
        runtime = StatefulRuntime(fault)
        result = execute_journeys(runtime, {"test_double": True}, "test-key", "unit-test-only",
                                  run_id="unit-test", **kwargs)
        self.assertTrue(runtime.closed)
        self.assertFalse(runtime.stopped)
        self.assertFalse(runtime.blocked)
        self.assertTrue(verify_signature(result, "test-key"))
        return result

    def test_all_eighteen_business_checks(self):
        result = self.execute()
        self.assertEqual(result["status"], "passed-shared-journeys")
        self.assertEqual([r["id"] for r in result["scenarios"]], [s[0] for s in SCENARIOS])
        self.assertTrue(all(r["status"] == "passed" for r in result["scenarios"]))
        self.assertEqual(result["observation_type"], OBSERVATION_TYPE)
        self.assertNotIn("receipt_type", result)
        self.assertTrue(all(result[k] is False for k in ("ms65_complete", "ms66_complete", "ms67_complete")))
        self.assertNotIn("everyday payments", json.dumps(result))

    def test_real_effects_and_business_rejections_required(self):
        expected = {"accepted-no-effects": "transfer-balance-delta-invalid",
                    "insufficient-500": "insufficient-funds-not-business-rejection",
                    "duplicate-effects": "duplicate-message-mutated-state",
                    "clearance-no-effects": "check-clearance-state-invalid",
                    "no-redelivery-attempt": "inflight-redelivery-not-observed"}
        for fault, reason in expected.items():
            with self.subTest(fault=fault):
                result = self.execute(fault)
                self.assertEqual(result["status"], "failed")
                failed = [r for r in result["scenarios"] if r["status"] == "failed"]
                self.assertEqual([r["reason"] for r in failed], [reason])

    def test_interrupt_restores_and_cannot_sign_success(self):
        result = self.execute("interrupt-dependency")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["interrupted"])
        self.assertEqual(len(result["scenarios"]), 18)

    def test_cleanup_failure_invalidates_all_passing_scenarios(self):
        result = self.execute("cleanup-failed")
        self.assertEqual(result["status"], "failed")

    def test_failed_checkpoint_cannot_sign_incomplete_success(self):
        count = 0
        def checkpoint(_):
            nonlocal count
            count += 1
            if count == 1:
                raise OSError("sensitive diagnostic")
        result = self.execute(checkpoint=checkpoint)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("sensitive diagnostic", json.dumps(result))

    def test_unmarked_existing_customer_prevents_fixture_mutation(self):
        runtime = StatefulRuntime()
        runtime.customer_row = {"customerId": runtime.owner, "customerOtherDetails": "real record"}
        result = execute_journeys(runtime, {}, "key", "test", run_id="unit-test")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(runtime.accounts)


class GkeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = GkeRuntime(project="test-project", region="us-west1", cluster="test-cluster",
            namespace="test-namespace", images={s: f"test/{s}@sha256:" + "a" * 64 for s in SERVICES},
            run_id="unit-test", output=Path(self.temp.name), signing_key="key", signer="test")

    def token_response(self, scopes, claims=None):
        claims = claims if claims is not None else {"sub": "owner", "exp": time.time() + 3600, "scope": scopes.split()}
        encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return Response(200, json.dumps({"access_token": "head." + encoded + ".sig",
            "token_type": "Bearer", "scope": scopes}).encode(), {})

    def test_owner_privilege_and_claim_mismatch_rejected(self):
        self.runtime.credentials["owner"] = ("owner", "not-for-output")
        for response, expected in [
            (self.token_response("cloudbank.read cloudbank.write cloudbank.transfer cloudbank.internal"), "owner-client-is-privileged"),
            (self.token_response("cloudbank.transfer"), "oauth-owner-scopes-missing"),
            (self.token_response("cloudbank.read", []), "oauth-claims-invalid"),
            (self.token_response("cloudbank.read", {"scope": ["cloudbank.internal"]}), "oauth-scope-claims-mismatch"),
        ]:
            with self.subTest(expected=expected), patch.object(self.runtime, "send", return_value=response):
                with self.assertRaisesRegex(JourneyFailure, expected):
                    self.runtime.token("owner")

    def test_stop_writes_signed_recovery_intent_before_scale(self):
        self.runtime.original["account"] = {"uid": "original-uid", "replicas": 2}
        def command(*args, **kwargs):
            if args[0] == "scale":
                state = json.loads((Path(self.temp.name) / "recovery-state.json").read_text())
                self.assertTrue(verify_signature(state, "key"))
                self.assertEqual(state["stopped_services"], ["account"])
                raise JourneyFailure("operator-command-failed")
        with patch.object(self.runtime, "deployment"), patch.object(self.runtime, "kubectl", side_effect=command):
            with self.assertRaises(JourneyFailure):
                self.runtime.stop("account")
        self.assertEqual(self.runtime.stopped, {"account"})

    def test_failed_scale_can_restore_existing_healthy_pods(self):
        self.runtime.stopped.add("account")
        with patch.object(self.runtime, "deployment", return_value={"spec": {"replicas": 2}}), \
                patch.object(self.runtime, "wait_ready") as wait, patch.object(self.runtime, "kubectl") as command:
            self.runtime.start("account")
        wait.assert_called_once_with("account", None)
        command.assert_not_called()

    def test_configuration_recovery_preserves_operator_changes(self):
        self.runtime.checks_delivery = {"original": None, "injected": {"name": "ACCOUNT_JOURNAL_URL", "value": "blocked"}}
        deployment = {"spec": {"template": {"spec": {"containers": [{"name": "checks", "env": [
            {"name": "ACCOUNT_JOURNAL_URL", "value": "operator-new-value"}]}]}}}}
        with patch.object(self.runtime, "deployment", return_value=deployment), patch.object(self.runtime, "kubectl") as command:
            with self.assertRaisesRegex(JourneyFailure, "changed-by-another-operator"):
                self.runtime.restore_checks_delivery()
        command.assert_not_called()

    def test_patch_uses_version_precondition_and_stdin(self):
        deployment = {"metadata": {"resourceVersion": "123"}, "spec": {"template": {"spec": {"containers": [
            {"name": "checks", "env": [{"name": "EXISTING", "value": "keep-in-memory"}]}]}}}}
        with patch.object(self.runtime, "deployment", return_value=deployment), patch.object(self.runtime, "kubectl") as command:
            self.runtime.patch_checks_delivery(None)
        args, kwargs = command.call_args
        self.assertNotIn("keep-in-memory", str(args))
        self.assertEqual(json.loads(kwargs["data"])[0], {"op": "test", "path": "/metadata/resourceVersion", "value": "123"})

    def test_queue_never_changes_database(self):
        with patch.object(self.runtime, "sql", return_value={"state": "PROCESSING", "attempts": 1}) as sql:
            self.runtime.queue("ly-" + "b" * 48)
        query = sql.call_args.args[0]
        self.assertTrue(query.startswith("SELECT "))
        self.assertNotIn("UPDATE", query)
        with self.assertRaises(JourneyFailure):
            self.runtime.queue("' OR TRUE --")

    def test_http_redirect_never_forwards_bearer(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/credential-sink")
                self.end_headers()
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(self.runtime, "forward", return_value=f"http://127.0.0.1:{server.server_port}"):
                response = self.runtime.send("account", "GET", "/original", None, {"Authorization": "Bearer test"})
            self.assertEqual(response.status, 302)
            self.assertEqual(seen, ["/original"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


    def test_authorization_preflight_reports_every_role(self):
        with patch.object(self.runtime, "load_credentials"), patch.object(self.runtime, "token", side_effect=JourneyFailure("scope-denied")):
            result = self.runtime.authorization_preflight()
        self.assertEqual(set(result), {"owner", "account", "test", "credit", "chat"})
        self.assertTrue(all(r["status"] == "failed" for r in result.values()))

    def test_changed_running_image_is_rejected(self):
        deploy = {"metadata": {"uid": "uid"}, "spec": {"replicas": 2,
            "template": {"spec": {"containers": [{"name": "account", "image": "unbound:latest"}]}}}}
        with patch.object(self.runtime, "get", return_value=deploy):
            with self.assertRaisesRegex(JourneyFailure, "deployment-image-drift"):
                self.runtime.deployment("account")

    def test_probe_credentials_are_references_and_session_read_only(self):
        self.runtime.probe_image = "approved/postgres@sha256:" + "c" * 64
        manifest = None
        def kubectl(*args, **kwargs):
            nonlocal manifest
            if args[0] == "create":
                manifest = json.loads(kwargs["data"])
                return json.dumps({"metadata": {"uid": "probe-uid"}})
            return ""
        secret = {"SPRING_DATASOURCE_URL": "jdbc:postgresql://10.1.2.3:5432/checks",
                  "SPRING_DATASOURCE_PASSWORD": "must-never-persist"}
        with patch.object(self.runtime, "secret_json", return_value=secret), \
                patch.object(self.runtime, "kubectl", side_effect=kubectl), \
                patch.object(self.runtime, "sql", return_value={"postgresql": True, "queue_present": True}):
            self.runtime.create_probe()
        self.assertNotIn("must-never-persist", json.dumps(manifest))
        env = {e["name"]: e for e in manifest["spec"]["containers"][0]["env"]}
        self.assertIn("secretKeyRef", env["PGPASSWORD"]["valueFrom"])
        self.assertIn("default_transaction_read_only=on", env["PGOPTIONS"]["value"])
        self.assertFalse(manifest["spec"]["automountServiceAccountToken"])


class CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("journey_cli", Path(__file__).parents[1] / "tools/cloudbank_journeys.py")
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def test_missing_mutation_ack_stops_before_external_access(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(self.cli, "command") as command, redirect_stdout(io.StringIO()) as output:
            code = self.cli.main(["run", "--project", "test-project", "--region", "us-west1",
                                  "--cluster", "test-cluster", "--signer", "test"])
        self.assertEqual(code, 1)
        self.assertIn("non-production-mutation-ack-required", output.getvalue())
        command.assert_not_called()

    def test_tampered_recovery_state_rejected_before_mutations(self):
        state = sign({"stopped_services": ["account"]}, "key", "test")
        state["stopped_services"] = ["checks"]
        with self.assertRaisesRegex(JourneyFailure, "recovery-state-signature-invalid"):
            self.cli.restore_state(None, state, "key")


if __name__ == "__main__":
    unittest.main()
