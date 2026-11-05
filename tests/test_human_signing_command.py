"""CI-only disposable fixtures: no token imports, real signatures or native proof."""
import base64
from contextlib import ExitStack
import os
import stat
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import (
    SigningBinding, SigningRefused, candidate_message, controller_payload,
    verify_candidate_reply, verify_controller_reply,
)
from lightyear_execution.human_signing_packet import prepare_packet
from lightyear_execution.signing_key_a import PUBLIC_KEYS, prepare_key_a_designation
from tools import human_signing as command


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def b64(raw):
    return base64.b64encode(raw).decode()


class PublicIdentityTests(unittest.TestCase):
    def test_registered_real_public_keys_hashes_and_roles(self):
        for pem, digest in PUBLIC_KEYS.values():
            self.assertEqual(sha(pem), digest)
        result = prepare_key_a_designation(source_commit="a" * 40, work_order_sha256="b" * 64)
        record = json.loads(result.record)
        self.assertEqual([(r["role"], r["slot"]) for r in record["roles"]],
                         [("controller-receipt", "9c"), ("candidate-commit", "9a")])
        self.assertEqual(record["host_label"], "DarkFactory")
        self.assertEqual(record["custodian"], "Howard")
        self.assertFalse(record["possession_verified"])
        self.assertFalse(record["native_qualified"])


