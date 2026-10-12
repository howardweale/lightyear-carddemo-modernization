import tempfile
import unittest
from pathlib import Path
from tools.check_posttran_attempt1_phase1 import structural,policy,sha,CANDIDATE,EXPECTED

class Phase1GateTests(unittest.TestCase):
    def test_candidate_is_exact_extraction(self):
        self.assertEqual(EXPECTED,sha(CANDIDATE.read_bytes()))
    def test_missing_output_is_not_success(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError,'missing-or-linked-output'):structural(Path(name))
    def test_invalid_width_is_not_success(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'ACCTFILE').write_bytes(b'invalid\n')
            with self.assertRaises(ValueError):structural(root)
    def test_sandbox_grants_no_network_subprocess_or_environment(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);s=policy(root/'input',root/'output',root/'classes')
            for forbidden in ('AllPermission','SocketPermission','getenv','execute','setSecurityManager'):
                self.assertNotIn(forbidden,s)
            self.assertIn('"read,write"',s)

    def test_consumed_attempt_cannot_execute_on_later_head(self):
        from unittest.mock import patch
        from tools.check_posttran_attempt1_phase1 import run
        with tempfile.TemporaryDirectory() as name, patch('tools.check_posttran_attempt1_phase1.subprocess.run',side_effect=AssertionError('execution forbidden')):
            result=run(Path(name)/'new')
            self.assertFalse(result['passed'])
            self.assertEqual('f9eeccaa19ed137f8250baa8594831e8dc7dbd90',result['head'])
