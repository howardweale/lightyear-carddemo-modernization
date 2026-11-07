"""Unsigned preparation fixtures: no keys generated, no signing or model calls."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.check_f8_request import RECORD, ROOT, review, public_fingerprint


class F8RequestTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads((ROOT / RECORD).read_bytes())

    def test_committed_preparation_is_valid_but_blocked(self):
        result = review(self.request)
        self.assertFalse(result["request_ready"])
        self.assertFalse(result["run_authorized"])
        self.assertEqual(5, len(result["pending"]))
        self.assertEqual(9395056, result["reserved_cost_microusd"])

    def test_missing_and_mismatched_public_fingerprint_never_ready(self):
        # RFC 8032 public test vector only; no private key or key generation.
        pem = (b"-----BEGIN PUBLIC KEY-----\n"
               b"MCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=\n"
               b"-----END PUBLIC KEY-----\n")
        digest = public_fingerprint(pem)
        self.assertFalse(review(self.request, public_pem=pem)["request_ready"])
        self.request["operator"]["tower"]["pem_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint-mismatch"):
            review(self.request, public_pem=pem)
        self.request["operator"]["tower"]["pem_sha256"] = digest
        self.assertFalse(review(self.request, public_pem=pem)["request_ready"])
        with self.assertRaisesRegex(ValueError, "tower-public-pem"):
            public_fingerprint(b"-----BEGIN PRIVATE KEY-----\n")

    def test_false_ready_claim_and_private_contents_refused(self):
        self.request["request_ready"] = True
        with self.assertRaisesRegex(ValueError, "readiness-claim"):
            review(self.request)
        self.request["request_ready"] = False
        self.request["operator"]["private_expected_values"]["values"] = ["not allowed"]
        with self.assertRaisesRegex(ValueError, "private-metadata-only"):
            review(self.request)

    def test_changed_scope_model_cap_window_and_digest_refused(self):
        mutations = [
            lambda r: r.update(g3_included=True),
            lambda r: r["roles"]["builder"].update(model="gpt-5.4"),
            lambda r: r["work_order"]["policy"].update(max_model_cost_usd=11),
            lambda r: r["window"].update(end="2026-10-31T20:00:00-07:00"),
            lambda r: r["bindings"]["workspace"].update(sha256="0" * 64),
            lambda r: r["estimate"].update(reserved_cost_microusd=1),
            lambda r: r["execution_policy"]["isolation"].update(network_mode="host"),
        ]
        for change in mutations:
            r = copy.deepcopy(self.request); change(r)
            with self.subTest(change=change), self.assertRaises(ValueError):
                review(r)

    def test_forged_final_binding_cannot_promote_draft(self):
        self.request["final_binding"] = {"publication_verified": True}
        with self.assertRaisesRegex(ValueError, "final-fields"):
            review(self.request)

    def test_validation_does_not_import_runtime_or_sign(self):
        with patch("subprocess.Popen", side_effect=AssertionError("No process for preparation")):
            self.assertFalse(review(self.request)["request_ready"])


    def test_november_request_window_remains_unsigned_and_blocked(self):
        self.request["window"] = {"start": "2026-11-17T08:00:00-08:00",
                                  "end": "2026-11-17T20:00:00-08:00"}
        result = review(self.request)
        self.assertFalse(result["request_ready"])
        self.assertFalse(result["run_authorized"])

    def test_wrong_november_offset_and_multiday_window_refuse(self):
        for window in (
            {"start": "2026-11-17T08:00:00-07:00", "end": "2026-11-17T20:00:00-07:00"},
            {"start": "2026-11-17T08:00:00-08:00", "end": "2026-11-21T20:00:00-08:00"},
            {"start": "2026-11-17T20:00:00-08:00", "end": "2026-11-17T08:00:00-08:00"}):
            self.request["window"] = window
            with self.subTest(window=window), self.assertRaisesRegex(ValueError, "window"):
                review(self.request)


    def test_selected_request_is_exact_unsigned_data_and_wrong_pin_refuses(self):
        import hashlib
        import tempfile
        from tools.check_f8_request import preparation_record, RUN_SELECTION
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            selected_path = "docs/factory/copau-run-request-2026-11/request.json"
            request = copy.deepcopy(self.request)
            request["record_path"] = selected_path
            request["window"] = {"start": "2026-11-17T08:00:00-08:00",
                                 "end": "2026-11-17T20:00:00-08:00"}
            raw = json.dumps(request).encode()
            target = root/selected_path
            target.parent.mkdir(parents=True)
            target.write_bytes(raw)
            binding = {"path": selected_path, "sha256": hashlib.sha256(raw).hexdigest()}
            (root/RUN_SELECTION).write_text(json.dumps(
                {"schema": "copau-run-request-selection/1", "request": binding}))
            path, observed, document = preparation_record(root)
            self.assertEqual((selected_path, raw, request), (path, observed, document))
            self.assertFalse(document["run_authorized"])
            target.write_bytes(raw+b" ")
            with self.assertRaisesRegex(ValueError, "record-digest"):
                preparation_record(root)

    def test_default_historical_preparation_stays_identical(self):
        from tools.check_f8_request import preparation_record
        path, raw, request = preparation_record(ROOT, RECORD)
        self.assertEqual(RECORD, path)
        self.assertEqual((ROOT/RECORD).read_bytes(), raw)
        self.assertEqual(self.request, request)

    def test_rewindowing_cannot_rename_away_required_copau_boundary(self):
        self.request["work_order"]["id"] = "different-run"
        with self.assertRaisesRegex(ValueError, "first-run-identity"):
            review(self.request)

if __name__ == "__main__":
    unittest.main()
