"""CI-only public fixture mechanics, not admitted-controller or OCI evidence."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


FIXTURE = (Path(__file__).resolve().parent / 'fixtures' / 'p5_public' /
           'human-public-build-control' / 'worker.py')


class PublicBuildFixtureTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def _invoke(self, root, raw):
        root.mkdir()
        worker = root / 'worker.py'
        worker.write_bytes(raw)
        completed = subprocess.run([sys.executable, '-I', '-B', str(worker)],
                                   cwd=root, capture_output=True, timeout=30,
                                   check=False)
        self.assertEqual(worker.read_bytes(), raw)
        return completed.returncode, completed.stdout, completed.stderr

    def test_defective_baseline_has_location_independent_failure(self):
        original = FIXTURE.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            first = self._invoke(Path(temp) / 'first', original)
            second = self._invoke(Path(temp) / 'a different checkout', original)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 1)
        self.assertEqual(first[1].splitlines(), [b'public-build-control-failed'])
        self.assertEqual(first[2], b'')
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_exact_repair_passes_same_embedded_check_and_original_still_fails(self):
        original = FIXTURE.read_bytes()
        broken = b'return left + right - 1'
        self.assertEqual(original.count(broken), 1)
        candidate = original.replace(broken, b'return left + right')
        # The acceptance command/check is byte-identical in both programs.
        self.assertEqual(original.split(b"if __name__ == '__main__':", 1)[1],
                         candidate.split(b"if __name__ == '__main__':", 1)[1])
        with tempfile.TemporaryDirectory() as temp:
            passed = self._invoke(Path(temp) / 'candidate', candidate)
            failed = self._invoke(Path(temp) / 'original', original)
        self.assertEqual(passed[0], 0)
        self.assertEqual(passed[1].splitlines(), [b'public-build-control-passed'])
        self.assertEqual(passed[2], b'')
        self.assertEqual(failed[0], 1)
        self.assertEqual(failed[1].splitlines(), [b'public-build-control-failed'])
        self.assertEqual(failed[2], b'')
        self.assertEqual(FIXTURE.read_bytes(), original)

    def test_wrong_repair_is_not_a_positive_control(self):
        original = FIXTURE.read_bytes()
        wrong = original.replace(b'return left + right - 1', b'return left + right + 1')
        self.assertNotEqual(wrong, original)
        with tempfile.TemporaryDirectory() as temp:
            failed = self._invoke(Path(temp) / 'wrong', wrong)
        self.assertEqual(failed[0], 1)
        self.assertEqual(failed[1].splitlines(), [b'public-build-control-failed'])
        self.assertEqual(failed[2], b'')
        self.assertEqual(FIXTURE.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
