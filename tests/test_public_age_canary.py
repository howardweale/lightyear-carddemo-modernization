"""Pure public vectors and injected failures; no identity, subprocess, or device access."""
import io
import json
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from tools import public_age_canary as canary


class Pipe:
    def __init__(self, raw):
        self.stream = io.BytesIO(raw)

    def read(self, size, end):
        return self.stream.read(size)


class CanaryVectors(unittest.TestCase):
    def setUp(self):
        self.spec = Path(canary.FIXTURE).parent
        self.vector = json.loads((self.spec/"PUBLIC-EXPECTED.json").read_bytes())
        self.raw = bytes.fromhex(self.vector["stream_hex"])
        self.cases = canary.rows()
        self.end = time.monotonic()+30
        self.proj = dict(count=2, plaintext_cap=canary.CAP, bindings_sha256=self.vector["binding_sha256"],
                         input_sha256=self.vector["input_sha256"], age_sha256=canary.TAG, operation_id=canary.TAG)

    def decode(self, raw):
        return canary.rx.decode(canary.CheckedPipe(Pipe(raw), self.raw), self.proj, canary.MANIFEST, self.end)

    def test_frame_hashes_and_full_stream(self):
        self.assertEqual(canary.plaintext(self.cases,self.vector["example_binding"]), self.raw)
        self.assertEqual(canary.writer.sha(self.raw),self.vector["stream_sha256"])
        self.assertEqual(canary.input_commitment(self.cases),self.vector["input_sha256"])
        self.assertEqual([canary.writer.sha(row) for row in self.decode(self.raw)],self.vector["case_sha256"])
        stream = io.BytesIO(self.raw)
        for sha in self.vector["prefix_and_body_sha256"]:
            prefix = stream.read(8)
            body = stream.read(int.from_bytes(prefix,"big"))
            self.assertEqual(canary.writer.sha(prefix+body), sha)
        self.assertEqual(stream.read(), b"")

    def test_altered_truncated_and_trailing(self):
        for bad in (self.raw[:-1], self.raw+b"!", self.raw[:-1]+b"!"):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                self.decode(bad)

    def test_different_valid_stream(self):
        cases = [dict(row) for row in self.cases]
        cases[0] = dict(cases[0], outputs=dict(cases[0]["outputs"], stdout="00"))
        other = canary.plaintext(cases,self.vector["example_binding"])
        with self.assertRaises(ValueError):
            self.decode(other)

    def test_wrong_input_commitment_and_expiry(self):
        self.proj["input_sha256"] = "0"*64
        with self.assertRaises(ValueError):
            self.decode(self.raw)
        self.proj["input_sha256"] = self.vector["input_sha256"]
        self.end = time.monotonic()-1
        with self.assertRaises(ValueError):
            self.decode(self.raw)

    def test_join_and_physical_removal_are_required(self):
        for outcome in ("pass", "wrong-recipient", "exit-after-eof", "wrong-cipher", "still-mounted",
                        "copy-unconfirmed", "handle-open", "second-claim"):
            with self.subTest(outcome=outcome):
                broker = Mock()
                broker.claim.return_value = canary.TAG
                if outcome == "second-claim":
                    broker.claim.side_effect = ValueError()
                broker.open_cipher.return_value = nullcontext(123)
                session = Mock()
                session.pipe.return_value = nullcontext(Pipe(b"" if outcome == "wrong-recipient" else self.raw))
                session.join_success.return_value = outcome != "exit-after-eof"
                broker.decrypt.return_value = nullcontext(session)
                broker.removal_receipt.return_value = dict(claim_sha256=canary.TAG, operation_id=canary.TAG,
                    decryptor_exited=True, group_absent=True, handles_closed=outcome!="handle-open",
                    usb_mount_absent=outcome!="still-mounted", howard_removed_usb=True,
                    howard_no_identity_copy=outcome!="copy-unconfirmed", codex_absent=True)
                with patch.object(canary.rx,"completion",return_value={"ciphertext":{}}), \
                     patch.object(canary.rx,"verify_cipher",side_effect=ValueError() if outcome=="wrong-cipher" else None):
                    if outcome == "pass":
                        self.assertEqual(len(canary.roundtrip(broker,self.proj,self.raw,self.end)),64)
                    else:
                        with self.assertRaises(ValueError):
                            canary.roundtrip(broker,self.proj,self.raw,self.end)
                if outcome in ("wrong-recipient","exit-after-eof","wrong-cipher","second-claim"):
                    broker.removal_receipt.assert_not_called()

    def test_failed_durable_write_cannot_return_commitment(self):
        for operation in ("file-or-directory-sync", "completion-readback", "exclusive-create", "write"):
            store, sink = Mock(), Mock()
            if operation == "file-or-directory-sync":
                store.seal_ciphertext.side_effect = OSError()
            elif operation == "completion-readback":
                store.seal_ciphertext.return_value = {"sha256":"1"*64,"bytes":128}
                store.complete.side_effect = OSError()
            elif operation == "exclusive-create":
                store.start.side_effect = FileExistsError()
            else:
                sink.write.side_effect = OSError()
            with self.subTest(operation=operation), self.assertRaises(OSError):
                canary.writer.write_answers(iter(self.cases),2,self.vector["example_binding"],store,
                    lambda fd,deadline:sink,lambda:True,lambda:canary.TAG,self.end)
            if operation != "completion-readback":
                store.complete.assert_not_called()
            store.close.assert_called_once()

    def test_existing_leaf_refuses_without_following_or_truncating(self):
        import os
        store = canary.writer.PrivateStore.__new__(canary.writer.PrivateStore)
        store.fd, store.dir = None, 901
        with patch.object(os,"O_NOFOLLOW",0x400000,create=True), \
             patch.object(os,"open",side_effect=FileExistsError()) as opened:
            with self.assertRaises(FileExistsError):
                store.start()
            name, flags, mode = opened.call_args.args
            self.assertEqual((name,mode,opened.call_args.kwargs),("answers.age",0o600,{"dir_fd":901}))
            for flag in (os.O_NOFOLLOW, os.O_EXCL, os.O_CREAT):
                self.assertTrue(flags & flag)
            self.assertFalse(flags & os.O_TRUNC)

    def test_source_interruption_after_first_case_aborts(self):
        def interrupted():
            yield self.cases[0]
            raise InterruptedError()
        store, sink = Mock(), Mock()
        with self.assertRaises(InterruptedError):
            canary.writer.write_answers(interrupted(),2,self.vector["example_binding"],store,
                lambda fd,end:sink,lambda:True,lambda:canary.TAG,self.end)
        sink.abort.assert_called_once()
        store.complete.assert_not_called()
        store.seal_ciphertext.assert_not_called()

    def test_both_fsync_failures_propagate(self):
        import os
        obj = canary.writer.PrivateStore.__new__(canary.writer.PrivateStore)
        obj.fd, obj.dir = 902, 903
        cipher = b"age-encryption.org/v1\n" + b"x"*80
        for failure in (obj.fd,obj.dir):
            seen = []
            def sync(fd):
                seen.append(fd)
                if fd == failure:
                    raise OSError()
            with patch.object(os,"fsync",side_effect=sync), patch.object(os,"lseek"), \
                 patch.object(os,"fstat",return_value=Mock(st_size=len(cipher))), \
                 patch.object(os,"read",side_effect=[cipher,b""]), self.assertRaises(OSError):
                obj.seal_ciphertext()
            self.assertEqual(seen, [obj.fd] if failure==obj.fd else [obj.fd,obj.dir])

    def test_fixture_substitution_refused(self):
        with patch.object(canary.h1,"read",return_value=b"[]"), self.assertRaises(ValueError):
            canary.rows()


