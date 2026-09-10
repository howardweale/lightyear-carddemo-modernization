"""Admission tests: a process exit or a partial workload must never imply success."""
from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import JourneyFailure, SERVICES, hashed
from lightyear_data.cloudbank_sustained_load import (
    HTTP_SERVICES, OPERATIONS, OBSERVATION_TYPE, PASS, validate_summary, validate_failure_diagnostics,
    verify_observation, workload,
)
from lightyear_data.contracts import sign

ROOT = Path(__file__).resolve().parents[1]


def summary():
    counts = {name: 40 for name in OPERATIONS}
    counts.update(oauth=50, account=320, journals=240, transfer=80)
    requests = sum(counts.values())
    replicas = {f"{s}_{i}": 1 for s in HTTP_SERVICES for i in range(2)}
    replicas["account_0"] += requests - len(replicas)
    return {"format": "lightyear-k6-business-summary-v2", "run_id": "ms67-load-test",
            "configured_duration_seconds": 300, "configured_vus": 10, "cycle_seconds": 10,
            "measured_duration_ms": 301000, "requests": requests, "errors": 0,
            "http_requests": requests, "http_failures": 0, "p95_ms": 500, "latency_samples": requests,
            "cycles_started": 40, "cycles_completed": 40, "checks_effects": 80, "checks_delivery_p95_ms": 1500,
            "iterations": 40, "vus_max": 10, "operations": {name: {"requests": n, "latency_samples": n, "p95_ms": 400, "errors": 0}
                for name, n in counts.items()}, "vu_cycles": {str(i): 4 for i in range(1, 11)}, "replica_requests": replicas,
            "failure_diagnostics": []}


def failed_transfer():
    value = summary()
    value.update(measured_duration_ms=7000, errors=1, http_failures=1)
    value["operations"]["transfer"]["errors"] = 1
    value["failure_diagnostics"] = [{"operation": "transfer", "kinds": {"transport": 1},
        "transport_causes": {"unexpected_eof": 1}, "http_status": {"min": 200, "max": 200},
        "k6_error_code": {"min": 1000, "max": 1000}, "replica_index": {"min": 1, "max": 1}}]
    return value


