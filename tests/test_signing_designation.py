"""Public fixtures only; executed by existing CI discovery, not local hardware."""
from dataclasses import replace
import base64
import hashlib
import json
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import (
    PRINCIPAL, SigningBinding, SigningRefused, _pem, _ssh_public,
)
from lightyear_execution.signing_designation import (
    handoff_parameters, prepare_designation, verify_designation,
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def public(raw):
    return Ed25519PublicKey.from_public_bytes(raw).public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


class SigningDesignationTests(unittest.TestCase):
    def setUp(self):
        # RFC8032 public test vectors; no private material or private operations.
        self.controller = public(bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"))
        self.candidate = public(bytes.fromhex(
            "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"))
        self.options = dict(designation_id="fixture-A-1", source_commit="a" * 40,
                            work_order_sha256="b" * 64, host_label="fixture-host",
                            custodian="fixture-human", revocation_contact="fixture-human")
        self.prepared = prepare_designation(self.controller, self.candidate, **self.options)
        self.binding = SigningBinding("a" * 40, "b" * 64, "fixture-run", "case-1", 1,
                                      "2099-01-01T00:00:00Z")

    def verify(self, record=None, **updates):
        record = self.prepared.record if record is None else record
        kwargs = dict(expected_sha256=sha(record), expected_designation_id="fixture-A-1",
                      binding=self.binding, revoked_raw_key_sha256=frozenset())
        kwargs.update(updates)
        return verify_designation(record, **kwargs)

    def test_both_keys_on_A_distinct_slots_and_public_only_claims(self):
        result = self.verify()
        value = json.loads(result.record)
        self.assertEqual([(r["device_label"], r["slot"]) for r in value["roles"]],
                         [("lightyear-A", "9c"), ("lightyear-A", "9a")])
        for name in ("device_attestation", "preflight_verified",
                     "possession_verified", "native_qualified"):
            self.assertIs(value[name], False)
        self.assertEqual(value["key_b_role"], "encryption-only-off-site-backup")
        self.assertEqual(result, self.prepared)

    def test_existing_handoff_key_formats_and_digest_contract(self):
        args = handoff_parameters(
            self.prepared.record, expected_sha256=self.prepared.sha256,
            expected_designation_id="fixture-A-1", binding=self.binding,
            revoked_raw_key_sha256=frozenset())
        _pem(args["controller_public_key"], args["controller_key_sha256"])
        blob, key = _ssh_public(args["candidate_allowed_signers"], args["candidate_key_sha256"])
        value = json.loads(self.prepared.record)
        expected = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        self.assertEqual(value["roles"][1]["openssh_fingerprint"], expected)
        self.assertEqual(key.public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo),
                         self.candidate)
        self.assertEqual(args["designation_sha256"], self.prepared.sha256)
        self.assertTrue(args["candidate_allowed_signers"].startswith(PRINCIPAL.encode() + b" "))

    def test_same_key_for_both_roles_refused(self):
        with self.assertRaisesRegex(SigningRefused, "distinct-role"):
            prepare_designation(self.controller, self.controller, **self.options)

    def test_either_revoked_role_refuses_whole_pair(self):
        for role in json.loads(self.prepared.record)["roles"]:
            with self.subTest(role=role["role"]), self.assertRaisesRegex(
                    SigningRefused, "shared-device-revoked"):
                self.verify(revoked_raw_key_sha256=frozenset([role["raw_ed25519_sha256"]]))
        self.verify(revoked_raw_key_sha256=frozenset(["f" * 64]))

    def test_revocation_snapshot_is_explicit_and_validated(self):
        for invalid in (None, [], set(), frozenset(["bad"])):
            with self.subTest(invalid=invalid), self.assertRaises(SigningRefused):
                self.verify(revoked_raw_key_sha256=invalid)

    def test_expected_digest_id_source_and_work_order_are_independent(self):
        cases = [
            dict(expected_sha256="0" * 64),
            dict(expected_designation_id="another-designation"),
            dict(binding=replace(self.binding, source_commit="c" * 40)),
            dict(binding=replace(self.binding, work_order_sha256="d" * 64)),
            dict(binding=None),
        ]
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(SigningRefused):
                self.verify(**updates)

    def test_slot_policy_role_and_fingerprint_substitution_refused(self):
        mutations = [("slot", "82"), ("slot", "9d"), ("device_label", "lightyear-B"),
                     ("pin_policy", "NEVER"), ("touch_policy", "CACHED"),
                     ("role", "candidate-commit"), ("pem_sha256", "0" * 64),
                     ("raw_ed25519_sha256", "0" * 64), ("openssh_fingerprint", "SHA256:wrong")]
        for field, replacement in mutations:
            value = json.loads(self.prepared.record)
            value["roles"][0][field] = replacement
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.verify(canonical(value))

    def test_swapping_roles_and_extra_roles_refused(self):
        for transform in (lambda rows: rows[::-1], lambda rows: rows + rows[:1]):
            value = json.loads(self.prepared.record)
            value["roles"] = transform(value["roles"])
            with self.assertRaises(SigningRefused):
                self.verify(canonical(value))

    def test_unknown_secret_fields_and_false_proof_claims_refused(self):
        for field, replacement in (("pin", "not-a-real-secret"), ("serial", "fixture"),
                                   ("device_attestation", True), ("native_qualified", True),
                                   ("existing_tower_authority", "machine")):
            value = json.loads(self.prepared.record)
            value[field] = replacement
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.verify(canonical(value))

    def test_noncanonical_duplicate_or_malformed_records_refused(self):
        raw = self.prepared.record
        cases = [raw + b"\n", b'{"schema":"x","schema":"y"}',
                 b"{}", b"[]", b"x" * 17000]
        for candidate in cases:
            with self.subTest(candidate=candidate[:40]), self.assertRaises(SigningRefused):
                self.verify(candidate)

    def test_malformed_public_inputs_refused(self):
        for bad in (b"", self.controller + b"\n", self.controller.decode(),
                    b"-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----\n"):
            with self.subTest(bad=bad), self.assertRaises(SigningRefused):
                prepare_designation(bad, self.candidate, **self.options)
        for bad_label in ("", "name\nsecret", "x" * 101):
            with self.assertRaises(SigningRefused):
                prepare_designation(self.controller, self.candidate,
                                    **dict(self.options, custodian=bad_label))

    def test_missing_or_wrong_type_role_public_key_refused(self):
        for replacement in ({}, {"public_key_pem": None}, {"public_key_pem": 1}):
            value = json.loads(self.prepared.record)
            value["roles"][0] = replacement
            with self.assertRaises(SigningRefused):
                self.verify(canonical(value))


if __name__ == "__main__":
    unittest.main()
