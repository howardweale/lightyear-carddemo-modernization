import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch
from tools.test_cloudbank_transfer_framing import build_fixture


class MavenBuildTests(unittest.TestCase):
    def run_build(self, results):
        with tempfile.TemporaryDirectory() as folder:
            with patch('tools.test_cloudbank_transfer_framing.subprocess.run', side_effect=results) as run:
                result = build_fixture(Path(folder))
            self.assertIn('-U', run.call_args.args[0])
            self.assertTrue((Path(folder) / 'maven-1.stdout').exists())
            return result, run.call_count

    def test_resolution_retry_is_bounded_and_retained(self):
        fail = CompletedProcess([], 1, 'Non-resolvable parent POM', '')
        good = CompletedProcess([], 0, 'compiled', '')
        self.assertEqual(self.run_build([fail, good])[1], 2)
        result, calls = self.run_build([fail, fail])
        self.assertEqual((result.returncode, calls), (1, 2))

    def test_semantic_failure_never_retried(self):
        fail = CompletedProcess([], 1, 'COMPILATION ERROR', '')
        self.assertEqual(self.run_build([fail])[1], 1)

    def test_success_not_retried(self):
        self.assertEqual(self.run_build([CompletedProcess([], 0, '', '')])[1], 1)