class RefusalAndMountTests(unittest.TestCase):
    def test_cli_emits_one_closed_code_and_no_detail(self):
        from contextlib import redirect_stderr
        for args, error, code in [
            (["tool","--sensitive-example"], None, "canary-arguments"),
            (["tool","--control","private-example","--approval-sha256","x"],
             canary.Refused("canary-usb-mount"), "canary-usb-mount"),
            (["tool","--control","private-example","--approval-sha256","x"],
             OSError("private-example"), "canary-fault"),
            (["tool","--control","private-example","--approval-sha256","x"],
             KeyboardInterrupt(), "canary-interrupted"),
        ]:
            output = io.StringIO()
            with self.subTest(code=code), patch.object(canary.sys, "argv", args), \
                 patch.object(canary,"execute",side_effect=error), redirect_stderr(output):
                self.assertEqual(canary.main(), 2)
            self.assertEqual(output.getvalue(), code+"\n")

    def test_untrusted_exceptions_never_supply_output_text(self):
        for error in (ValueError("canary-usb-mount"), canary.Refused("private-value"),
                      canary.Refused([]), canary.Refused("canary-custody","private-value")):
            self.assertEqual(canary.refusal(error), "canary-fault")

    def test_valid_mountinfo(self):
        line = "17 1 8:16 / /example ro,nosuid,nodev,noexec - ext4 /dev/example ro"
        canary.mount_record([line],17,"8:16")

    def test_wrong_or_ambiguous_mountinfo(self):
        line = "17 1 8:16 / /example ro,nosuid,nodev,noexec - ext4 /dev/example ro"
        for lines in ([], [line.replace("17 ", "12 ",1)], [line.replace("8:16","8:17")],
                      [line.replace("ro,nosuid","rw,nosuid")], [line.replace(",noexec","")],
                      [line, line.replace("17 ","18 ",1)], [line.replace(" / /"," /sub /")],
                      [line.replace("ext4","9p")], ["broken"]):
            with self.subTest(lines=lines), self.assertRaisesRegex(canary.Refused,"canary-usb-mount"):
                canary.mount_record(lines,17,"8:16")

    def test_invalid_terminal_pair(self):
        for pair in (("", "8:16"), ("0","8:16"), ("1","x"), ("١","8:1")):
            with self.subTest(pair=pair), self.assertRaisesRegex(canary.Refused,"canary-usb-mount"):
                canary.parse_usb_pair(*pair)
