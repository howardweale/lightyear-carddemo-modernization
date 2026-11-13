"""Actual temporary Git preservation checks; inert CI feedback only."""
import os,subprocess,unittest
from pathlib import Path
import test_operator_flow_tree_guards as fixtures
from tools.ci.operator_flow_publisher_preflight import _protected_history,_posttran_inventory,POSTTRAN_RETAINED

class PublisherPosttranHistory(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.f=fixtures.OriginalTreeChecks();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.protected=frozenset({'source.txt'})
    def changes(self,base=None):
        return _protected_history(self.f.root,base or self.f.base,self.f.oid(),self.protected)
    def test_changed_source_is_detected(self):
        self.assertEqual(self.changes(),self.protected)
    def test_reverted_change_remains_in_history(self):
        (self.f.root/'source.txt').write_bytes(b'baseline\n');self.f.commit('revert')
        self.assertEqual(self.f.git('diff','--name-only',self.f.base,self.f.oid()),b'')
        self.assertEqual(self.changes(),self.protected)
    def test_rename_preserves_deleted_path_detection(self):
        self.f.git('mv','source.txt','renamed.txt');self.f.commit('rename')
        self.assertEqual(self.changes(self.f.executable),self.protected)
    def test_mode_only_delta_is_detected(self):
        self.f.git('update-index','--chmod=+x','source.txt');self.f.git('commit','-m','mode')
        self.assertEqual(self.changes(self.f.executable),self.protected)
    def test_metadata_only_preserves_protected_history(self):
        self.f.candidate();self.assertEqual(self.changes(self.f.executable),frozenset())
    def test_unrelated_history_base_refuses(self):
        with self.assertRaisesRegex(ValueError,'consumer-git-refused'):
            _protected_history(self.f.root,self.f.executable,self.f.base,self.protected)
    def test_missing_independent_inventory_refuses_before_git(self):
        with self.assertRaisesRegex(ValueError,'independent-posttran-digest'):_posttran_inventory(None,self.f.base,None)
    def test_actual_committed_inventory_includes_all_retained_paths(self):
        root=Path(__file__).resolve().parents[1]
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()
        result=_posttran_inventory(root,head,'ea2b22bfb7465d3dee5b0286d7770a60df4cf62869d3cb7f9c84c6708810d27d')
        self.assertEqual(len(result),235);self.assertTrue(set(POSTTRAN_RETAINED)<=result)
