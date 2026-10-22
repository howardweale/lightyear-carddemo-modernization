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


if __name__ == "__main__":
    unittest.main()
