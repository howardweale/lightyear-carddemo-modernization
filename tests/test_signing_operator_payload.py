"""CI-only public fixtures; no key generation, signing or hardware API calls."""
import base64
from dataclasses import replace
import hashlib
import json
import struct
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import (
    BEGIN, END, PRINCIPAL, SigningBinding, SigningRefused, SigningWindow,
    _Reader, candidate_message, controller_payload,
)
from lightyear_execution.signing_operator_payload import (
    assemble_operator_reply, prepare_operator_payload,
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def string(raw):
    return struct.pack(">I", len(raw)) + raw


class SigningOperatorPayloadTests(unittest.TestCase):
    def setUp(self):
        # RFC8032 public bytes only: no private fixture or test signing operation.
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"))
        self.pem = key.public_bytes(serialization.Encoding.PEM,
                                    serialization.PublicFormat.SubjectPublicKeyInfo)
        self.allowed = (PRINCIPAL.encode() + b" " + key.public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH) + b"\n")
        self.binding = SigningBinding("a" * 40, "b" * 64, "fixture-run", "case-1", 1,
                                      "2099-01-01T00:00:00Z")
        self.window = SigningWindow(self.binding.expires_at, 100)
        self.clock = patch("lightyear_execution.external_signing.time.monotonic", return_value=1)
        self.monotonic = self.clock.start()
        self.addCleanup(self.clock.stop)

    def request(self, purpose="controller-receipt"):
        material = self.pem if purpose == "controller-receipt" else self.allowed
        if purpose == "controller-receipt":
            payload = controller_payload(canonical(dict(fixture=True, go=False)),
                                         self.binding, sha(material))
        else:
            payload = (b"tree " + b"c" * 40 + b"\nparent " + b"d" * 40
                       + b"\nauthor Fixture <fixture@example.invalid> 1 +0000"
                       + b"\ncommitter Fixture <fixture@example.invalid> 1 +0000\n\n"
                       + candidate_message(b"Disposable public fixture", self.binding, sha(material)))
        return canonical(dict(schema="external-signing-request/1", context_sha256="e" * 64,
                              binding=self.binding.document(purpose, sha(material)),
                              payload_sha256=sha(payload),
                              payload_base64=base64.b64encode(payload).decode(),
                              public_material_base64=base64.b64encode(material).decode()))

    def prepare(self, purpose="controller-receipt", request=None, **updates):
        request = self.request(purpose) if request is None else request
        options = dict(expected_request_sha256=sha(request), expected_context_sha256="e" * 64,
                       expected_purpose=purpose,
                       designated_public_material=self.pem if purpose == "controller-receipt" else self.allowed,
                       binding=self.binding, window=self.window)
        options.update(updates)
        return prepare_operator_payload(request, **options)

    def test_controller_uses_exact_retained_canonical_bytes_and_slot9c(self):
        prepared = self.prepare()
        self.assertEqual(prepared.message_to_sign, prepared.payload)
        self.assertEqual(prepared.piv_slot, "9c")
        self.assertEqual(prepared.request_sha256, sha(self.request()))

    def test_candidate_uses_git_sshsig_domain_sha512_and_slot9a(self):
        prepared = self.prepare("candidate-commit")
        expected = (b"SSHSIG" + string(b"git") + string(b"") + string(b"sha512")
                    + string(hashlib.sha512(prepared.payload).digest()))
        self.assertEqual(prepared.message_to_sign, expected)
        self.assertEqual(prepared.piv_slot, "9a")
        self.assertNotEqual(prepared.message_to_sign, prepared.payload)

    def test_controller_reply_delegates_crypto_verification_before_return(self):
        prepared = self.prepare()
        with patch("lightyear_execution.signing_operator_payload.verify_controller_reply") as verify:
            reply = assemble_operator_reply(prepared, b"\0" * 64)
        value = json.loads(reply)
        self.assertEqual(value["content_sha256"], sha(prepared.payload))
        self.assertEqual(base64.b64decode(value["signature"]["value"]), b"\0" * 64)
        verify.assert_called_once_with(
            prepared.payload, reply, public_key=self.pem, key_sha256=sha(self.pem),
            binding=self.binding, window=self.window)
        # Mock assembly is not signature proof; real public verification rejects it.
        with self.assertRaisesRegex(SigningRefused, "signature-invalid"):
            assemble_operator_reply(prepared, b"\0" * 64)

    def test_candidate_reply_armor_and_signature_blob_are_correct(self):
        prepared = self.prepare("candidate-commit")
        with patch("lightyear_execution.signing_operator_payload.verify_candidate_reply") as verify:
            reply = assemble_operator_reply(prepared, b"\0" * 64)
        headers, message = reply.split(b"\n\n", 1)
        lines = headers.split(b"\n")
        armor = [line[7:] if line.startswith(b"gpgsig ") else line[1:]
                 for line in lines[4:]]
        self.assertEqual(armor[0], BEGIN)
        self.assertEqual(armor[-1], END)
        reader = _Reader(base64.b64decode(b"".join(armor[1:-1]), validate=True))
        self.assertEqual(reader.take(6), b"SSHSIG")
        self.assertEqual(reader.uint(), 1)
        self.assertEqual(reader.string(), base64.b64decode(self.allowed.split()[2]))
        self.assertEqual(reader.string(), b"git")
        self.assertEqual(reader.string(), b"")
        self.assertEqual(reader.string(), b"sha512")
        signature = _Reader(reader.string())
        reader.end()
        self.assertEqual(signature.string(), b"ssh-ed25519")
        self.assertEqual(signature.string(), b"\0" * 64)
        signature.end()
        self.assertEqual(b"\n".join(lines[:4]) + b"\n\n" + message, prepared.payload)
        verify.assert_called_once_with(
            prepared.payload, reply, allowed_signers=self.allowed, key_sha256=sha(self.allowed),
            binding=self.binding, window=self.window)
        with self.assertRaisesRegex(SigningRefused, "signature-invalid"):
            assemble_operator_reply(prepared, b"\0" * 64)

    def test_retained_digest_context_binding_and_role_must_match(self):
        cases = [
            dict(expected_request_sha256="f" * 64),
            dict(expected_context_sha256="f" * 64),
            dict(binding=replace(self.binding, source_commit="f" * 40)),
            dict(binding=replace(self.binding, attempt=2)),
            dict(expected_purpose="candidate-commit"),
            dict(expected_purpose="unknown"),
            dict(expected_purpose=[]),
            dict(binding=None),
        ]
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(SigningRefused):
                self.prepare(**updates)

    def test_designated_public_material_cannot_come_from_packet(self):
        with self.assertRaisesRegex(SigningRefused, "role-key-substitution"):
            self.prepare(designated_public_material=self.allowed)
        with self.assertRaises(SigningRefused):
            self.prepare(designated_public_material=None)

    def test_public_packet_extra_fields_duplicates_and_noncanonical_json_refused(self):
        value = json.loads(self.request())
        value["pin"] = "not-a-real-pin"
        for request in (canonical(value), self.request() + b"\n",
                        b'{"schema":"x","schema":"x"}'):
            with self.subTest(request=request[:30]), self.assertRaises(SigningRefused):
                self.prepare(request=request)

    def test_payload_hash_and_custody_binding_checked_before_signing(self):
        for mutation in ("digest", "binding", "wrapped"):
            value = json.loads(self.request())
            payload = json.loads(base64.b64decode(value["payload_base64"]))
            if mutation == "digest":
                value["payload_sha256"] = "f" * 64
            else:
                if mutation == "binding":
                    payload["custody_signing"]["attempt"] = 2
                else:
                    payload["signature"] = {}
                raw = canonical(payload)
                value["payload_sha256"] = sha(raw)
                value["payload_base64"] = base64.b64encode(raw).decode()
            with self.subTest(mutation=mutation), self.assertRaises(SigningRefused):
                self.prepare(request=canonical(value))

    def test_candidate_existing_signature_extra_header_and_wrong_trailer_refused(self):
        for mutation in ("signature", "extra", "trailer"):
            value = json.loads(self.request("candidate-commit"))
            payload = base64.b64decode(value["payload_base64"])
            if mutation == "signature":
                payload = payload.replace(b"\n\n", b"\ngpgsig fixture\n\n", 1)
            elif mutation == "extra":
                payload = payload.replace(b"\n\n", b"\nextra header\n\n", 1)
            else:
                payload = payload.replace(b"Custody-Signing:", b"Other-Trailer:")
            value.update(payload_sha256=sha(payload),
                         payload_base64=base64.b64encode(payload).decode())
            with self.subTest(mutation=mutation), self.assertRaises(SigningRefused):
                self.prepare("candidate-commit", request=canonical(value))

    def test_noncanonical_base64_and_oversize_packets_refused(self):
        for field in ("payload_base64", "public_material_base64"):
            value = json.loads(self.request())
            value[field] += "\n"
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.prepare(request=canonical(value))
        with self.assertRaises(SigningRefused):
            self.prepare(request=b"x" * (3 * 1024 * 1024))

    def test_prepared_payload_drift_and_wrong_signature_size_refused(self):
        prepared = self.prepare()
        for changed in (replace(prepared, piv_slot="82"),
                        replace(prepared, payload=b"substituted"),
                        replace(prepared, message_to_sign=b"substituted")):
            with self.assertRaisesRegex(SigningRefused, "payload-drift"):
                assemble_operator_reply(changed, b"\0" * 64)
        for signature in (b"", b"x" * 63, b"x" * 65, "x" * 64):
            with self.subTest(size=len(signature)), self.assertRaises(SigningRefused):
                assemble_operator_reply(prepared, signature)

    def test_original_deadline_is_checked_again_when_reply_arrives(self):
        prepared = self.prepare()
        self.monotonic.return_value = 100
        with self.assertRaisesRegex(SigningRefused, "window-closed"):
            assemble_operator_reply(prepared, b"\0" * 64)
        with self.assertRaisesRegex(SigningRefused, "window-closed"):
            self.prepare()

    def test_verifier_failure_is_not_converted_to_success(self):
        prepared = self.prepare()
        with patch("lightyear_execution.signing_operator_payload.verify_controller_reply",
                   side_effect=SigningRefused("fixture-rejection")):
            with self.assertRaisesRegex(SigningRefused, "fixture-rejection"):
                assemble_operator_reply(prepared, b"\0" * 64)


if __name__ == "__main__":
    unittest.main()