class HumanSigningTests(unittest.TestCase):
    def setUp(self):
        # Synthetic CI signature material only, never either human key.
        self.keys = {r: Ed25519PrivateKey.generate() for r in PUBLIC_KEYS}
        fixtures = {}
        for role, key in self.keys.items():
            pem = key.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            fixtures[role] = (pem, sha(pem))
        self.patcher = patch.dict(PUBLIC_KEYS, fixtures)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.now = datetime.now(timezone.utc)
        self.binding = SigningBinding("a" * 40, "b" * 64, "fixture", "case-1", 1,
                                      (self.now + timedelta(minutes=5)).isoformat())
        self.designation = prepare_key_a_designation(
            source_commit=self.binding.source_commit, work_order_sha256=self.binding.work_order_sha256)
        self.rev = dict(schema="human-signing-revocations/1",
                        designation_sha256=self.designation.sha256,
                        issued_at=(self.now - timedelta(seconds=1)).isoformat(),
                        expires_at=self.binding.expires_at, revoked_raw_key_sha256=[])

    def request(self, purpose):
        material = (self.designation.controller_public_key if purpose == "controller-receipt"
                    else self.designation.candidate_allowed_signers)
        if purpose == "controller-receipt":
            payload = controller_payload(canonical(dict(kind="disposable", go=False)),
                                         self.binding, sha(material))
        else:
            payload = (b"tree " + b"3" * 40 + b"\nparent " + b"4" * 40
                       + b"\nauthor Fixture <fixture@example.invalid> 1 +0000"
                       + b"\ncommitter Fixture <fixture@example.invalid> 1 +0000\n\n"
                       + candidate_message(b"Disposable fixture", self.binding, sha(material)))
        return dict(schema="external-signing-request/1", context_sha256="c" * 64,
                    binding=self.binding.document(purpose, sha(material)),
                    payload_sha256=sha(payload), payload_base64=b64(payload),
                    public_material_base64=b64(material))

    def packet(self, purpose="controller-receipt", request=None, rev=None, **updates):
        request = canonical(self.request(purpose) if request is None else request)
        rev = canonical(self.rev if rev is None else rev)
        options = dict(request_sha256=sha(request), designation_sha256=self.designation.sha256,
                       revocations_sha256=sha(rev), purpose=purpose, source_commit="a" * 40,
                       work_order_sha256="b" * 64, context_sha256="c" * 64)
        options.update(updates)
        return prepare_packet(request, self.designation.record, rev, **options)

    def test_both_replies_roundtrip_through_existing_verifiers(self):
        for purpose in self.keys:
            packet = self.packet(purpose)
            reply = packet.reply(self.keys[purpose].sign(packet.signing_bytes()))
            options = dict(binding=packet.binding, window=packet.window,
                           key_sha256=packet.key_sha256)
            if purpose == "controller-receipt":
                self.assertEqual(verify_controller_reply(
                    packet.payload, reply, public_key=packet.material, **options), sha(packet.payload))
            else:
                object_id = verify_candidate_reply(packet.payload, reply,
                                                   allowed_signers=packet.material, **options)
                self.assertEqual(len(object_id), 40)
                self.assertIn(b"gpgsig -----BEGIN SSH SIGNATURE-----", reply)

    def test_candidate_sshsig_is_accepted_by_openssh_when_available(self):
        import shutil
        import subprocess
        if not shutil.which("ssh-keygen"):
            self.skipTest("OpenSSH unavailable on this CI runner")
        packet = self.packet("candidate-commit")
        reply = packet.reply(self.keys[packet.purpose].sign(packet.signing_bytes()))
        header = reply.split(b"\n\n", 1)[0]
        armor = header.split(b"\ngpgsig ", 1)[1].replace(b"\n ", b"\n") + b"\n"
        with tempfile.TemporaryDirectory() as temp:
            allowed, sig = Path(temp) / "allowed", Path(temp) / "signature"
            allowed.write_bytes(packet.material)
            sig.write_bytes(armor)
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I",
                 "factory@lightyear.invalid", "-n", "git", "-s", str(sig)],
                input=packet.payload, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_role_signature_invalid_and_truncated_fail(self):
        for purpose in self.keys:
            packet = self.packet(purpose)
            other = self.keys["candidate-commit" if purpose == "controller-receipt" else "controller-receipt"]
            for signature in (b"", b"x" * 64, other.sign(packet.signing_bytes())):
                with self.assertRaises(SigningRefused):
                    packet.reply(signature)

    def test_independent_digests_context_source_work_order_and_role(self):
        for updates in (
            dict(request_sha256="0" * 64), dict(designation_sha256="0" * 64),
            dict(revocations_sha256="0" * 64), dict(context_sha256="0" * 64),
            dict(source_commit="d" * 40), dict(work_order_sha256="d" * 64),
        ):
            with self.subTest(updates=updates), self.assertRaises(SigningRefused):
                self.packet(**updates)
        with self.assertRaises(SigningRefused):
            self.packet("candidate-commit", self.request("controller-receipt"))

    def test_payload_material_extra_fields_and_signature_in_request(self):
        request = self.request("controller-receipt")
        for field, value in (("payload_sha256", "0" * 64),
                             ("payload_base64", "!!!!"),
                             ("public_material_base64", b64(b"other")),
                             ("unexpected", True), ("binding", [])):
            with self.subTest(field=field), self.assertRaises(SigningRefused):
                self.packet(request=dict(request, **{field: value}))
        payload = json.loads(base64.b64decode(request["payload_base64"]))
        payload["signature"] = {}
        raw = canonical(payload)
        with self.assertRaises(SigningRefused):
            self.packet(request=dict(request, payload_base64=b64(raw), payload_sha256=sha(raw)))

    def test_revocation_of_either_key_and_stale_future_snapshot_fail(self):
        roles = json.loads(self.designation.record)["roles"]
        for role in roles:
            with self.assertRaisesRegex(SigningRefused, "revoked"):
                self.packet(rev=dict(self.rev, revoked_raw_key_sha256=[role["raw_ed25519_sha256"]]))
        for updates in (
            dict(issued_at=(self.now + timedelta(days=1)).isoformat()),
            dict(expires_at=(self.now - timedelta(seconds=1)).isoformat()),
            dict(designation_sha256="0" * 64), dict(revoked_raw_key_sha256=["bad"]),
        ):
            with self.assertRaises(SigningRefused):
                self.packet(rev=dict(self.rev, **updates))

    def test_expired_window_and_post_hardware_expiry_fail(self):
        packet = self.packet()
        with patch("lightyear_execution.external_signing.time.monotonic",
                   return_value=packet.window.monotonic_deadline + 1):
            with self.assertRaises(SigningRefused):
                packet.reply(self.keys[packet.purpose].sign(packet.signing_bytes()))
        expired = replace(packet, revocations_expires_at=(self.now - timedelta(seconds=1)).isoformat())
        with self.assertRaises(SigningRefused):
            expired.check()

    def test_controller_size_and_candidate_binding_refused_before_device(self):
        request = self.request("controller-receipt")
        body = json.loads(base64.b64decode(request["payload_base64"]))
        raw = canonical(dict(body, excess="x" * 1100))
        with self.assertRaisesRegex(SigningRefused, "size-not-qualified"):
            self.packet(request=dict(request, payload_base64=b64(raw), payload_sha256=sha(raw)))
        request = self.request("candidate-commit")
        raw = base64.b64decode(request["payload_base64"]).replace(b"Custody-Signing:", b"Other:")
        with self.assertRaises(SigningRefused):
            self.packet("candidate-commit", dict(request, payload_base64=b64(raw), payload_sha256=sha(raw)))

    def test_durable_intent_blocks_changed_context_request_and_expiry(self):
        packet = self.packet()
        with tempfile.TemporaryDirectory() as temp, ExitStack() as seams:
            root = Path(temp) / "journal"
            if os.name != "posix":
                # Windows exercises real exclusive file/directory creation.
                # Only POSIX ownership, no-follow and directory-fsync seams
                # are synthetic; Linux retains the unpatched native path.
                original_lstat = Path.lstat

                def owned_lstat(path, *args, **kwargs):
                    result = original_lstat(path, *args, **kwargs)
                    if path == root:
                        fields = list(result)
                        fields[0], fields[4] = stat.S_IFDIR | 0o700, 42
                        return os.stat_result(fields)
                    return result

                seams.enter_context(patch.object(Path, "lstat", owned_lstat))
                seams.enter_context(patch.object(command.os, "getuid", return_value=42, create=True))
                seams.enter_context(patch.object(command.os, "O_NOFOLLOW", 0, create=True))
                seams.enter_context(patch.object(command, "sync_dir"))
            attempt = command.reserve_attempt(root, packet)
            intent = attempt / "intent.json"
            original = intent.read_bytes()
            record = json.loads(original)
            self.assertEqual(record["state"], "CONSUMED_BEFORE_HARDWARE")
            self.assertEqual(record["request_sha256"], packet.request_sha256)
            self.assertEqual(record["context_sha256"], packet.context_sha256)
            changed = replace(packet, context_sha256="d" * 64, request_sha256="e" * 64,
                              binding=replace(packet.binding, expires_at="2099-01-01T00:00:00Z"))
            with self.assertRaises(FileExistsError):
                command.reserve_attempt(root, changed)
            with self.assertRaises(FileExistsError):
                command.write_new(intent, b"replacement")
            self.assertEqual(intent.read_bytes(), original)

    def test_policy_and_public_key_mismatch_refused(self):
        role = "controller-receipt"
        metadata = SimpleNamespace(
            key_type=SimpleNamespace(name="ED25519"), generated=True,
            pin_policy=SimpleNamespace(name="ONCE"), touch_policy=SimpleNamespace(name="ALWAYS"),
            public_key=self.keys[role].public_key())
        command.require_slot(metadata, role)
        for field, value in (("generated", False), ("pin_policy", SimpleNamespace(name="NEVER")),
                             ("touch_policy", SimpleNamespace(name="CACHED")),
                             ("public_key", self.keys["candidate-commit"].public_key())):
            changed = SimpleNamespace(**vars(metadata))
            setattr(changed, field, value)
            with self.assertRaises(SigningRefused):
                command.require_slot(changed, role)

    def test_non_mac_cli_refuses_before_packet_or_hardware_access(self):
        with patch.object(command.sys, "platform", "linux"), patch.object(command, "read_public") as read:
            result = command.main([
                "sign", "--source-commit", "a" * 40, "--work-order-sha256", "b" * 64,
                "--output", "unused", "--request", "unused", "--request-sha256", "c" * 64,
                "--designation", "unused", "--designation-sha256", "d" * 64,
                "--revocations", "unused", "--revocations-sha256", "e" * 64,
                "--context-sha256", "f" * 64, "--role", "controller-envelope"])
            self.assertEqual(result, 1)
            read.assert_not_called()

    def test_worker_cleanup_terminates_then_kills_and_refuses_survivor(self):
        process = Mock()
        process.is_alive.side_effect = [True, True, False]
        command.stop_worker(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        process.close.assert_called_once()
        process = Mock()
        process.is_alive.return_value = True
        with self.assertRaisesRegex(SigningRefused, "cleanup-unconfirmed"):
            command.stop_worker(process)


    def test_mock_hardware_one_pin_one_sign_exact_slot_and_failures(self):
        import sys
        import time
        from unittest.mock import mock_open
        metadata = {}
        for purpose, slot in (("controller-receipt", 0x9c), ("candidate-commit", 0x9a)):
            metadata[slot] = SimpleNamespace(
                key_type=SimpleNamespace(name="ED25519"), generated=True,
                pin_policy=SimpleNamespace(name="ONCE"),
                touch_policy=SimpleNamespace(name="ALWAYS"),
                public_key=self.keys[purpose].public_key())
        piv = Mock()
        piv.get_slot_metadata.side_effect = metadata.__getitem__
        piv.sign.return_value = b"s" * 64
        connection = Mock()
        device = Mock()
        device.open_connection.return_value.__enter__ = Mock(return_value=connection)
        device.open_connection.return_value.__exit__ = Mock(return_value=False)
        devices = Mock(return_value=[(device, SimpleNamespace(version=(5, 8, 0)))])
        modules = {
            "ykman.device": SimpleNamespace(list_all_devices=devices),
            "yubikit.core.smartcard": SimpleNamespace(SmartCardConnection=object),
            "yubikit.piv": SimpleNamespace(
                PivSession=Mock(return_value=piv),
                SLOT=SimpleNamespace(SIGNATURE=0x9c, AUTHENTICATION=0x9a),
                KEY_TYPE=SimpleNamespace(ED25519="ED25519")),
        }
        with patch.dict(sys.modules, modules), patch.object(command, "version", return_value="5.9.2"), \
                patch.object(command.logging, "disable"), patch("builtins.open", mock_open()), \
                patch.object(command.getpass, "getpass", return_value="mock-not-a-PIN") as pin:
            for purpose, slot in (("controller-receipt", 0x9c), ("candidate-commit", 0x9a)):
                piv.reset_mock()
                pin.reset_mock()
                pipe = Mock()
                command.hardware_worker(pipe, purpose, b"fixture", self.binding.expires_at,
                                        time.monotonic() + 60)
                pin.assert_called_once()
                piv.verify_pin.assert_called_once_with("mock-not-a-PIN")
                piv.sign.assert_called_once_with(slot, "ED25519", b"fixture", None)
                pipe.send_bytes.assert_called_once_with(b"s" * 64)
            piv.reset_mock()
            pin.reset_mock()
            piv.verify_pin.side_effect = ValueError("mock wrong PIN")
            pipe = Mock()
            command.hardware_worker(pipe, "controller-receipt", b"fixture",
                                    self.binding.expires_at, time.monotonic() + 60)
            piv.verify_pin.assert_called_once()
            piv.sign.assert_not_called()
            pipe.send_bytes.assert_called_once_with(b"")
            piv.reset_mock()
            pin.reset_mock()
            metadata[0x9a].touch_policy.name = "CACHED"
            command.hardware_worker(Mock(), "controller-receipt", b"fixture",
                                    self.binding.expires_at, time.monotonic() + 60)
            pin.assert_not_called()
            piv.verify_pin.assert_not_called()
            piv.sign.assert_not_called()

if __name__ == "__main__":
    unittest.main()
