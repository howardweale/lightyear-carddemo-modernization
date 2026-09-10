from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from lightyear_data.contracts import sign
from test_cloudbank_production_readiness import image_lock, environment, observation, KEY, HEX_A

ROOT = Path(__file__).resolve().parents[1]
previous = list(sys.path)
sys.path.insert(0, str(ROOT / "tools"))
try:
    spec = importlib.util.spec_from_file_location("ms67_closeout_test", ROOT / "tools/ms67_reconcile_closeout.py")
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
finally:
    sys.path[:] = previous


def fixtures():
    lock, env = image_lock(), environment()
    _manifest, bundle = review.ms65.render_deployment_bundle(lock, env, HEX_A)
    obs = observation(lock, env, bundle)
    receipt = sign({
        "schema_version": "1.0", "receipt_type": review.ms65.RECEIPT_TYPE, "release": "0.65.0",
        "run_id": "ms65-fixture", "signer": "unit-observer",
        "bindings": review.ms65.readiness_receipt()["bindings"],
        "source_ms64_receipt_sha256": HEX_A, "image_lock_sha256": lock["content_sha256"],
        "environment_sha256": env["content_sha256"], "deployment_bundle_sha256": bundle["content_sha256"],
        "observation_sha256": obs["content_sha256"], "cluster_identity_sha256": env["cluster_identity_sha256"],
        "rehearsal": {"status": "passed", "contract_sha256": review.ms65.CONTRACT_SHA256,
                      "scenario_count": len(review.ms65.SCENARIO_IDS), "services": list(review.ms65.SERVICES),
                      **{k: obs[k] for k in ("scenarios", "service_rollouts", "backup_restore", "cutover_states",
                                           "slo_window", "synthetic_data_only", "raw_output_persisted",
                                           "secret_values_persisted", "production_environment")}},
        "production_like_rehearsal_complete": True, "cutover_rehearsal_complete": True,
        "rollback_rehearsal_complete": True, "production_deployed": False,
        "whole_application_equivalent": False, "migration_complete": False, "production_ready": False,
    }, KEY, "unit-observer")
    context = {"bindings": {"ms64_receipt_sha256": HEX_A, "image_lock_sha256": lock["content_sha256"],
                            "platform_profile_sha256": "f" * 64},
               "profile": {"cluster_uid_sha256": env["cluster_identity_sha256"]},
               "images": {r["service"]: r["reference"] for r in lock["images"]},
               "environment": {"project": review.PROJECT, "region": "us-west1", "cluster": "cloudbank-ms67",
                               "namespace": "cloudbank-ms67", "namespace_uid_sha256": "1" * 64},
               "ms65_environment_sha256": env["content_sha256"], "journeys_sha256": "2" * 64}
    return receipt, context


def row(value, context, locator="local/receipt.json"):
    return review.inspect(value, KEY, context, locator, "d" * 64)


