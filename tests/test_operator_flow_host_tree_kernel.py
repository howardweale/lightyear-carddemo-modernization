"""CI tests of original public boundary and shared tree algorithm only."""
import os,subprocess,sys,unittest
from pathlib import Path
import test_operator_flow_tree_guards as fixtures
from tools.ci.operator_flow_tree_guards import check_tree_composition,_checked_tree_composition

class HostTreeKernel(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def test_public_entry_still_refuses_non_CI_before_paths(self):
        env=dict(os.environ);env.pop('GITHUB_ACTIONS',None)
        code="from tools.ci.operator_flow_tree_guards import check_tree_composition; check_tree_composition(None,None,None,None)"
        result=subprocess.run([sys.executable,'-B','-c',code],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('tree-check-ci-only',result.stderr)
    def test_shared_original_kernel_matches_guarded_CI_entry(self):
        f=fixtures.OriginalTreeChecks();f.setUp();self.addCleanup(f.doCleanups)
        head=f.candidate()
        original=check_tree_composition(f.root,f.executable,head,f.base,f.metadata)
        self.assertEqual(_checked_tree_composition(f.root,f.executable,head,f.base,f.metadata),original)
        self.assertFalse(original['publication_authorized']);self.assertFalse(original['full_publication_guards_passed'])
