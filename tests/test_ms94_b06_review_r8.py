from pathlib import Path
import unittest


class ReviewR8Tests(unittest.TestCase):
    def test_login_has_no_s4u_copy_or_policy_bypass_and_preserves_pinned_proofs(self):
        # Contract check, not evidence that Windows sign-in or ACL enforcement passed.
        root = Path(__file__).resolve().parents[1]
        parent = (root/'tools/ms94_b06_builder_login.ps1').read_text()
        self.assertNotIn('ExecutionPolicy',parent)
        self.assertNotIn('Register-ScheduledTask',parent)
        self.assertIn('CreateProcessWithLogonW',parent)
        self.assertIn('Disable-LocalUser',parent)
        self.assertIn('cli_auth_credentials_store=',parent)
        self.assertIn("$start.UserName='lyb06builder'",parent)
        self.assertNotIn('ReadAllText',parent)
        self.assertNotIn('-File ',parent)
