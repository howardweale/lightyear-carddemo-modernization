"""Disposable signatures made only when the CI test suite executes."""
import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from lightyear_control_tower.decisions import canonical, verify_envelope
from lightyear_execution.external_signing import (
    BEGIN, END, MAX_PAYLOAD, PRINCIPAL, SigningBinding, SigningRefused, SigningWindow,
    candidate_message, controller_payload, verify_candidate_reply, verify_controller_reply,
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def string(value):
    return struct.pack(">I", len(value)) + value


class ExternalCustodySigningTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.pem = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.ssh = self.key.public_key().public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        self.allowed = PRINCIPAL.encode() + b" " + self.ssh + b"\n"
        self.binding = SigningBinding("1" * 40, "2" * 64, "fixture-run", "case-01", 1,
                                      "2099-01-01T00:00:00-08:00")
        self.window = SigningWindow(self.binding.expires_at, 50)
        self.clock = patch("lightyear_execution.external_signing.time.monotonic", return_value=1)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def payload(self, **updates):
        return controller_payload(canonical(dict(record_type="disposable-test", go=False, **updates)),
                                  self.binding, digest(self.pem))

    def envelope(self, payload, key=None, pem=None):
        key, pem = key or self.key, pem or self.pem
        return canonical(dict(json.loads(payload), content_sha256=digest(payload),
                              signature=dict(algorithm="Ed25519", key_id=digest(pem),
                                             value=base64.b64encode(key.sign(payload)).decode())))

    def verify(self, payload, reply, **kwargs):
        params = dict(public_key=self.pem, key_sha256=digest(self.pem),
                      binding=self.binding, window=self.window)
        params.update(kwargs)
        return verify_controller_reply(payload, reply, **params)

    def unsigned_commit(self, **kwargs):
        binding = kwargs.get("binding", self.binding)
        key_id = kwargs.get("key_sha256", digest(self.allowed))
        return (b"tree " + b"3" * 40 + b"\nparent " + b"4" * 40
                + b"\nauthor Lightyear Factory <factory@lightyear.invalid> 1700000000 +0000"
                + b"\ncommitter Lightyear Factory <factory@lightyear.invalid> 1700000000 +0000\n\n"
                + candidate_message(b"Factory candidate attempt 1\n\nFactory-Provenance: fixture\n",
                                    binding, key_id))

    def armor(self, payload, *, namespace=b"git", reserved=b"", algorithm=b"sha512",
              version=1, key=None, outer_extra=b"", inner_extra=b"", signature_type=b"ssh-ed25519"):
        key = key or self.key
        public = key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                               serialization.PublicFormat.OpenSSH)
        public_blob = base64.b64decode(public.split()[1])
        signed = (b"SSHSIG" + string(namespace) + string(reserved) + string(algorithm)
                  + string(hashlib.new(algorithm.decode(), payload).digest()))
        blob = (b"SSHSIG" + struct.pack(">I", version) + string(public_blob) + string(namespace)
                + string(reserved) + string(algorithm)
                + string(string(signature_type) + string(key.sign(signed)) + inner_extra) + outer_extra)
        encoded = base64.b64encode(blob)
        return BEGIN + b"\n" + b"\n".join(encoded[n:n + 70] for n in range(0, len(encoded), 70)) + b"\n" + END + b"\n"

    def commit(self, payload, armor=None):
        armor = armor or self.armor(payload)
        headers, message = payload.split(b"\n\n", 1)
        return headers + b"\ngpgsig " + armor.rstrip(b"\n").replace(b"\n", b"\n ") + b"\n\n" + message

    def verify_commit(self, payload, signed, **kwargs):
        params = dict(allowed_signers=self.allowed, key_sha256=digest(self.allowed),
                      binding=self.binding, window=self.window)
        params.update(kwargs)
        return verify_candidate_reply(payload, signed, **params)

    def test_controller_envelope_uses_existing_verifier_format(self):
        payload = self.payload()
        reply = self.envelope(payload)
        self.assertTrue(verify_envelope(json.loads(reply), self.pem))
        self.assertEqual(digest(payload), self.verify(payload, reply))
        # A valid signature never rewrites disposable proof or its negative verdict.
        self.assertFalse(json.loads(reply)["go"])
        self.assertEqual("disposable-test", json.loads(reply)["record_type"])

    def test_validly_signed_changed_body_cannot_replace_controller_output(self):
        payload = self.payload()
        altered = canonical(dict(json.loads(payload), go=True))
        with self.assertRaises(SigningRefused):
            self.verify(payload, self.envelope(altered))

    def test_controller_context_replay_refused(self):
        payload = self.payload()
        for field, value in dict(source_commit="a" * 40, work_order_sha256="b" * 64,
                                 run_id="other-run", case_id="case-02", attempt=2).items():
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.verify(payload, self.envelope(payload), binding=replace(self.binding, **{field: value}))

    def test_json_bool_or_float_cannot_alias_bound_integer_attempt(self):
        for attempt in (True, 1.0):
            document = json.loads(self.payload())
            document["custody_signing"]["attempt"] = attempt
            payload = canonical(document)
            with self.subTest(attempt=attempt), self.assertRaises(SigningRefused):
                self.verify(payload, self.envelope(payload))

    def test_reply_cannot_select_its_own_key(self):
        payload = self.payload()
        other = Ed25519PrivateKey.generate()
        pem = other.public_key().public_bytes(serialization.Encoding.PEM,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
        with self.assertRaises(SigningRefused):
            self.verify(payload, self.envelope(payload, other, pem))
        with self.assertRaises(SigningRefused):
            self.verify(payload, self.envelope(payload), public_key=pem)

    def test_duplicate_noncanonical_extra_and_bad_signature_reply_refused(self):
        payload = self.payload()
        reply = self.envelope(payload)
        value = json.loads(reply)
        corrupt = json.loads(reply)
        corrupt["signature"]["value"] = base64.b64encode(b"x" * 64).decode()
        extra_signature = json.loads(reply)
        extra_signature["signature"]["unreviewed"] = True
        malformed = [reply + b"\n", reply[:-1] + b',"go":false}', canonical(dict(value, extra=1)),
                     canonical(corrupt), canonical(extra_signature), b"[]", b'{"x":NaN}', b"\xff"]
        for bad in malformed:
            with self.subTest(bad=bad[:30]), self.assertRaises(SigningRefused):
                self.verify(payload, bad)

    def test_public_pem_rejects_private_wrong_type_and_trailing_data(self):
        private = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
        rsa = generate_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        for raw in (private, rsa, self.pem + b"\n", self.pem + self.pem):
            with self.subTest(kind=raw[:30]), self.assertRaises(SigningRefused):
                self.verify(self.payload(), self.envelope(self.payload()), public_key=raw, key_sha256=digest(raw))

    def test_request_bounds_and_already_signed_body(self):
        for raw in (b"x" * (MAX_PAYLOAD + 1), b'{"x":1,"x":2}', b'{"signature":{}}',
                    b'{"content_sha256":"x"}', b'{"custody_signing":{}}', b' {"x":1}'):
            with self.subTest(raw=raw[:30]), self.assertRaises(SigningRefused):
                controller_payload(raw, self.binding, digest(self.pem))

    def test_original_wall_and_monotonic_deadlines_both_enforced(self):
        before = datetime(2098, 1, 1, tzinfo=timezone.utc)
        at = datetime(2099, 1, 1, 8, tzinfo=timezone.utc)
        self.window.check(self.binding, wall=before, monotonic=49)
        for wall, monotonic in ((at, 1), (before, 50), (before, float("nan")),
                                (before, float("inf")), (before.replace(tzinfo=None), 1)):
            with self.subTest(wall=wall, monotonic=monotonic), self.assertRaises(SigningRefused):
                self.window.check(self.binding, wall=wall, monotonic=monotonic)
        with self.assertRaises(SigningRefused):
            self.window.check(replace(self.binding, expires_at="2099-01-02T00:00:00-08:00"))

    def test_late_verification_completion_is_not_success(self):
        payload = self.payload()
        reply = self.envelope(payload)
        commit = self.unsigned_commit()
        signed = self.commit(commit)
        for operation in (lambda: self.verify(payload, reply), lambda: self.verify_commit(commit, signed)):
            with patch("lightyear_execution.external_signing.time.monotonic", side_effect=[1, 50]):
                with self.assertRaises(SigningRefused):
                    operation()

    def test_binding_rejects_bool_attempt_naive_timestamp_and_invalid_ids(self):
        for change in (dict(attempt=True), dict(attempt=0), dict(attempt=1.5), dict(case_id="../case"),
                       dict(source_commit="x" * 40), dict(expires_at="2099-01-01T00:00:00"),
                       dict(expires_at="2099-02-30T00:00:00Z")):
            with self.subTest(change=change), self.assertRaises(SigningRefused):
                replace(self.binding, **change)

    def test_candidate_real_ed25519_signatures_both_hash_algorithms(self):
        payload = self.unsigned_commit()
        for algorithm in (b"sha256", b"sha512"):
            signed = self.commit(payload, self.armor(payload, algorithm=algorithm))
            expected = hashlib.sha1(b"commit " + str(len(signed)).encode() + b"\0" + signed).hexdigest()
            self.assertEqual(expected, self.verify_commit(payload, signed))

    def test_candidate_valid_signature_cannot_change_commit_bytes(self):
        payload = self.unsigned_commit()
        for changed in (payload.replace(b"3" * 40, b"5" * 40), payload.replace(b"4" * 40, b"6" * 40),
                        payload.replace(b"1700000000", b"1700000001"), payload.replace(b"fixture\n", b"edited\n")):
            with self.subTest(changed=changed[:60]), self.assertRaises(SigningRefused):
                self.verify_commit(payload, self.commit(changed))

    def test_candidate_context_and_role_replay_refused(self):
        payload = self.unsigned_commit()
        signed = self.commit(payload)
        for field, value in dict(source_commit="a" * 40, work_order_sha256="b" * 64,
                                 run_id="other", case_id="case-02", attempt=2).items():
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.verify_commit(payload, signed, binding=replace(self.binding, **{field: value}))
        for options in (dict(namespace=b"file"), dict(namespace=b""), dict(reserved=b"future"),
                        dict(version=2), dict(key=Ed25519PrivateKey.generate()),
                        dict(signature_type=b"ssh-rsa"), dict(outer_extra=b"x"), dict(inner_extra=b"x")):
            with self.subTest(options=list(options)), self.assertRaises(SigningRefused):
                self.verify_commit(payload, self.commit(payload, self.armor(payload, **options)))

    def test_candidate_single_designated_signer_only(self):
        payload = self.unsigned_commit()
        for allowed in (self.allowed * 2, self.allowed.replace(PRINCIPAL.encode(), b"*"),
                        self.allowed.replace(b" ssh-ed25519", b' namespaces="git" ssh-ed25519'),
                        self.allowed + b"comment", self.allowed.rstrip(b"\n")):
            with self.subTest(allowed=allowed[:40]), self.assertRaises(SigningRefused):
                self.verify_commit(payload, self.commit(payload), allowed_signers=allowed,
                                   key_sha256=digest(allowed))

    def test_candidate_malformed_armor_duplicate_signature_and_extra_headers(self):
        payload = self.unsigned_commit()
        signed = self.commit(payload)
        for bad in (signed.replace(BEGIN, b"wrong"), signed.replace(END, b"wrong"),
                    signed.replace(b"gpgsig ", b"gpgsig wrong\ngpgsig "),
                    signed.replace(b"\nauthor ", b"\nencoding utf-8\nauthor "),
                    signed.replace(b"\n", b"\r\n"), signed + b"x", b"x" * (MAX_PAYLOAD + 1)):
            with self.subTest(bad=bad[:40]), self.assertRaises(SigningRefused):
                self.verify_commit(payload, bad)
        for armor in (BEGIN + b"\n!!!!\n" + END + b"\n",
                      BEGIN + b"\n" + base64.b64encode(b"SSHSIG\0\0\0\1\xff\xff\xff\xff") + b"\n" + END + b"\n"):
            with self.assertRaises(SigningRefused):
                self.verify_commit(payload, self.commit(payload, armor))

    def test_no_unbound_or_duplicate_candidate_trailer(self):
        with self.assertRaises(SigningRefused):
            candidate_message(b"Custody-Signing: forged", self.binding, digest(self.allowed))
        payload = self.unsigned_commit().replace(b"Custody-Signing:", b"Other-Trailer:")
        with self.assertRaises(SigningRefused):
            self.verify_commit(payload, self.commit(payload))

    def test_openssh_cli_interoperability_in_ci(self):
        # Independent implementation, not just test encoder/verifier agreement.
        # No skip: required CI runners must have OpenSSH available.
        ssh_keygen = shutil.which("ssh-keygen")
        self.assertIsNotNone(ssh_keygen, "OpenSSH required for interoperability regression")
        payload = self.unsigned_commit()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / "allowed-signers"
            allowed.write_bytes(self.allowed)
            signature = root / "public-commit.sig"
            signature.write_bytes(self.armor(payload))
            subprocess.run([ssh_keygen, "-Y", "verify", "-f", str(allowed), "-I", PRINCIPAL,
                            "-n", "git", "-s", str(signature)], input=payload,
                           check=True, capture_output=True, timeout=20)
            signed = self.commit(payload, signature.read_bytes())
            self.assertEqual(40, len(self.verify_commit(payload, signed)))
