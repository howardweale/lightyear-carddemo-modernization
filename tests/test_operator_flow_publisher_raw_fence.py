"""CI-only original raw fence on real Git/inert public fixtures; no authority."""
import os,subprocess,tempfile,unittest
from pathlib import Path
import test_java_quality_fence as fixtures
from tools import check_java_quality_fence as original
from tools.ci.operator_flow_publisher_preflight import _raw_fence,_fence_source

class PublisherRawFence(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'source';self.root.mkdir()
        self.env=dict(os.environ,GIT_AUTHOR_NAME='Disposable fence test',GIT_AUTHOR_EMAIL='test@example.invalid',
            GIT_COMMITTER_NAME='Disposable fence test',GIT_COMMITTER_EMAIL='test@example.invalid')
        self.git('init');self.git('config','core.autocrlf','false')
        documents=fixtures.JavaQualityFenceTests().fixture()
        for name,raw in dict(documents,**{'service/Support.java':b'original'}).items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.commit('base');self.base=self.head()
        self.digest=original.inspect(self.root,self.base,self.base)['fence_sha256']
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),'-c','commit.gpgsign=false',
            '-c','core.hooksPath='+str(Path(self.tmp.name)/'empty-hooks'),*args],env=self.env,stderr=subprocess.DEVNULL)
    def commit(self,message):self.git('add','.');self.git('commit','-m',message)
    def head(self):return self.git('rev-parse','HEAD').decode().strip()
    def test_original_unfenced_metadata_is_only_path_observation(self):
        p=self.root/'docs/factory/p5-human-clean-control/proof.json';p.parent.mkdir(parents=True);p.write_bytes(b'inert-invalid-proof')
        self.commit('metadata');head=self.head();report=_raw_fence(self.root,self.base,head,self.digest)
        self.assertEqual(report['blocked_paths'],[]);self.assertFalse(report['automatic_expiry'])
        self.assertEqual(report['head'],head);self.assertEqual(self.head(),head)
    def test_wrong_independent_fence_digest_refuses(self):
        with self.assertRaisesRegex(ValueError,'raw-fence-binding'):_raw_fence(self.root,self.base,self.base,'0'*64)
    def test_new_original_test_prefix_is_blocked(self):
        p=self.root/'factory/carddemo-web/service/src/test/java/NewTest.java';p.parent.mkdir(parents=True);p.write_bytes(b'new')
        self.commit('fenced test')
        with self.assertRaisesRegex(ValueError,'raw-fence-blocked'):_raw_fence(self.root,self.base,self.head(),self.digest)
    def test_frozen_path_rename_is_blocked(self):
        self.git('mv','service/Support.java','service/Other.java');self.commit('rename')
        with self.assertRaisesRegex(ValueError,'raw-fence-blocked'):_raw_fence(self.root,self.base,self.head(),self.digest)
    def test_candidate_record_cannot_remove_trusted_base_fence(self):
        (self.root/original.F2).write_bytes(b'{}');self.commit('candidate altered record')
        with self.assertRaisesRegex(ValueError,'raw-fence-blocked'):_raw_fence(self.root,self.base,self.head(),self.digest)
    def test_exact_actual_ci_source_matches_its_committed_base(self):
        root=Path(__file__).resolve().parents[1];head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()
        first=_fence_source(root,head,head);self.assertEqual(len(first),64);self.assertEqual(_fence_source(root,head,head),first)
    def test_other_checkout_cannot_supply_loaded_checker_origin(self):
        with self.assertRaisesRegex(ValueError,'fence-source-origin'):_fence_source(self.root,self.base,self.base)
    def test_missing_independent_digest_refuses_before_git(self):
        with self.assertRaisesRegex(ValueError,'independent-raw-fence-digest'):_raw_fence(None,self.base,self.base,None)
