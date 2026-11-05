"""CI-only public fixtures. No private keys, generation, signing or device calls."""
import base64
from dataclasses import replace
import hashlib
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import (
    PRINCIPAL, SigningBinding, SigningRefused, SigningWindow,
    candidate_message, controller_payload,
)
from lightyear_execution.signing_operator_payload import prepare_operator_payload
from lightyear_execution.signing_operator_preflight import (
    MAX_REPORT, check_operator_preflight,
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class OperatorPreflightTests(unittest.TestCase):
    def setUp(self):
        # Two RFC8032 public keys only; no fixture secret material.
        self.controller = Ed25519PublicKey.from_public_bytes(bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"))
        self.candidate = Ed25519PublicKey.from_public_bytes(bytes.fromhex(
            "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"))
        self.pem = self.controller.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.allowed = self.ssh(self.candidate)
        self.binding = SigningBinding("a" * 40, "b" * 64, "fixture", "case-1", 1,
                                      "2099-01-01T00:00:00Z")
        self.window = SigningWindow(self.binding.expires_at, 100)
        self.clock = patch("lightyear_execution.external_signing.time.monotonic", return_value=1)
        self.monotonic = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.prepared = self.prepare("controller-receipt")

    def ssh(self, key):
        return (PRINCIPAL.encode() + b" " + key.public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH) + b"\n")

    def prepare(self, purpose):
        material = self.pem if purpose == "controller-receipt" else self.allowed
        if purpose == "controller-receipt":
            payload = controller_payload(canonical(dict(fixture=True, go=False)),
                                         self.binding, sha(material))
        else:
            payload = (b"tree " + b"c" * 40 + b"\nparent " + b"d" * 40
                       + b"\nauthor Fixture <fixture@example.invalid> 1 +0000"
                       + b"\ncommitter Fixture <fixture@example.invalid> 1 +0000\n\n"
                       + candidate_message(b"Public fixture", self.binding, sha(material)))
        request = canonical(dict(
            schema="external-signing-request/1", context_sha256="e" * 64,
            binding=self.binding.document(purpose, sha(material)),
            payload_sha256=sha(payload), payload_base64=base64.b64encode(payload).decode(),
            public_material_base64=base64.b64encode(material).decode()))
        return prepare_operator_payload(
            request, expected_request_sha256=sha(request), expected_context_sha256="e" * 64,
            expected_purpose=purpose, designated_public_material=material,
            binding=self.binding, window=self.window)

    def report(self):
        roles = []
        for purpose, slot, label, material in (
                ("controller-receipt", "9c", "SIGNATURE", self.pem),
                ("candidate-commit", "9a", "AUTHENTICATION", self.allowed)):
            roles.append(dict(
                purpose=purpose, device_label="lightyear-A", slot=slot,
                piv_info_slot="Slot " + slot.upper() + " (" + label + ")",
                algorithm="ED25519", origin="GENERATED", pin_policy="ONCE",
                touch_policy="ALWAYS", certificate="absent",
                public_material_sha256=sha(material)))
        return dict(
            schema="public-signing-operator-preflight/1",
            request_sha256=self.prepared.request_sha256,
            context_sha256=self.prepared.context_sha256, designation_sha256="f" * 64,
            purpose=self.prepared.purpose, device_label="lightyear-A",
            connected_devices=["lightyear-A"], key_b_state="unplugged-no-configuration-writes",
            owner_state="attended-isolated", operation_state="unattempted", roles=roles,
            preserved_inventory_sha256="1" * 64,
            canary=dict(
                plaintext_sha256="2" * 64, ciphertext_sha256="3" * 64,
                created_with_all_keys_unplugged=True, digest_committed_before_encryption=True,
                digest_recorded_on_paper=True, digest_sent_to_operator_record=True,
                encrypted_to_both_existing_recipients=True,
                plaintext_deleted_before_insertion=True, b_decryption_sha256="2" * 64,
                a_before_decryption_sha256="2" * 64, a_after_decryption_sha256="2" * 64))

    def check(self, report=None, raw=None, **changes):
        raw = canonical(self.report() if report is None else report) if raw is None else raw
        options = dict(
            expected_observation_sha256=sha(raw), expected_designation_sha256="f" * 64,
            controller_public_key=self.pem, candidate_allowed_signers=self.allowed,
            expected_canary_plaintext_sha256="2" * 64, expected_canary_ciphertext_sha256="3" * 64,
            expected_preserved_inventory_sha256="1" * 64)
        options.update(changes)
        return check_operator_preflight(self.prepared, raw, **options)

    def test_exact_report_for_both_roles_is_only_public_match(self):
        for purpose, slot in (("controller-receipt", "9c"), ("candidate-commit", "9a")):
            self.prepared = self.prepare(purpose)
            result = self.check()
            self.assertEqual(result.request_sha256, self.prepared.request_sha256)
            self.assertEqual(result.piv_slot, slot)
            self.assertEqual(result.device_label, "lightyear-A")
            self.assertFalse(hasattr(result, "signature"))
            self.assertFalse(hasattr(result, "authorized"))

    def test_independent_retained_anchors_cannot_be_replaced_by_report(self):
        for field in ("expected_observation_sha256", "expected_designation_sha256",
                      "expected_canary_plaintext_sha256", "expected_canary_ciphertext_sha256",
                      "expected_preserved_inventory_sha256"):
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.check(**{field: "9" * 64})

    def test_report_bound_to_exact_request_context_and_role(self):
        for field, value in (("request_sha256", "9" * 64), ("context_sha256", "9" * 64),
                             ("purpose", "candidate-commit"), ("schema", "unknown")):
            report = self.report()
            report[field] = value
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.check(report)

    def test_wrong_device_extra_device_unknown_owner_or_any_attempt_refused(self):
        for field, values in (
                ("device_label", ["lightyear-B", None]),
                ("connected_devices", [[], ["lightyear-A", "lightyear-B"], ["lightyear-A"] * 2]),
                ("key_b_state", ["unknown", "configuration-written"]),
                ("owner_state", ["unknown", "unattended"]),
                ("operation_state", ["attempted", "ambiguous", "failed", "retry", None])):
            for value in values:
                report = self.report()
                report[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(SigningRefused):
                    self.check(report)

    def test_role_swap_policies_certificates_and_origin_refuse(self):
        for field, value in (
                ("slot", "82"), ("slot", "9a"), ("device_label", "lightyear-B"),
                ("piv_info_slot", "Slot 9C"), ("algorithm", "RSA2048"),
                ("origin", "IMPORTED"), ("pin_policy", "ALWAYS"), ("pin_policy", None),
                ("touch_policy", "CACHED"), ("certificate", "present"),
                ("public_material_sha256", "9" * 64)):
            report = self.report()
            report["roles"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(SigningRefused):
                self.check(report)

    def test_exact_two_roles_no_duplicates_omissions_extras_or_malformed_types(self):
        for roles in ([], self.report()["roles"][:1], self.report()["roles"] * 2,
                      [self.report()["roles"][0]] * 2, {}, [None, None]):
            report = self.report()
            report["roles"] = roles
            with self.subTest(roles=roles), self.assertRaises(SigningRefused):
                self.check(report)
        report = self.report()
        report["roles"][0]["purpose"] = []
        with self.assertRaises(SigningRefused):
            self.check(report)

    def test_different_encodings_of_same_key_are_not_distinct_roles(self):
        with self.assertRaisesRegex(SigningRefused, "distinct-role-keys"):
            self.check(candidate_allowed_signers=self.ssh(self.controller))

    def test_request_key_must_match_authenticated_designation(self):
        replacement = self.candidate.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        with self.assertRaisesRegex(SigningRefused, "request-designation"):
            self.check(controller_public_key=replacement,
                       candidate_allowed_signers=self.ssh(self.controller))
        with self.assertRaises(SigningRefused):
            self.check(controller_public_key=None)

    def test_every_canary_prerequisite_must_be_literal_true(self):
        baseline = self.report()
        fields = [key for key, value in baseline["canary"].items() if value is True]
        for field in fields:
            for value in (False, None, 1, "true"):
                report = self.report()
                report["canary"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(SigningRefused):
                    self.check(report)

    def test_all_three_decryptions_must_match_prior_committed_digest(self):
        for field in ("plaintext_sha256", "b_decryption_sha256",
                      "a_before_decryption_sha256", "a_after_decryption_sha256",
                      "ciphertext_sha256"):
            report = self.report()
            report["canary"][field] = "9" * 64
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.check(report)

    def test_schema_rejects_extra_or_missing_data_at_every_level(self):
        for path in ((), ("roles", 0), ("canary",)):
            for mutation in ("extra", "missing"):
                report = self.report()
                target = report
                for part in path:
                    target = target[part]
                if mutation == "extra":
                    target["unexpected"] = "public-fixture"
                else:
                    del target[next(iter(target))]
                with self.subTest(path=path, mutation=mutation), self.assertRaises(SigningRefused):
                    self.check(report)

    def test_noncanonical_duplicate_oversize_and_nonbytes_reports_refuse(self):
        for raw in (canonical(self.report()) + b"\n", b'{"a":1,"a":2}',
                    b"x" * (MAX_REPORT + 1), b"[]"):
            with self.subTest(raw=raw[:20]), self.assertRaises(SigningRefused):
                self.check(raw=raw)
        with self.assertRaises(SigningRefused):
            check_operator_preflight(
                self.prepared, "not bytes", expected_observation_sha256="a" * 64,
                expected_designation_sha256="f" * 64, controller_public_key=self.pem,
                candidate_allowed_signers=self.allowed, expected_canary_plaintext_sha256="2" * 64,
                expected_canary_ciphertext_sha256="3" * 64,
                expected_preserved_inventory_sha256="1" * 64)

    def test_forged_prepared_payload_cannot_bypass_existing_validation(self):
        self.prepared = replace(self.prepared, piv_slot="82")
        with self.assertRaisesRegex(SigningRefused, "payload-drift"):
            self.check()

    def test_original_deadline_checked_before_and_after_report_validation(self):
        self.monotonic.return_value = 100
        with self.assertRaisesRegex(SigningRefused, "window-closed"):
            self.check()
        self.monotonic.side_effect = [1, 1, 100]
        with self.assertRaisesRegex(SigningRefused, "window-closed"):
            self.check()


if __name__ == "__main__":
    unittest.main()
