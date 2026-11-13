"""Disposable CI signatures must fail the real offline verification trust key.

Only the retained PUBLIC verification key is present. No Tower connection,
private authority, signing service, nonce, or model is used.
"""
import base64
import copy
import hashlib
import os
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_control_tower.decisions import canonical, digest, ZERO
from lightyear_control_tower.verification import verify_journal, DecisionVerificationError

PUBLIC_VERIFICATION_KEY = b"-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAN7nhVi3JYLepJDsdKo+6VF/VfEl26Wf8D1k5o2jlLFI=\n-----END PUBLIC KEY-----\n"
PUBLIC_VERIFICATION_SHA256 = "658ba69010237ebc143a1e6d2c519f7d2adb1843993bc171c1d015e7b86b0c8a"

@unittest.skipUnless(os.environ.get("GITHUB_ACTIONS") == "true", "disposable CI signatures only")
class DisposableTrustRefusal(unittest.TestCase):
    def setUp(self):
        self.assertEqual(hashlib.sha256(PUBLIC_VERIFICATION_KEY).hexdigest(), PUBLIC_VERIFICATION_SHA256)
        # Fresh for every test/run; never serialized, written, uploaded, or reused.
        self.key = Ed25519PrivateKey.generate()
        self.addCleanup(lambda: setattr(self, "key", None))
        self.public = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.assertNotEqual(self.public, PUBLIC_VERIFICATION_KEY)
        body = {"record_type": "tower-journal-export/1", "scope": "factory",
                "events": [], "journal_head_sha256": ZERO, "disposable_fixture": True,
                "admission": False, "approval": False, "qualification_evidence": False}
        self.export = {**body, "content_sha256": digest(body),
                       "signature": {"algorithm": "Ed25519",
                         "key_id": hashlib.sha256(self.public).hexdigest(),
                         "value": base64.b64encode(self.key.sign(canonical(body))).decode()}}
        # Establish a valid disposable signature before asserting trust refusal.
        self.assertEqual(verify_journal(self.export, self.public, scope="factory", expected_head=ZERO), [])

    def test_real_verifier_rejects_disposable_signature_under_factory_public_trust(self):
        with self.assertRaisesRegex(DecisionVerificationError, "^invalid-export-signature$"):
            verify_journal(self.export, PUBLIC_VERIFICATION_KEY, scope="factory", expected_head=ZERO)

    def test_claiming_factory_key_id_cannot_make_disposable_signature_trusted(self):
        forged = copy.deepcopy(self.export)
        forged["signature"]["key_id"] = PUBLIC_VERIFICATION_SHA256
        with self.assertRaisesRegex(DecisionVerificationError, "^invalid-export-signature$"):
            verify_journal(forged, PUBLIC_VERIFICATION_KEY, scope="factory", expected_head=ZERO)
