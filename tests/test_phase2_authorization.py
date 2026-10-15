"""No application execution; failed preflights must never create a tag."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.posttran_phase2_authorization import check_artifact_metadata, verify_signed, REQUEST, PROOF, PUBLIC_KEY, PLAN, RETURN_CODES
from tools.run_posttran_phase2 import reserve
from tests import test_decision_console_factory as fixtures


class RetainedPlanInspectionTests(unittest.TestCase):
    def fixture(self, root, *, bad_hash=False):
        from tools.check_posttran_retained_plan import PLAN, ORIGINAL, REQUEST
        from tools.prepare_posttran_phase2 import digest
        root = Path(root)
        raw = b"reviewed program\n"
        (root / "program.txt").write_bytes(raw)
        expected = hashlib.sha256(raw).hexdigest()
        common = dict(candidate_files={"program.txt": expected}, twin={}, scenarios=[],
                      scenario_count=0, compared_outputs=[], normalization_rules=[], preparation_run=123)
        original = dict(common, bound_files={"program.txt": expected})
        original["content_sha256"] = digest(original)
        (root / ORIGINAL).parent.mkdir(parents=True)
        (root / ORIGINAL).write_text(json.dumps(original))
        plan = dict(common, bound_files={"program.txt": expected},
                    original_plan_sha256=hashlib.sha256((root / ORIGINAL).read_bytes()).hexdigest())
        if bad_hash:
            plan["bound_files"]["other.txt"] = "0" * 64
            (root / "other.txt").write_text("not the bound bytes")
        plan["content_sha256"] = digest(plan)
        (root / PLAN).write_text(json.dumps(plan))
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-qm", "Retained plan"], cwd=root, check=True)
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        request = dict(details=dict(executable_commit=revision, request_seal=plan["content_sha256"]),
                       sources=[dict(path=PLAN, commit=revision,
                                     sha256=hashlib.sha256((root / PLAN).read_bytes()).hexdigest())])
        (root / REQUEST).write_text(json.dumps(request))
        return plan, expected

    def test_retained_inspection_reports_drift_but_execution_still_refuses(self):
        from tools.check_posttran_retained_plan import inspect, PLAN
        from tools.run_posttran_phase2 import bound_plan
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, expected = self.fixture(root)
            report = inspect(root)
            self.assertTrue(report["current_checkout_matches_plan"])
            self.assertFalse(report["execution_authorized"])
            (root / "program.txt").write_text("changed after review")
            report = inspect(root)
            self.assertEqual(["program.txt"], report["changed_bound_files"])
            self.assertFalse(report["current_checkout_matches_plan"])
            self.assertFalse(report["execution_authorized"])
            with patch("tools.run_posttran_phase2.ROOT", root), \
                    patch("tools.run_posttran_phase2.PLAN", root / PLAN), \
                    patch("tools.run_posttran_phase2.CANDIDATE", root / "program.txt"), \
                    patch("tools.run_posttran_phase2.EXPECTED", expected):
                with self.assertRaisesRegex(ValueError, "phase2-bound-file-changed"):
                    bound_plan()

    def test_retained_content_and_request_tampering_are_refused(self):
        from tools.check_posttran_retained_plan import inspect, PLAN, REQUEST
        for change in ("plan", "source_hash", "revision", "snapshot_hash"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.fixture(root, bad_hash=change == "snapshot_hash")
                if change == "plan":
                    (root / PLAN).write_text("{}")
                elif change in ("source_hash", "revision"):
                    request = json.loads((root / REQUEST).read_bytes())
                    if change == "source_hash": request["sources"][0]["sha256"] = "0" * 64
                    else: request["details"]["executable_commit"] = "HEAD"
                    (root / REQUEST).write_text(json.dumps(request))
                with self.assertRaisesRegex(ValueError, "phase2-retained-"):
                    inspect(root)


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
