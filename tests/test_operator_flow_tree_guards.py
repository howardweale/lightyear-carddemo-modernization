"""CI-only real temporary Git trees; no valid proof, service or authority."""
import os,subprocess,tempfile,unittest
from pathlib import Path
from tools.ci.operator_flow_tree_guards import check_tree_composition
from tools.ci.operator_flow_metadata import LIMITS

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS')=='true','CI-only real Git tree/merge checks')
class OriginalTreeChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']);self.addCleanup(self.tmp.cleanup)
        self.root=(Path(self.tmp.name)/'independent').resolve();self.root.mkdir()
        self.env=dict(os.environ,GIT_AUTHOR_NAME='Tree fixture',GIT_AUTHOR_EMAIL='fixture@example.invalid',
            GIT_COMMITTER_NAME='Tree fixture',GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init');self.git('config','core.autocrlf','false');self.git('config','core.filemode','false')
        (self.root/'source.txt').write_bytes(b'baseline\n');self.commit('base')
        self.base=self.oid()
        (self.root/'source.txt').write_bytes(b'executable\n');self.commit('E')
        self.executable=self.oid()
        self.metadata={p:('{"inert_path":"'+p+'"}\n').encode() for p in LIMITS}
    def git(self,*args):
        return subprocess.check_output(['git','--no-optional-locks','-C',str(self.root),
            '-c','commit.gpgsign=false','-c','core.hooksPath='+str(Path(self.tmp.name)/'no-hooks'),*args],
            env=self.env,stderr=subprocess.DEVNULL)
    def commit(self,message):self.git('add','.');self.git('commit','-m',message)
    def oid(self):return self.git('rev-parse','HEAD').decode().strip()
    def candidate(self):
        for relative,raw in self.metadata.items():
            p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.commit('M');return self.oid()
    def test_presign_E_full_tree_and_actual_main_merge(self):
        result=check_tree_composition(self.root,self.executable,self.executable,self.base)
        self.assertEqual(result['tree'],result['actual_merge_tree'])
        self.assertFalse(result['full_publication_guards_passed']);self.assertFalse(result['publication_authorized'])
    def test_metadata_M_preserves_complete_tree_and_merge(self):
        head=self.candidate();result=check_tree_composition(self.root,self.executable,head,self.base,self.metadata)
        self.assertEqual(result['metadata_head'],head)
        self.assertEqual(result['tree'],result['actual_merge_tree'])
        self.assertFalse(result['publication_authorized'])
        self.assertEqual(self.oid(),head);self.assertEqual(self.git('status','--porcelain=v1'),b'')
    def test_extra_source_delta_is_not_hidden_by_metadata_paths(self):
        (self.root/'unapproved.txt').write_bytes(b'extra\n');head=self.candidate()
        with self.assertRaisesRegex(ValueError,'complete-inventory-mismatch'):
            check_tree_composition(self.root,self.executable,head,self.base,self.metadata)
    def test_metadata_byte_mismatch_refuses(self):
        head=self.candidate();changed=dict(self.metadata);changed[next(iter(changed))]+=b' '
        with self.assertRaisesRegex(ValueError,'complete-inventory-mismatch'):
            check_tree_composition(self.root,self.executable,head,self.base,changed)
    def test_metadata_git_mode_mismatch_refuses(self):
        for relative,raw in self.metadata.items():
            p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.git('add','.');self.git('update-index','--chmod=+x',next(iter(self.metadata)))
        self.git('commit','-m','wrong metadata mode');head=self.oid()
        with self.assertRaisesRegex(ValueError,'complete-inventory-mismatch'):
            check_tree_composition(self.root,self.executable,head,self.base,self.metadata)
    def test_clean_merge_with_new_main_file_still_refuses(self):
        head=self.candidate();self.git('checkout','--detach',self.base)
        (self.root/'main-only.txt').write_bytes(b'new main input\n');self.commit('advanced main');main=self.oid()
        self.git('checkout','--detach',head)
        with self.assertRaisesRegex(ValueError,'actual-main-merge-differs'):
            check_tree_composition(self.root,self.executable,head,main,self.metadata)
    def test_actual_conflicting_main_merge_refuses(self):
        head=self.candidate();self.git('checkout','--detach',self.base)
        (self.root/'source.txt').write_bytes(b'conflicting main\n');self.commit('conflicting main');main=self.oid()
        self.git('checkout','--detach',head)
        with self.assertRaisesRegex(ValueError,'tree-git-or-merge-refused'):
            check_tree_composition(self.root,self.executable,head,main,self.metadata)
    def test_wrong_parent_refuses(self):
        head=self.candidate()
        with self.assertRaisesRegex(ValueError,'sole-parent-E'):
            check_tree_composition(self.root,self.base,head,self.base,self.metadata)
    def test_dirty_clone_refuses_before_merge(self):
        head=self.candidate();(self.root/'untracked.txt').write_bytes(b'dirty\n')
        with self.assertRaisesRegex(ValueError,'consumer-clean-source'):
            check_tree_composition(self.root,self.executable,head,self.base,self.metadata)