class AdmissionTests(unittest.TestCase):
    def test_exact_threshold_can_pass(self):
        self.assertEqual(validate_summary(summary(), "ms67-load-test")["p95_ms"], 500)

    def test_client_failure_precedes_duration_even_when_server_returned_200(self):
        failed = failed_transfer()
        with self.assertRaisesRegex(JourneyFailure, "load-client-transport-error"):
            validate_summary(failed, failed["run_id"])
        # Removing/relabeling counters cannot turn retained failure evidence
        # into a passing observation, even with a full-duration measurement.
        failed.update(errors=0, http_failures=0, measured_duration_ms=301000)
        with self.assertRaisesRegex(JourneyFailure, "load-client-transport-error"):
            validate_summary(failed, failed["run_id"])
        for kind, reason in (("http_status", "load-unexpected-http-status"),
                             ("response_json", "load-response-json-invalid"),
                             ("response_body", "load-response-body-invalid"),
                             ("business_contract", "load-business-contract-failed")):
            failed = failed_transfer()
            failed["failure_diagnostics"][0].update(kinds={kind: 1}, transport_causes={})
            with self.subTest(kind=kind), self.assertRaisesRegex(JourneyFailure, reason):
                validate_summary(failed, failed["run_id"])

    def test_failure_diagnostics_reject_unbounded_or_raw_response_fields(self):
        original = failed_transfer()["failure_diagnostics"]
        validate_failure_diagnostics(original)
        changes = (("url", "http://private.invalid/?secret=PRIVATE"),
                   ("response", "PRIVATE"), ("operation", "PRIVATE"),
                   ("transport_causes", {"PRIVATE": 1}), ("kinds", {"transport": 11}),
                   ("http_status", {"min": 200, "max": 199}),
                   ("k6_error_code", {"min": 0, "max": float("inf")}),
                   ("replica_index", {"min": True, "max": 1}))
        for name, value in changes:
            changed = copy.deepcopy(original)
            changed[0][name] = value
            with self.subTest(field=name), self.assertRaisesRegex(JourneyFailure, "load-failure-diagnostics-invalid"):
                validate_failure_diagnostics(changed)
        with self.assertRaises(JourneyFailure):
            validate_failure_diagnostics(original * 2)

    def test_failed_incomplete_or_relabelled_runs_are_rejected(self):
        cases = {"run_id": "another", "configured_duration_seconds": 3, "configured_vus": 1,
                 "cycle_seconds": 0, "measured_duration_ms": 299999, "vus_max": 9,
                 "requests": 999, "errors": 1, "http_failures": 1, "p95_ms": 500.001,
                 "latency_samples": 100, "cycles_started": 41, "iterations": 39, "checks_effects": 79,
                 "http_requests": 5000}
        for field, value in cases.items():
            with self.subTest(field=field):
                bad = summary()
                bad[field] = value
                with self.assertRaises(JourneyFailure):
                    validate_summary(bad, "ms67-load-test")

    def test_nonfinite_boolean_and_missing_measurements_fail(self):
        for value in (float("nan"), float("inf"), True, None, -1, "400"):
            with self.subTest(value=value):
                bad = summary()
                bad["p95_ms"] = value
                with self.assertRaises(JourneyFailure):
                    validate_summary(bad, "ms67-load-test")

    def test_one_idle_user_or_replica_and_missing_chat_cannot_pass(self):
        for section, name in (("vu_cycles", "10"), ("replica_requests", "chatbot_1"), ("operations", "chat")):
            with self.subTest(section=section):
                bad = summary()
                del bad[section][name]
                with self.assertRaises(JourneyFailure):
                    validate_summary(bad, "ms67-load-test")
        bad = summary()
        bad["operations"]["chat"]["requests"] = 0
        with self.assertRaises(JourneyFailure):
            validate_summary(bad, "ms67-load-test")

    def observation(self):
        images = {s: f"registry/{s}@sha256:" + "a" * 64 for s in SERVICES}
        environment = {"project": "test"}
        profile = {"cluster_uid_sha256": "b" * 64, "namespace_uid_sha256": "c" * 64,
                   "model_image": "registry/model@sha256:" + "a" * 64}
        live = {s: {"image": images[s], "ready_replicas": 2, "pod_identity_sha256": hashed(s)} for s in SERVICES}
        specs = {s: hashed({"service": s}) for s in SERVICES}
        metrics = summary()
        value = {"schema_version": "1.0", "phase": "complete", "observation_type": OBSERVATION_TYPE,
                 "status": PASS, "run_id": metrics["run_id"],
                 "k6_exit_code": 0, "bindings": {}, "images": images, "environment": environment,
                 "workload": workload(ROOT), "cluster_identity_sha256": profile["cluster_uid_sha256"],
                 "profile_namespace_uid_sha256": profile["namespace_uid_sha256"],
                 "summary": metrics, "load": validate_summary(metrics, metrics["run_id"]),
                 "live": {"before": live, "after": copy.deepcopy(live)},
                 "deployment_specs": {"before": specs, "after": copy.deepcopy(specs)},
                 "fixtures": {"account_count": 30, "final_state_verified": True,
                              "synthetic_records_retained": True, "final_state_sha256": "d" * 64,
                              "identity_sha256": "e" * 64},
                 "credentials_persisted": False, "raw_output_persisted": False, "synthetic_data_only": True,
                 "production_environment": False, "deployment_mutations": 0, "ms67_complete": False,
                 "production_ready": False, "local_processes_stopped": True}
        value.update(k6_version="k6 v2.2.0 (test)", started_at="2026-09-10T12:00:00Z",
                     load_started_at="2026-09-10T12:01:00Z", load_finished_at="2026-09-10T12:06:01Z",
                     finished_at="2026-09-10T12:07:00Z",
                     http_pod_identities={s: {"pod_uid_sha256": [hashed(s + str(i)) for i in range(2)],
                                             "pod_identity_sha256": live[s]["pod_identity_sha256"]} for s in HTTP_SERVICES})
        model = {"image": profile["model_image"], "ready_replicas": 2, "spec_sha256": "f" * 64}
        value["model"] = {"before": model, "after": dict(model)}
        return value, dict(bindings={}, images=images, environment=environment, profile=profile, root=ROOT)

    def test_signed_evidence_is_rechecked_and_rejects_drift_and_unfinished_state(self):
        value, args = self.observation()
        verify_observation(sign(value, "test-key", "test"), "test-key", **args)
        bad = sign(value, "test-key", "test")
        bad["summary"]["p95_ms"] = 0
        with self.assertRaises(JourneyFailure):
            verify_observation(bad, "test-key", **args)
        for path, altered in ((["fixtures", "final_state_verified"], False),
                              (["live", "after", "checks", "ready_replicas"], 1),
                              (["live", "after", "account", "pod_identity_sha256"], "e" * 64),
                              (["deployment_specs", "after", "chatbot"], "f" * 64),
                              (["model", "after", "ready_replicas"], 1),
                              (["load_finished_at"], "2026-09-10T12:01:01Z"),
                              (["local_processes_stopped"], False), (["ms67_complete"], True),
                              (["k6_exit_code"], 99), (["workload", "duration_seconds"], 3)):
            with self.subTest(path=path):
                current, args = self.observation()
                target = current
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = altered
                with self.assertRaises(JourneyFailure):
                    verify_observation(sign(current, "test-key", "test"), "test-key", **args)

    def test_controller_produces_verifiable_evidence_and_upload_failure_cannot_pass(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import cloudbank_sustained_load as tool
        from lightyear_data.cloudbank_image_security import save_observation, CheckpointFailure

        baseline, verification = self.observation()
        profile = verification["profile"]
        profile.update(context="gke_test_us-west1_cloudbank-ms67", namespace="cloudbank-ms67", region="us-west1",
                       namespace_uid_sha256=hashlib.sha256(b"namespace-uid").hexdigest())

        class Runtime:
            def __init__(self, **kwargs):
                self.context, self.forwards = profile["context"], {}
                self.tokens, self.credentials, self.owner = {}, {"owner": ("owner", "private-test")}, "owner"

            def environment(self):
                return verification["environment"]

            def get(self, *_):
                return {"metadata": {"uid": "namespace-uid"}}

            def ready(self):
                pass

            def authorize(self):
                pass

        class Fixture:
            def __init__(self, runtime, run):
                self.accounts, self.marker = [1, 2, 3], run

            def customer(self):
                pass

            def prepare_accounts(self):
                pass

            def state(self):
                rows = [(0, "WITHDRAW"), (0, "DEPOSIT"), (0, "DEPOSIT"), (1, "WITHDRAW"), (1, "DEPOSIT")] * 4
                return {"balances": [1000, 250, 5], "journals": [
                    {"account": i, "type": kind, "amount": 1, "id": n} for n, (i, kind) in enumerate(rows)]}

        class Forwards:
            def __init__(self, runtime):
                self.identities = baseline["http_pod_identities"]

            def open(self):
                return {}

            def close(self):
                pass

        for outcome in ("passed", "upload-failure", "client-failure"):
            fail_upload = outcome == "upload-failure"
            client_failure = outcome == "client-failure"
            class Journal:
                def __init__(self, path, uri, project, key, signer):
                    self.path, self.key, self.signer = path, key, signer
                    self.calls = 0

                def write(self, value):
                    self.calls += 1
                    if fail_upload and self.calls == 4:
                        raise CheckpointFailure("load-test-upload-unconfirmed")
                    return save_observation(self.path, value, self.key, self.signer)

            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, LIGHTYEAR_NON_PRODUCTION_ACK="I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS"))
                replacements = {
                    "evidence_key": lambda _: "test-key",
                    "bound_inputs": lambda *_: (verification["images"], profile, {}, verification["environment"]),
                    "command": lambda *_: "k6 v2.2.0 (test)", "GkeRuntime": Runtime, "Journeys": Fixture,
                    "PodForwards": Forwards, "ImageJournal": Journal,
                    "live_snapshot": lambda _: (baseline["live"]["before"], baseline["deployment_specs"]["before"]),
                    "model_snapshot": lambda *_: baseline["model"]["before"],
                    "cluster_identity": lambda *_: profile["cluster_uid_sha256"],
                    "execute_k6": lambda *_: (108, failed_transfer()) if client_failure else (0, summary()),
                }
                for name, replacement in replacements.items():
                    stack.enter_context(patch.object(tool, name, replacement))
                stack.enter_context(patch.object(tool.uuid, "uuid4", return_value=SimpleNamespace(hex="test")))
                stack.enter_context(patch.object(tool, "stamp", side_effect=[
                    "2026-09-10T12:00:00Z", "2026-09-10T12:01:00Z", "2026-09-10T12:06:01Z",
                    "2026-09-10T12:07:00Z", "2026-09-10T12:07:01Z"]))
                output = Path(directory) / "run"
                argv = ["run", "--project", "test", "--region", "us-west1", "--cluster", "cloudbank-ms67",
                        "--namespace", "cloudbank-ms67", "--signer", "test", "--evidence-bucket",
                        "gs://test-ms67-evidence/sustained-load", "--output-root", str(output)]
                for name in ("image-lock", "ms64-receipt", "ms66-receipt", "platform-profile", "journeys"):
                    argv += ["--" + name, "unused-test-input.json"]
                printed = io.StringIO()
                with contextlib.redirect_stdout(printed):
                    code = tool.main(argv)
                result = json.loads((output / "sustained-load.observation.json").read_text())
                self.assertNotIn("private-test", printed.getvalue())
                self.assertEqual(code, 0 if outcome == "passed" else 1, printed.getvalue())
                if fail_upload:
                    self.assertEqual(result["evidence_upload"], "unconfirmed")
                    with self.assertRaises(JourneyFailure):
                        verify_observation(result, "test-key", **verification)
                elif client_failure:
                    self.assertEqual(result["reason"], "load-client-transport-error")
                    self.assertEqual(result["summary"]["failure_diagnostics"], failed_transfer()["failure_diagnostics"])
                    self.assertIn("unexpected_eof", printed.getvalue())
                    with self.assertRaises(JourneyFailure):
                        verify_observation(result, "test-key", **verification)
                else:
                    verify_observation(result, "test-key", **verification)


if __name__ == "__main__":
    unittest.main()
