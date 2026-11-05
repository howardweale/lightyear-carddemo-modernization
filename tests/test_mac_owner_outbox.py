"""CI-only public outbox fixtures; no Tower, private operations or native proof."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import SigningBinding, SigningRefused, SigningWindow
from lightyear_execution.mac_owner_outbox import ACK_SCHEMA, MacOwnerPublicOutbox


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class MacOwnerOutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "public-outbox.sqlite"
        self.binding = SigningBinding("1" * 40, "2" * 64, "fixture-run", "case-1", 1,
                                      "2099-01-01T00:00:00Z")
        self.window = SigningWindow(self.binding.expires_at, 50)
        self.clock = patch("lightyear_execution.external_signing.time.monotonic", return_value=1)
        self.monotonic = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.receipt = canonical(dict(kind="disposable-CI", native_proof=False))
        self.options = dict(binding=self.binding, window=self.window,
                            attempt_identity_sha256="a" * 64, tower_context_sha256="b" * 64,
                            public_receipt=self.receipt)

    def outbox(self, **changes):
        box = MacOwnerPublicOutbox(self.path, **dict(self.options, **changes))
        self.addCleanup(box.close)
        return box

    def row(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT payload, state, ack FROM delivery WHERE id=1").fetchone()

    def ack(self, delivery, **changes):
        value = dict(
            schema=ACK_SCHEMA, attempt_identity_sha256="a" * 64,
            tower_context_sha256="b" * 64, delivery_sha256=sha(delivery),
            receipt_sha256=sha(self.receipt), journal_entry_sha256="c" * 64)
        value.update(changes)
        return canonical(value)

    def finish(self, box, ack, **changes):
        parameters = dict(
            authenticated_ack_sha256=sha(ack),
            authenticated_journal_entry_sha256="c" * 64)
        parameters.update(changes)
        return box.acknowledge_once(ack, **parameters)

    def test_seal_persists_exact_payload_and_release_intent_before_return(self):
        box = self.outbox()
        sealed, state, ack = self.row()
        self.assertEqual((state, ack), ("sealed", None))
        delivery = box.release_once()
        self.assertEqual(delivery, sealed)
        self.assertEqual(self.row(), (delivery, "released", None))
        value = json.loads(delivery)
        self.assertEqual(value["receipt_sha256"], sha(self.receipt))
        self.assertEqual(value["binding"]["expires_at"], self.binding.expires_at)

    def test_matching_ack_is_bound_and_retained_without_changing_payload(self):
        box = self.outbox()
        delivery = box.release_once()
        ack = self.ack(delivery)
        self.assertEqual(self.finish(box, ack), "c" * 64)
        self.assertEqual(self.row(), (delivery, "acknowledged", ack))
        with self.assertRaises(SigningRefused):
            self.finish(box, ack)

    def test_duplicate_release_fail_stops_owner(self):
        box = self.outbox()
        delivery = box.release_once()
        with self.assertRaises(SigningRefused):
            box.release_once()
        with self.assertRaises(SigningRefused):
            self.finish(box, self.ack(delivery))
        self.assertEqual(self.row()[1], "released")

    def test_no_reopen_even_before_first_release(self):
        box = self.outbox()
        box.close()
        with self.assertRaisesRegex(SigningRefused, "existing-no-resume"):
            self.outbox()
        self.assertEqual(self.row()[1], "sealed")

    def test_no_reopen_or_resend_after_delivery_uncertainty(self):
        box = self.outbox()
        box.release_once()
        box.close()
        with self.assertRaisesRegex(SigningRefused, "existing-no-resume"):
            self.outbox()
        self.assertEqual(self.row()[1], "released")

    def test_ack_before_release_fail_stops_owner(self):
        box = self.outbox()
        with self.assertRaises(SigningRefused):
            self.finish(box, b"{}")
        with self.assertRaises(SigningRefused):
            box.release_once()
        self.assertEqual(self.row()[1], "sealed")

    def test_every_ack_binding_field_is_required(self):
        for field in ("attempt_identity_sha256", "tower_context_sha256",
                      "delivery_sha256", "receipt_sha256", "journal_entry_sha256", "schema"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "outbox.sqlite"
                with MacOwnerPublicOutbox(path, **self.options) as box:
                    value = json.loads(self.ack(box.release_once()))
                    value[field] = "wrong" if field == "schema" else "d" * 64
                    ack = canonical(value)
                    with self.assertRaises(SigningRefused):
                        self.finish(box, ack)
                    with self.assertRaises(SigningRefused):
                        self.finish(box, self.ack(b"fixture"))
                    with closing(sqlite3.connect(path)) as db:
                        self.assertEqual(db.execute("SELECT state FROM delivery").fetchone()[0],
                                         "ack-consumed")

    def test_authenticated_ack_digest_cannot_be_taken_from_response(self):
        box = self.outbox()
        ack = self.ack(box.release_once())
        with self.assertRaisesRegex(SigningRefused, "unauthenticated-ack"):
            self.finish(box, ack, authenticated_ack_sha256="e" * 64)
        self.assertEqual(self.row()[1], "ack-consumed")

    def test_duplicate_unknown_and_noncanonical_ack_fields_refused(self):
        for mutation in ("duplicate", "extra", "newline"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                with MacOwnerPublicOutbox(Path(directory) / "outbox.sqlite", **self.options) as box:
                    raw = self.ack(box.release_once())
                    if mutation == "duplicate":
                        raw = raw[:-1] + b',"schema":"mac-owner-public-ack/1"}'
                    elif mutation == "extra":
                        raw = canonical(dict(json.loads(raw), ignored="no"))
                    else:
                        raw += b"\n"
                    with self.assertRaises(SigningRefused):
                        self.finish(box, raw)

    def test_original_monotonic_deadline_cannot_rebase_for_handoff(self):
        box = self.outbox()
        self.monotonic.return_value = 50
        with self.assertRaisesRegex(SigningRefused, "window-closed"):
            box.release_once()
        self.monotonic.return_value = 1
        with self.assertRaises(SigningRefused):
            box.release_once()

    def test_ack_expiry_preserves_uncertain_delivery_without_retry(self):
        box = self.outbox()
        ack = self.ack(box.release_once())
        self.monotonic.return_value = 51
        with self.assertRaises(SigningRefused):
            self.finish(box, ack)
        self.assertEqual(self.row()[1], "released")

    def test_wall_deadline_is_also_required(self):
        binding = replace(self.binding, expires_at="2000-01-01T00:00:00Z")
        with self.assertRaises(SigningRefused):
            self.outbox(binding=binding, window=SigningWindow(binding.expires_at, 50))
        self.assertFalse(self.path.exists())

    def test_tampered_journal_content_cannot_be_released(self):
        box = self.outbox()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE delivery SET payload=?", (b"changed",))
            db.commit()
        with self.assertRaisesRegex(SigningRefused, "state-or-content"):
            box.release_once()

    def test_forked_owner_cannot_release(self):
        box = self.outbox()
        with patch("lightyear_execution.mac_owner_outbox.os.getpid", return_value=os.getpid() + 1):
            with self.assertRaisesRegex(SigningRefused, "owner-unavailable"):
                box.release_once()
        with self.assertRaises(SigningRefused):
            box.release_once()

    def test_existing_sidecar_is_not_recovered(self):
        Path(str(self.path) + "-journal").write_bytes(b"fixture")
        with self.assertRaisesRegex(SigningRefused, "existing-sidecar"):
            self.outbox()
        self.assertFalse(self.path.exists())

    def test_invalid_receipt_cannot_occupy_outbox(self):
        with self.assertRaises(SigningRefused):
            self.outbox(public_receipt=b'{"x":1,"x":2}')
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
