"""No application execution; failed preflights must never create a tag."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from tools.posttran_phase2_authorization import check_artifact_metadata, verify_signed, REQUEST, PROOF, PUBLIC_KEY, PLAN, RETURN_CODES
from tools.run_posttran_phase2 import reserve
from tests import test_decision_console_factory as fixtures


class Phase2AuthorizationTests(unittest.TestCase):
    def test_missing_unsigned_or_foreign_proof_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "phase2-signed-proof-missing"):
                verify_signed(Path(temp), {}, "a"*40, {})

    def test_missing_expired_and_short_retention_refuse(self):
        at = datetime(2026, 10, 15, tzinfo=timezone.utc)
        plan = dict(compiler_image_artifact="compiler")
        for rows in ([], [dict(name="compiler", expired=True, expires_at=(at+timedelta(days=2)).isoformat())],
                     [dict(name="compiler", expired=False, expires_at=(at+timedelta(hours=23)).isoformat())]):
            with self.assertRaises(ValueError): check_artifact_metadata(rows, plan, at)
        row = dict(name="compiler", expired=False, expires_at=(at+timedelta(days=2)).isoformat())
        self.assertEqual(row, check_artifact_metadata([row], plan, at))

    def test_proof_failure_never_contacts_tag_api(self):
        for refusal in ("phase2-signed-proof-missing", "phase2-signed-plan-binding", "invalid-signature"):
            with patch("tools.run_posttran_phase2.verify", side_effect=ValueError(refusal)), \
                    patch("tools.run_posttran_phase2.urllib.request.urlopen") as write:
                with self.assertRaisesRegex(ValueError, refusal): reserve(Path("unused"))
                write.assert_not_called()


class Phase2SignedProofTests(unittest.TestCase):
    setUp = fixtures.FactoryTests.setUp
    contract = fixtures.FactoryTests.contract
    decide = fixtures.FactoryTests.decide

    def fixture(self):
        plan = dict(content_sha256="a"*64, bound_files={".github/workflows/posttran-phase2.yml":"c"*64},
                    candidate_files={"spec/mainframe/posttran-independent/attempt-1/PosttranCandidate.java":"d"*64,
                                     "spec/mainframe/posttran-independent/attempt-1/provenance.json":"e"*64},
                    twin={"image_archive_sha256":"f"*64}, retries=0, return_code_rule=RETURN_CODES)
        raw = json.dumps(plan).encode()
        (self.root/PLAN).write_bytes(raw)
        c = self.contract("engineering-run-approval")
        c["sources"].append(dict(path=PLAN, sha256=hashlib.sha256(raw).hexdigest(), commit="b"*40))
        c["details"].update(request_seal=plan["content_sha256"], observer_sha256="c"*64,
                            class_hashes=dict(Candidate="d"*64, Provenance="e"*64, CompilerImageArchive="f"*64),
                            caps=dict(attempts=1, runs=1))
        proof, _, _ = self.decide(c)
        (self.root/REQUEST).write_text(json.dumps(c))
        (self.root/PROOF).write_text(json.dumps(proof))
        (self.root/PUBLIC_KEY).write_bytes(self.service.public_key)
        env = {"POSTTRAN_PHASE2_APPROVED_JOURNAL_HEAD":proof["journal"]["journal_head_sha256"]}
        now = datetime.fromisoformat(c["details"]["window"]["start"])
        return plan, env, now

    def test_valid_signature_and_wrong_plan_head_or_key(self):
        plan, env, now = self.fixture()
        with patch("tools.posttran_phase2_authorization.subprocess.run"), \
                patch("tools.posttran_phase2_authorization.subprocess.check_output", return_value=PROOF+"\n"):
            verify_signed(self.root, plan, "b"*40, env, now=now)
            changed = copy.deepcopy(plan); changed["content_sha256"] = "1"*64
            with self.assertRaisesRegex(ValueError, "phase2-signed-plan-binding"):
                verify_signed(self.root, changed, "b"*40, env, now=now)
            with patch("tools.posttran_phase2_authorization.subprocess.check_output", return_value="src/changed.py\n"):
                with self.assertRaisesRegex(ValueError, "phase2-signed-executable-head-changed"):
                    verify_signed(self.root, plan, "b"*40, env, now=now)
            from lightyear_mainframe.zos_evidence import Signer, initialize_key
            key = Path(self.temp.name)/"foreign.pem"; initialize_key(key)
            (self.root/PUBLIC_KEY).write_bytes(Signer(key).public)
            with self.assertRaises(ValueError): verify_signed(self.root, plan, "b"*40, env, now=now)

    def test_image_failure_never_contacts_tag_api(self):
        for refusal in ("phase2-image-artifact-missing-or-ambiguous", "phase2-image-retention-below-24-hours", "phase2-image-archive-changed"):
            with patch("tools.run_posttran_phase2.verify", return_value=({"content_sha256":"a"*64}, "b"*40)), \
                    patch.dict("os.environ", {"GITHUB_REPOSITORY":"howardweale/lightyear-carddemo-modernization"}), \
                    patch("tools.posttran_phase2_authorization.verify_image", side_effect=ValueError(refusal)), \
                    patch("tools.run_posttran_phase2.urllib.request.urlopen") as write:
                with self.assertRaisesRegex(ValueError, refusal): reserve(Path("unused"))
                write.assert_not_called()
