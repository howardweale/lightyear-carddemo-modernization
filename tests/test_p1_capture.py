"""CI-only synthetic subprocess tests; no real repository scan or secret."""
from contextlib import redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from tools.ci.p1_capture import CaptureRefused, capture


class P1CaptureTests(unittest.TestCase):
    def test_stdout_stderr_and_traceback_stay_captured(self):
        marker = "SYNTHETIC-SECRET-ONLY"
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, GITHUB_ACTIONS="true"):
            with redirect_stdout(out), redirect_stderr(err):
                code, raw, errors = capture([sys.executable, "-c",
                    "print('SYNTHETIC-SECRET-ONLY'); raise ValueError('SYNTHETIC-SECRET-ONLY')"], temp)
        self.assertEqual(code, 1)
        self.assertIn(marker.encode(), raw)
        self.assertIn(marker.encode(), errors)
        self.assertNotIn(marker, out.getvalue() + err.getvalue())

    def test_launch_failure_does_not_echo_command(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, GITHUB_ACTIONS="true"):
            with self.assertRaisesRegex(CaptureRefused, "^capture-failed$"):
                capture([str(Path(temp) / "SYNTHETIC-SECRET-MISSING")], temp)

    def test_output_limit_and_non_ci_refusal(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, GITHUB_ACTIONS="true"):
            with self.assertRaisesRegex(CaptureRefused, "^capture-output-limit$"):
                capture([sys.executable, "-c", "print('SYNTHETIC-SECRET')"], temp, limit=1)
        with patch.dict(os.environ, GITHUB_ACTIONS="false"):
            with self.assertRaisesRegex(CaptureRefused, "^ci-only$"):
                capture([sys.executable, "-c", "print('unreachable')"], ".")
