"""Original Git history and exact approved import; no authority or execution."""
import os,unittest
from pathlib import Path
import test_operator_flow_tree_guards as fixtures
from tools.ci.operator_flow_publisher_preflight import (_protected_history,_provenance_protected_history,
    _posttran_inventory,POSTTRAN_APPROVED_ARCHIVE_MAIN,POSTTRAN_APPROVED_ARCHIVE_PATHS)

class ApprovedSyncHistory(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.f=fixtures.OriginalTreeChecks();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.protected=frozenset({'source.txt'})
    def changed(self):
        return _provenance_protected_history(self.f.root,self.f.executable,self.f.oid(),self.protected)
    def actual_inventory(self):
        root=Path(__file__).resolve().parents[1]
        head='245ae1ba5ad8222d259c1f1078dce51eebff213f'
        return root,head,_posttran_inventory(root,head,'ea2b22bfb7465d3dee5b0286d7770a60df4cf62869d3cb7f9c84c6708810d27d')
    def test_exact_approved_sync_is_inherited_without_new_edit(self):
        root,head,protected=self.actual_inventory()
        self.assertEqual(_provenance_protected_history(root,POSTTRAN_APPROVED_ARCHIVE_MAIN,head,protected),frozenset())
    def test_original_full_history_still_sees_imported_paths(self):
        root,head,protected=self.actual_inventory()
        self.assertEqual(_protected_history(root,POSTTRAN_APPROVED_ARCHIVE_MAIN,head,protected),POSTTRAN_APPROVED_ARCHIVE_PATHS)
    def test_other_merge_import_is_not_exempt(self):
        tree=self.f.git('rev-parse',self.f.executable+'^{tree}').decode().strip()
        merge=self.f.git('commit-tree',tree,'-p',self.f.base,'-p',self.f.executable,'-m','inert different import').decode().strip()
        self.assertEqual(_provenance_protected_history(self.f.root,self.f.executable,merge,self.protected),self.protected)
    def test_reverted_change_stays_visible(self):
        (self.f.root/'source.txt').write_bytes(b'changed\n');self.f.commit('change')
        (self.f.root/'source.txt').write_bytes(b'executable\n');self.f.commit('revert')
        self.assertEqual(self.changed(),self.protected)
    def test_mode_change_stays_visible(self):
        self.f.git('update-index','--chmod=+x','source.txt');self.f.git('commit','-m','mode')
        self.assertEqual(self.changed(),self.protected)
    def test_rename_stays_visible(self):
        self.f.git('mv','source.txt','renamed.txt');self.f.commit('rename')
        self.assertEqual(self.changed(),self.protected)
    def test_metadata_only_history_remains_empty(self):
        self.f.candidate();self.assertEqual(self.changed(),frozenset())
    def test_unrelated_base_still_refuses(self):
        with self.assertRaisesRegex(ValueError,'consumer-git-refused'):
            _provenance_protected_history(self.f.root,self.f.executable,self.f.base,self.protected)
    def test_archive_interval_preserves_only_two_approved_edits(self):
        root,head,protected=self.actual_inventory()
        anchor='f267fc9ee8d1329529debf4b5edd72bb026b63a5'
        self.assertEqual(_provenance_protected_history(root,anchor,POSTTRAN_APPROVED_ARCHIVE_MAIN,protected),POSTTRAN_APPROVED_ARCHIVE_PATHS)
    def test_original_archive_detector_retains_all_seven_imported_paths(self):
        root,head,protected=self.actual_inventory()
        anchor='f267fc9ee8d1329529debf4b5edd72bb026b63a5'
        expected=POSTTRAN_APPROVED_ARCHIVE_PATHS|frozenset('docs/factory/posttran-key-change-2026-10-23/'+n for n in
            ('README.md','amendment.json','authority.public.pem','seven-bindings-not-adopted.json','unsigned-request.json'))
        self.assertEqual(_protected_history(root,anchor,POSTTRAN_APPROVED_ARCHIVE_MAIN,protected),expected)
