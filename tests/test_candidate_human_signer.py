"""CI-only disposable signatures and Git history; no native/private operations."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_external_custody_signing as fixtures
from lightyear_execution.candidate_human_signer import CandidateHumanSigner
from lightyear_execution.external_signing import SigningRefused
from lightyear_execution.signing_designation import prepare_designation
from lightyear_factory.authorship import CandidateHistory, CICommitSigner
from lightyear_factory.contracts import ContractError
import test_factory_authorship as fixture_support


class CandidateHumanSignerTests(unittest.TestCase):
    def setUp(self):
        self.controller = fixtures.ExternalCustodySigningTests()
        self.candidate = fixtures.ExternalCustodySigningTests()
        for fixture in (self.controller, self.candidate):
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.revoked = frozenset()
        self.designation = prepare_designation(
            self.controller.pem, self.candidate.pem, designation_id="fixture",
            source_commit=self.candidate.binding.source_commit,
            work_order_sha256=self.candidate.binding.work_order_sha256,
            host_label="CI", custodian="Fixture", revocation_contact="Fixture")
        self.transform = lambda payload: payload
        self.reply_key = self.candidate
        self.options = dict(
            binding=self.candidate.binding, window=self.candidate.window,
            attempt_identity_sha256="a"*64, designation=self.designation.record,
            designation_sha256=self.designation.sha256, designation_id="fixture",
            current_revocations=lambda: self.revoked,
            exchange_public_reply=self.exchange)
        self.signer = CandidateHumanSigner(self.root/"handoff.sqlite", **self.options)
        self.addCleanup(self.signer.close)
        (self.root/"history").mkdir()
        _, _, _, self.history, _ = fixture_support.FactoryAuthorshipTests().setup_history(self.root/"history")
        self.history._git("add", "-A", "--", "candidate")
        self.tree = self.history._git("write-tree").decode().strip()
        self.parent = self.history.start_commit
        self.message = b"Factory candidate attempt 1\n\nFactory-Provenance: fixture\n"

    def exchange(self, request):
        payload = base64.b64decode(json.loads(request)["payload_base64"])
        return self.reply_key.commit(self.transform(payload))

    def sign(self):
        return self.signer.sign(self.history, self.tree, self.parent, self.message)

    def test_exact_public_response_once_and_independent_reverification(self):
        commit = self.sign()
        self.assertTrue(self.signer.verify(self.history, commit))
        self.assertEqual(self.tree+" "+self.parent,
                         self.history._git("show", "-s", "--format=%T %P", commit).decode().strip())
        self.assertEqual(self.signer.expected_message(self.message).strip(),
                         self.history._git("show", "-s", "--format=%B", commit).strip())
        with self.assertRaises(SigningRefused):
            self.sign()

    def test_tree_parent_and_body_substitution_consume_attempt(self):
        for old, new in ((self.tree.encode(), b"9"*40), (self.parent.encode(), b"8"*40),
                         (b"fixture", b"changed")):
            with self.subTest(old=old):
                # Each fault has a fresh disposable owner, never a resumed attempt.
                self.signer.close()
                path = self.root / ("fault-"+str(len(list(self.root.iterdir()))))
                self.signer = CandidateHumanSigner(path, **self.options)
                self.addCleanup(self.signer.close)
                self.transform = lambda payload, old=old, new=new: payload.replace(old, new)
                with self.assertRaises(SigningRefused):
                    self.sign()
                with self.assertRaises(SigningRefused):
                    self.sign()

    def test_wrong_key_refused(self):
        self.reply_key = self.controller
        with self.assertRaises(SigningRefused):
            self.sign()

    def test_revocation_of_either_slot_refused(self):
        for role in json.loads(self.designation.record)["roles"]:
            self.revoked = frozenset([role["raw_ed25519_sha256"]])
            with self.assertRaises(SigningRefused):
                CandidateHumanSigner(self.root/role["slot"], **self.options)

    def test_revocation_after_delivery_and_expiry_refused(self):
        original = self.signer._exchange
        def revoked(request):
            reply = original(request)
            self.revoked = frozenset([json.loads(self.designation.record)["roles"][0]["raw_ed25519_sha256"]])
            return reply
        self.signer._exchange = revoked
        with self.assertRaises(SigningRefused):
            self.sign()
        self.revoked = frozenset()
        with patch("lightyear_execution.external_signing.time.monotonic", return_value=50):
            with self.assertRaises(SigningRefused):
                CandidateHumanSigner(self.root/"expired", **self.options)

    def test_collision_no_resume_and_uncertain_delivery(self):
        with self.assertRaises(SigningRefused):
            CandidateHumanSigner(self.root/"handoff.sqlite", **self.options)
        self.signer._exchange = lambda request: (_ for _ in ()).throw(OSError("uncertain"))
        with self.assertRaises(OSError):
            self.sign()
        with self.assertRaises(SigningRefused):
            self.sign()

    def test_exact_type_guard_still_rejects_duck_signers_and_subclasses(self):
        class Subclass(CandidateHumanSigner):
            pass
        for signer in (object(), object.__new__(Subclass)):
            with self.assertRaises(ContractError):
                CandidateHistory(self.history.workspace, self.root/"other", "fixture-run",
                                 self.history.ledger, signer=signer)
        accepted = CandidateHistory(self.history.workspace, self.root/"accepted", "fixture-run",
                                    self.history.ledger, signer=self.signer)
        self.assertIs(accepted.signer, self.signer)
