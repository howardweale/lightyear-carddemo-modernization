"""CI-only disposable handoff fault regressions; no production keys or execution."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import test_external_custody_signing as fixtures
from lightyear_control_tower.decisions import canonical
from lightyear_execution import signing_handoff as handoff
from lightyear_execution.external_signing import SigningRefused


class PublicSigningHandoffTests(unittest.TestCase):
    def setUp(self):
        self.controller = fixtures.ExternalCustodySigningTests()
        self.controller.setUp()
        self.addCleanup(self.controller.doCleanups)
        self.candidate = fixtures.ExternalCustodySigningTests()
        self.candidate.setUp()
        self.addCleanup(self.candidate.doCleanups)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "attempt.sqlite"
        self.options = dict(
            binding=self.controller.binding, window=self.controller.window,
            attempt_identity_sha256="a" * 64, designation_sha256="b" * 64,
            controller_public_key=self.controller.pem,
            controller_key_sha256=fixtures.digest(self.controller.pem),
            candidate_allowed_signers=self.candidate.allowed,
            candidate_key_sha256=fixtures.digest(self.candidate.allowed))
        self.store = handoff.PublicSigningHandoff(self.path, **self.options)
        self.addCleanup(self.store.close)

    def export(self):
        request = self.store.request_controller(canonical(dict(go=False, record_type="disposable-test")))
        payload = base64.b64decode(json.loads(request)["payload_base64"], validate=True)
        return request, payload, self.controller.envelope(payload)

    def row(self):
        # SQLite's transaction context does not close the connection.
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(
                "SELECT request, payload, status, reply FROM handoffs WHERE purpose='controller-receipt'").fetchone()

    def test_controller_is_retained_before_export_and_returned_once(self):
        request, payload, reply = self.export()
        self.assertEqual((request, payload, "EXPORTED", None), self.row())
        result = self.store.accept_controller(reply)
        self.assertEqual(fixtures.digest(payload), result.verified_identity)
        self.assertEqual(fixtures.digest(reply), result.reply_sha256)
        self.assertFalse(json.loads(result.reply)["go"])
        self.assertEqual("SIGNATURE_VERIFIED", self.row()[2])
        with self.assertRaises(SigningRefused):
            self.store.accept_controller(reply)

    def test_separate_candidate_key_verifies_exact_commit(self):
        headers = self.candidate.unsigned_commit().split(b"\n\n", 1)[0]
        original = headers + b"\n\nFactory candidate attempt 1\n\nFactory-Provenance: fixture\n"
        request = self.store.request_candidate(original)
        payload = base64.b64decode(json.loads(request)["payload_base64"])
        self.assertTrue(payload.startswith(original.rstrip(b"\n")))
        signed = self.candidate.commit(payload)
        result = self.store.accept_candidate(signed)
        identity = hashlib.sha1(b"commit " + str(len(signed)).encode() + b"\0" + signed).hexdigest()
        self.assertEqual(identity, result.verified_identity)

    def test_same_key_cannot_fill_both_roles(self):
        options = dict(self.options, candidate_allowed_signers=self.controller.allowed,
                       candidate_key_sha256=fixtures.digest(self.controller.allowed))
        with self.assertRaisesRegex(SigningRefused, "distinct-role"):
            handoff.PublicSigningHandoff(Path(self.tmp.name) / "other", **options)

    def test_duplicate_export_is_fail_stop(self):
        _, _, reply = self.export()
        with self.assertRaises(SigningRefused):
            self.export()
        with self.assertRaises(SigningRefused):
            self.store.accept_controller(reply)

    def test_existing_database_cannot_resume_even_after_close(self):
        self.export()
        self.store.close()
        with self.assertRaisesRegex(SigningRefused, "no-resume"):
            handoff.PublicSigningHandoff(self.path, **self.options)

    def test_invalid_reply_burns_slot_before_verification(self):
        _, payload, reply = self.export()
        changed = canonical(dict(json.loads(payload), go=True))
        with self.assertRaises(SigningRefused):
            self.store.accept_controller(self.controller.envelope(changed))
        self.assertEqual("CONSUMED", self.row()[2])
        with self.assertRaises(SigningRefused):
            self.store.accept_controller(reply)

    def test_expired_reply_is_consumed_without_verification(self):
        _, _, reply = self.export()
        with patch("lightyear_execution.external_signing.time.monotonic", return_value=50), \
                patch.object(handoff, "verify_controller_reply") as verifier:
            with self.assertRaises(SigningRefused):
                self.store.accept_controller(reply)
            verifier.assert_not_called()
        self.assertEqual("CONSUMED", self.row()[2])

    def test_oversized_reply_burns_slot(self):
        self.export()
        with self.assertRaises(SigningRefused):
            self.store.accept_controller(b"x" * (handoff.MAX_PAYLOAD + handoff.MAX_SIGNATURE + 1))
        self.assertEqual("CONSUMED", self.row()[2])

    def test_uncertain_export_commit_never_returns_request(self):
        commit = self.store._commit
        def uncertain():
            commit()
            raise OSError("injected post-commit uncertainty")
        with patch.object(self.store, "_commit", side_effect=uncertain):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual("EXPORTED", self.row()[2])
        with self.assertRaises(SigningRefused):
            self.export()

    def test_uncertain_consume_commit_never_calls_verifier(self):
        _, _, reply = self.export()
        commit = self.store._commit
        def uncertain():
            commit()
            raise OSError("injected post-commit uncertainty")
        with patch.object(self.store, "_commit", side_effect=uncertain), \
                patch.object(handoff, "verify_controller_reply") as verifier:
            with self.assertRaises(OSError):
                self.store.accept_controller(reply)
            verifier.assert_not_called()
        self.assertEqual("CONSUMED", self.row()[2])

    def test_expiry_after_verified_commit_cannot_deliver_success(self):
        _, _, reply = self.export()
        commit, commits = self.store._commit, []
        def counted():
            commit()
            commits.append(True)
        with patch.object(self.store, "_commit", side_effect=counted), \
                patch("lightyear_execution.external_signing.time.monotonic",
                      side_effect=lambda: 50 if len(commits) == 2 else 1):
            with self.assertRaises(SigningRefused):
                self.store.accept_controller(reply)
        self.assertEqual("SIGNATURE_VERIFIED", self.row()[2])
        with self.assertRaises(SigningRefused):
            self.store.accept_controller(reply)

    def test_payload_tamper_is_refused_before_verifier(self):
        _, _, reply = self.export()
        self.store._db.execute("UPDATE handoffs SET payload=?", (b"changed",))
        with patch.object(handoff, "verify_controller_reply") as verifier:
            with self.assertRaises(SigningRefused):
                self.store.accept_controller(reply)
            verifier.assert_not_called()

    def test_context_tamper_is_refused(self):
        self.store._db.execute("UPDATE context SET body=?", (b"changed",))
        with self.assertRaisesRegex(SigningRefused, "context-drift"):
            self.export()

    def test_state_change_during_verification_is_refused(self):
        _, _, reply = self.export()
        verify = handoff.verify_controller_reply
        def changed(*args, **kwargs):
            identity = verify(*args, **kwargs)
            self.store._db.execute("UPDATE handoffs SET status='EXPORTED'")
            return identity
        with patch.object(handoff, "verify_controller_reply", side_effect=changed):
            with self.assertRaisesRegex(SigningRefused, "state-drift"):
                self.store.accept_controller(reply)

    def test_two_concurrent_replies_have_only_one_success(self):
        _, _, reply = self.export()
        def accept():
            try:
                return self.store.accept_controller(reply)
            except SigningRefused:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: accept(), range(2)))
        self.assertEqual(1, sum(result is not None for result in results))

    def test_changed_process_owner_is_refused(self):
        with patch.object(handoff.os, "getpid", return_value=os.getpid() + 1):
            with self.assertRaises(SigningRefused):
                self.export()

    def test_hardlinked_database_is_refused(self):
        os.link(self.path, Path(self.tmp.name) / "alias.sqlite")
        with self.assertRaises(SigningRefused):
            self.export()

    def test_preexisting_sidecar_is_refused_without_creating_database(self):
        other = Path(self.tmp.name) / "other.sqlite"
        Path(str(other) + "-journal").write_bytes(b"occupied")
        with self.assertRaisesRegex(SigningRefused, "sidecar"):
            handoff.PublicSigningHandoff(other, **self.options)
        self.assertFalse(other.exists())

    def test_already_bound_candidate_cannot_be_exported_again(self):
        with self.assertRaises(SigningRefused):
            self.store.request_candidate(self.candidate.unsigned_commit())