class CloseoutTests(unittest.TestCase):
    def test_current_ms65_reused_and_old_milestone_preserved(self):
        receipt, context = fixtures()
        current = row(receipt, context)
        self.assertEqual("contract-verified-current-context", current["verification"])
        report = review.build_report([current], {}, [], 1, 0)
        self.assertFalse(review.should_resume(report))
        changed = copy.deepcopy(context)
        changed["bindings"]["image_lock_sha256"] = "e" * 64
        old = row(receipt, changed)
        self.assertEqual("historical-milestone-pass", old["verification"])
        self.assertTrue(review.should_resume(review.build_report([old], {}, [], 1, 0)))

    def test_matching_claim_without_valid_measurements_or_signature_never_passes(self):
        receipt, context = fixtures()
        for resigned in (False, True):
            broken = copy.deepcopy(receipt)
            broken["rehearsal"]["slo_window"]["errors"] = 1
            if resigned:
                broken = sign(broken, KEY, "unit-observer")
            result = row(broken, context)
            self.assertNotEqual("contract-verified-current-context", result["verification"])
            with self.assertRaises(review.JourneyFailure):
                review.should_resume(review.build_report([result], {}, [], 1, 0))

    def test_namespace_cluster_environment_and_image_drift_prevent_current_reuse(self):
        receipt, context = fixtures()
        changes = [
            lambda c: c["profile"].update(cluster_uid_sha256="9" * 64),
            lambda c: c.update(ms65_environment_sha256="9" * 64),
            lambda c: c["images"].update(account="registry.example.test/other@sha256:" + "9" * 64),
            lambda c: c["bindings"].update(ms64_receipt_sha256="9" * 64),
        ]
        for change in changes:
            altered = copy.deepcopy(context)
            change(altered)
            self.assertEqual("historical-milestone-pass", row(receipt, altered)["verification"])

    def test_self_reported_platform_success_and_secret_values_are_not_promoted_or_copied(self):
        _receipt, context = fixtures()
        candidate = sign({"observation_type": "lightyear-cloudbank-ms67-platform-observation",
                          "status": "passed", "resilience": {"node_disruption_observed": True},
                          "rolling_deployments": [], "cutover_rollback": {},
                          "bindings": context["bindings"], "environment": context["environment"],
                          "secret_values": "NEVER_COPY_THIS_PAYLOAD"}, KEY, "unit-observer")
        result = row(candidate, context)
        self.assertEqual("matching-context-needs-contract-review", result["verification"])
        report = review.build_report([result], {}, [], 1, 0)
        self.assertFalse(report["ms67_complete"])
        self.assertFalse(report["qualification_evidence"])
        self.assertNotIn("NEVER_COPY_THIS_PAYLOAD", json.dumps(report))
        self.assertTrue(all(g["status"] == "evidence-review-required" for g in report["groups"]))

    def test_inventory_gaps_stop_automatic_execution(self):
        for gap in ("cloud-candidate-limit-reached", "cloud-listing-or-read-incomplete",
                    "local-candidate-unreadable-or-invalid"):
            report = review.build_report([], {}, [gap], 0, 0)
            with self.assertRaises(review.JourneyFailure):
                review.should_resume(report)
            self.assertTrue(all(g["status"] == "not-located-in-completed-reads" for g in report["groups"]))

    def test_summary_deduplicates_local_and_cloud_copies(self):
        receipt, context = fixtures()
        records = [row(receipt, context), row(receipt, context, review.BUCKET + "/receipt.json")]
        report = review.build_report(records, {}, [], 1, 1)
        self.assertEqual(1, report["groups"][0]["candidates"])
        self.assertEqual(2, len(report["records"]))

    def test_cloud_reader_rejects_writes_other_buckets_wildcards_and_secret_versions(self):
        rejected = [
            ("builds", "submit"), ("storage", "cp", "file", review.BUCKET + "/receipt.json"),
            ("storage", "cat", "gs://other-bucket/receipt.json"),
            ("storage", "cat", review.BUCKET + "/**.json"),
            ("secrets", "versions", "access", "latest", "--secret=cloudbank-ms67-evidence-key"),
            ("secrets", "add-iam-policy-binding", "cloudbank-ms67-evidence-key"),
        ]
        with patch.object(review, "invoke") as command:
            for args in rejected:
                with self.subTest(args=args), self.assertRaises(review.JourneyFailure):
                    review.cloud(*args)
            command.assert_not_called()

    def test_local_scan_ignores_repositories_symlinks_non_object_json_and_large_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "receipt.json").write_text("{}")
            (root / "controller").mkdir()
            (root / "controller/receipt.json").write_text("{}")
            (root / "ms67-630/.git").mkdir(parents=True)
            (root / "ms67-630/receipt.json").write_text("{}")
            (root / "ms67-closeout").mkdir()
            (root / "ms67-closeout/observation.json").write_text("{}")
            files, gaps = review.local_paths(root)
            self.assertEqual([root / "receipt.json"], files)
            self.assertEqual([], gaps)
            self.assertIsNone(review.decode(b"[]"))
            with patch.object(review, "MAX_BYTES", 1), self.assertRaises(review.JourneyFailure):
                review.read_local(root / "receipt.json")
            try:
                (root / "link.receipt.json").symlink_to(root / "receipt.json")
            except OSError:
                pass
            else:
                with self.assertRaises(review.JourneyFailure):
                    review.read_local(root / "link.receipt.json")

    def test_default_cli_is_read_only_and_keeps_keys_and_original_evidence_out_of_report(self):
        receipt, context = fixtures()
        remote_uri = review.BUCKET + "/test/receipt.json"
        def fake_cloud(*args):
            if args[:3] == ("secrets", "versions", "list"):
                return json.dumps([{"name": "projects/233419964177/secrets/cloudbank-ms67-evidence-key/versions/1",
                                    "state": "ENABLED"}])
            if args[:3] == ("secrets", "versions", "access"):
                return KEY
            if args[:2] == ("storage", "ls"):
                return remote_uri + "\n"
            if args == ("storage", "cat", remote_uri):
                return json.dumps(receipt)
            raise AssertionError("Unexpected cloud command")
        for resume in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                original = json.dumps(receipt).encode()
                path = root / "receipt.json"
                path.write_bytes(original)
                output = io.StringIO()
                retained = {"load": {"status": "verified"}, "sql": {"status": "verified"}}
                with patch.object(review, "cloud", side_effect=fake_cloud), \
                     patch.object(review, "anchors", return_value=(context, retained)), \
                     patch.object(review.subprocess, "run") as process, contextlib.redirect_stdout(output):
                    command = ["--evidence-root", str(root)] + (["--resume-ms65"] if resume else [])
                    self.assertEqual(0, review.main(command))
                    process.assert_not_called()
                self.assertEqual(original, path.read_bytes())
                reports = list((root / "ms67-closeout").glob("*/closeout-reconciliation.json"))
                self.assertEqual(1, len(reports))
                result = json.loads(reports[0].read_text())
                self.assertEqual("inventory-collected", result["status"])
                self.assertEqual(2, len(result["records"]))
                self.assertEqual(0, result["cloud_mutations"])
                self.assertEqual(1, result["groups"][0]["contract_verified_current_context"])
                self.assertNotIn(KEY, reports[0].read_text() + output.getvalue())

    def test_remote_failure_is_bounded_and_never_exposes_server_output(self):
        with patch.object(review, "cloud", side_effect=RuntimeError("SECRET_SERVER_RESPONSE")):
            result = review.read_remote(review.BUCKET + "/receipt.json")
        self.assertEqual("cloud-candidate-unreadable-or-invalid", result[-1])
        self.assertNotIn("SECRET_SERVER_RESPONSE", repr(result))

    def test_malformed_type_is_ignored_and_permission_failures_keep_bounded_reason(self):
        self.assertEqual([], review.family({"receipt_type": {"untrusted": "value"}}))
        with patch.object(review, "cloud", side_effect=review.JourneyFailure("operator-command-failed-permission-denied")):
            result = review.read_remote(review.BUCKET + "/receipt.json")
        self.assertEqual("operator-command-failed-permission-denied", result[-1])
