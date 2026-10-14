import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.check_posttran_phase1_retained import AUTHORIZATION, PINNED, REPORT, ROOT, verify


class RetainedPhase1Tests(unittest.TestCase):
    def test_verifies_original_success_without_execution(self):
        with patch("subprocess.run", side_effect=AssertionError("no execution")), \
                patch("subprocess.Popen", side_effect=AssertionError("no execution")):
            result = verify()
        self.assertTrue(result["verified"])
        self.assertEqual(result["evidence_run"], 38304981119)
        self.assertEqual(result["new_candidate_executions"], 0)
        self.assertFalse(result["phase2_authorized"])

    def fixture(self, root):
        paths = set(PINNED) | set(json.loads((ROOT / AUTHORIZATION).read_text())["bound_file_sha256"])
        for path in paths:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())
        return paths

    def test_every_bound_input_refuses_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.fixture(root)
            for path in paths:
                with self.subTest(path=path):
                    original = (root / path).read_bytes()
                    (root / path).write_bytes(original + b" ")
                    with self.assertRaisesRegex(ValueError, "retained-binding-changed"):
                        verify(root)
                    (root / path).write_bytes(original)

    def test_historical_failure_cannot_replace_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            failed = root / "docs/factory/posttran-attempt1-phase1-2026-10-12.json"
            (root / REPORT).write_bytes(failed.read_bytes())
            with self.assertRaisesRegex(ValueError, "retained-binding-changed"):
                verify(root)

    def test_missing_report_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing-or-linked-evidence"):
                verify(Path(directory))
