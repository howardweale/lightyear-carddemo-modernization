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

    def test_rerun_refuses_local_execution_and_automatic_retry(self):
        from unittest.mock import patch
        from tools.check_posttran_attempt1_phase1 import authorize_rerun
        for env in ({}, {'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'pull_request','GITHUB_RUN_ATTEMPT':'2'}):
            with patch.dict('os.environ',env,clear=True), self.assertRaisesRegex(ValueError,'first-CI-run-only'):
                authorize_rerun()

    def test_abend_transport_contracts_are_strict_and_separate(self):
        from unittest.mock import patch
        from lightyear_mainframe.posttran_invariants import check
        with patch('lightyear_mainframe.posttran_invariants.require_collation_independent'), patch('lightyear_mainframe.posttran_invariants.records',return_value=[]), patch('lightyear_mainframe.posttran_invariants.chronological_context',return_value=([{'outcome':'duplicate-write-abend-after-balances'}],{},{})):
            self.assertTrue(check({}, {}, timestamp='unused', returncode=12)['passed'])
            self.assertFalse(check({}, {}, timestamp='unused', returncode=999)['passed'])
            self.assertTrue(check({}, {}, timestamp='unused', returncode=999, returncode_contract='source-abcode')['passed'])
            self.assertFalse(check({}, {}, timestamp='unused', returncode=12, returncode_contract='source-abcode')['passed'])
            with self.assertRaisesRegex(ValueError,'unknown-returncode-contract'):
                check({}, {}, timestamp='unused', returncode=999, returncode_contract='anything')
