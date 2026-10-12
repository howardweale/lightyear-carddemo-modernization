"""Offline only: replace environment and all HTTP/process boundaries."""
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from lightyear_factory import posttran_phase1_transport as t


def payload():
    return dict(model="gpt-6-astra", reasoning={"effort": "high"}, input=[],
                store=False, max_output_tokens=64000, truncation="disabled",
                service_tier="default")


def response():
    return dict(status="completed", usage=dict(input_tokens=42, output_tokens=12))


class TransportTests(unittest.TestCase):
    def worker(self, value=None, status=200, raw=None, exception=None, environment=None):
        connection = Mock()
        connection.getresponse.return_value.status = status
        connection.getresponse.return_value.read.return_value = raw or t.canonical(value or response())
        if exception:
            connection.request.side_effect = exception
        env = {t.KEY_NAME: "fake-only-secret"} if environment is None else environment
        with patch.object(t.os, "environ", env), patch.object(t.http.client, "HTTPSConnection", return_value=connection) as constructor:
            result = t._http_worker(t.GENERATE, payload())
        return result, connection, constructor

    def test_tls_fixed_timeout_hashes_and_one_request(self):
        result, connection, constructor = self.worker()
        self.assertTrue(result["ok"])
        self.assertEqual(result["request_sha256"], t.sha(t.canonical(payload())))
        self.assertEqual(result["response_sha256"], t.sha(t.canonical(response())))
        context = constructor.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(constructor.call_args.kwargs["timeout"], 30)
        connection.sock.settimeout.assert_called_once_with(1800)
        connection.request.assert_called_once()
        self.assertFalse(json.loads(connection.request.call_args.kwargs["body"])["store"])

    def test_generic_environment_is_not_a_fallback(self):
        result, connection, constructor = self.worker(environment={"OPENAI_API_KEY": "fake-only-secret"})
        self.assertFalse(result["ok"])
        constructor.assert_not_called()
        connection.request.assert_not_called()

    def test_http_errors_never_retry_or_log_body(self):
        for status in (301, 429, 500):
            result, connection, _ = self.worker(status=status, raw=b'{"error":"private server text"}')
            self.assertFalse(result["ok"])
            self.assertNotIn("private server text", json.dumps(result))
            connection.request.assert_called_once()

    def test_exception_secret_is_redacted(self):
        result, connection, _ = self.worker(exception=RuntimeError("fake-only-secret"))
        self.assertNotIn("fake-only-secret", json.dumps(result))
        self.assertFalse(result["ok"])
        connection.request.assert_called_once()

    def test_raw_and_escaped_key_echo_refused(self):
        for raw in (b'{"x":"fake-only-secret"}', b'{"x":"fake-only-\\u0073ecret"}'):
            result, _, _ = self.worker(raw=raw)
            self.assertEqual(result["error_code"], "sensitive-response-refused")
            self.assertNotIn("fake-only-secret", json.dumps(result))

    def test_incomplete_missing_usage_and_over_cap_refused(self):
        for value in ({"status": "incomplete"}, {"status": "completed"},
                      dict(status="completed", usage=dict(input_tokens=42, output_tokens=64001)),
                      dict(status="completed", usage=dict(input_tokens=True, output_tokens=1))):
            result, _, _ = self.worker(value=value)
            self.assertFalse(result["ok"])

    def test_contract_refuses_store_and_wrong_output_cap(self):
        for change in ({"store": True}, {"max_output_tokens": 64001}):
            with self.assertRaises(t.Refusal):
                t._payload_valid(t.GENERATE, dict(payload(), **change))

    def test_wall_timeout_single_process(self):
        with patch.object(t.subprocess, "run", side_effect=subprocess.TimeoutExpired("fake", 1800)) as run:
            result = t.network_once(t.GENERATE, payload())
        self.assertEqual(result["error_code"], "transport-wall-timeout")
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["timeout"], 1800)

    def test_untrusted_worker_stderr_is_not_returned(self):
        with patch.object(t.subprocess, "run", return_value=Mock(returncode=0, stderr=b"fake-only-secret", stdout=b"{}")):
            result = t.network_once(t.GENERATE, payload())
        self.assertEqual(result["error_code"], "worker-failed")
        self.assertNotIn("fake-only-secret", json.dumps(result))

    def setup_state(self, directory):
        base = Path(directory) / "receipt"
        base.mkdir()
        ledger = Path(directory) / "phase1-ledger.json"
        return base, ledger

    def test_preflight_never_touches_existing_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            base, ledger = self.setup_state(directory)
            ledger.write_bytes(b"preserve previous ledger exactly")
            with patch.object(t, "locations", return_value=(base, ledger)), patch.object(t, "packet_payload", return_value=(payload(), {"file": "hash"})), patch.object(t, "network_once", return_value=dict(ok=True, response_sha256="a" * 64, response=dict(object="response.input_tokens", input_tokens=42))):
                result = t.preflight({}, "plan")
            self.assertEqual(ledger.read_bytes(), b"preserve previous ledger exactly")
            self.assertEqual(result["attempts_consumed"], 0)
            receipt = json.loads((base / "preflight.json").read_bytes())
            t.verify_seal(receipt)
            self.assertTrue(receipt["outside_reservation_ledger"])

    def test_failed_preflight_consumes_zero_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            base, ledger = self.setup_state(directory)
            with patch.object(t, "locations", return_value=(base, ledger)), patch.object(t, "packet_payload", return_value=(payload(), {})), patch.object(t, "network_once", return_value=dict(ok=False, error_code="http-status-refused", response_sha256="b" * 64)) as network:
                with self.assertRaises(t.Refusal):
                    t.preflight({}, "plan")
                with self.assertRaises(t.Refusal):
                    t.preflight({}, "plan")
            network.assert_called_once()
            self.assertFalse(ledger.exists())
            self.assertEqual(json.loads((base / "preflight.json").read_bytes())["attempts_consumed"], 0)

    def test_reservation_precedes_generation_and_failure_consumed(self):
        for success in (True, False):
            with tempfile.TemporaryDirectory() as directory:
                base, ledger = self.setup_state(directory)
                def network(endpoint, body):
                    if endpoint == t.COUNT:
                        self.assertFalse(ledger.exists())
                        return dict(ok=True, response_sha256="c" * 64, response=dict(object="response.input_tokens", input_tokens=42))
                    state = json.loads(ledger.read_bytes())
                    self.assertEqual(state["reservations"][0]["status"], "reserved")
                    self.assertEqual(state["reservations"][0]["reserved_usd"], 11.05)
                    return dict(ok=success, error_code="http-status-refused", response_sha256="d" * 64, response=response())
                with patch.object(t, "locations", return_value=(base, ledger)), patch.object(t, "packet_payload", return_value=(payload(), {})), patch.object(t, "network_once", side_effect=network) as calls:
                    t.preflight({}, "plan")
                    if success:
                        t.attempt_one({}, "plan")
                    else:
                        with self.assertRaises(t.Refusal):
                            t.attempt_one({}, "plan")
                    with self.assertRaises(t.Refusal):
                        t.attempt_one({}, "plan")
                self.assertEqual(calls.call_count, 2)
                state = json.loads(ledger.read_bytes())
                t.verify_seal(state)
                self.assertEqual(state["reservations"][0]["status"], "completed" if success else "failed")

    def test_no_preflight_means_no_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            base, ledger = self.setup_state(directory)
            with patch.object(t, "locations", return_value=(base, ledger)), patch.object(t, "packet_payload", return_value=(payload(), {})), patch.object(t, "network_once") as network:
                with self.assertRaises(FileNotFoundError):
                    t.attempt_one({}, "plan")
                network.assert_not_called()
            self.assertFalse(ledger.exists())

    def test_changed_packet_and_stale_preflight_refuse_before_reservation(self):
        for change in ("packet", "time"):
            with tempfile.TemporaryDirectory() as directory:
                base, ledger = self.setup_state(directory)
                with patch.object(t, "locations", return_value=(base, ledger)), patch.object(t, "packet_payload", return_value=(payload(), {})), patch.object(t, "network_once", return_value=dict(ok=True, response_sha256="c" * 64, response=dict(object="response.input_tokens", input_tokens=42))):
                    t.preflight({}, "plan")
                receipt = json.loads((base / "preflight.json").read_bytes())
                receipt.pop("content_sha256")
                if change == "packet":
                    receipt["packet_sha256"] = {"changed": "bytes"}
                else:
                    receipt["finished_at"] = "2000-01-01T00:00:00+00:00"
                (base / "preflight.json").write_bytes(t.canonical(t.seal(receipt)))
                with patch.object(t, "locations", return_value=(base, ledger)), patch.object(t, "packet_payload", return_value=(payload(), {})), patch.object(t, "network_once") as network:
                    with self.assertRaises(t.Refusal):
                        t.attempt_one({}, "plan")
                    network.assert_not_called()
                self.assertFalse(ledger.exists())

    def test_published_amendment_exact_go_and_transport_pin(self):
        path = t.ROOT / "docs/factory/posttran-second-opinion/dedicated-transport-plan-2026-10-11.json"
        plan = json.loads(path.read_bytes())
        with self.assertRaisesRegex(t.Refusal, "exact-amended-plan"):
            t.load_plan(path, "go POSTTRAN " + plan["supersedes_plan_sha256"])
        # Avoid even the pinned executable read in this unit test: self-hash mismatch
        # is checked first and must refuse before accessing that file.
        plan.pop("content_sha256")
        plan["dispatch"]["dedicated_transport"]["sha256"] = "0" * 64
        altered = t.seal(plan)
        with tempfile.TemporaryDirectory() as directory:
            altered_path = Path(directory) / "plan.json"
            altered_path.write_bytes(t.canonical(altered))
            with self.assertRaisesRegex(t.Refusal, "transport-hash-mismatch"):
                t.load_plan(altered_path, "go POSTTRAN " + altered["content_sha256"])


if __name__ == "__main__":
    unittest.main()
