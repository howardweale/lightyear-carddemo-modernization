"""CI disposable real Git preparation with inert metadata, never valid proof."""
from pathlib import Path
from hashlib import sha256
import os,subprocess,unittest
import test_operator_flow_metadata as fixtures
from tools.ci.operator_flow_metadata import PREFIX
from tools.ci.operator_flow_publication_review import _materialize_review_checkout

class ReviewMetadataCheckout(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.fixture=fixtures.MetadataObjects();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.source=self.fixture.root;self.root=Path(self.fixture.tmp.name)/'review-copy'
        subprocess.run(['git','clone','--no-hardlinks',str(self.source),str(self.root)],check=True,capture_output=True,env=self.fixture.env)
        self.git('config','core.autocrlf','false');self.git('checkout','--detach',self.fixture.head)
        self.candidate=self.fixture.build()
        self.files={name:self.fixture.raw[PREFIX+name] for name in ('plan.json','contract.json','proof.json')}
    def git(self,*args):return self.fixture.git(*args,root=self.root)
    def prepare(self,**override):
        args=dict(executable=self.fixture.head,metadata_head=self.candidate['commit'],commit_epoch=1700000000);args.update(override)
        return _materialize_review_checkout(self.source,self.root,self.files,**args)
    def test_actual_independent_git_M_preserves_source_and_false_authority(self):
        before={p.relative_to(self.source).as_posix():sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        result=self.prepare()
        self.assertEqual(result,self.candidate);self.assertFalse(result['native_proof_verified']);self.assertFalse(result['publication_authorized'])
        self.assertEqual(self.git('rev-parse','HEAD').decode().strip(),result['commit'])
        self.assertEqual(self.git('status','--porcelain=v1','--untracked-files=all'),b'')
        for name,body in self.files.items():self.assertEqual((self.root/(PREFIX+name)).read_bytes(),body)
        self.assertEqual(before,{p.relative_to(self.source).as_posix():sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()})
    def test_existing_intent_refuses_without_mutation(self):
        intent=self.root/'.git/operator-review-materialization-intent.txt';intent.write_bytes(b'prior attempt')
        with self.assertRaisesRegex(ValueError,'one-shot'):self.prepare()
        self.assertEqual(intent.read_bytes(),b'prior attempt');self.assertEqual(self.git('rev-parse','HEAD').decode().strip(),self.fixture.head)
    def test_completed_preparation_cannot_resume(self):
        self.prepare();head=self.git('rev-parse','HEAD')
        with self.assertRaisesRegex(ValueError,'exact-E'):self.prepare()
        self.assertEqual(self.git('rev-parse','HEAD'),head)
    def test_attached_checkout_refuses_before_intent(self):
        self.git('checkout','-b','fixture-attached')
        with self.assertRaisesRegex(ValueError,'prepared-detached'):self.prepare()
        self.assertFalse((self.root/'.git/operator-review-materialization-intent.txt').exists())
    def test_dirty_checkout_refuses_without_repair(self):
        p=self.root/'executable.py';p.write_bytes(b'changed retained bytes')
        with self.assertRaisesRegex(ValueError,'clean-source'):self.prepare()
        self.assertEqual(p.read_bytes(),b'changed retained bytes')
    def test_wrong_candidate_or_epoch_refuses_before_intent(self):
        for args in (dict(metadata_head='0'*40),dict(commit_epoch=1700000001)):
            with self.assertRaisesRegex(ValueError,'exact-M'):self.prepare(**args)
            self.assertFalse((self.root/'.git/operator-review-materialization-intent.txt').exists())
    def test_source_checkout_cannot_be_materialization_target(self):
        self.root=self.source
        with self.assertRaisesRegex(ValueError,'separate-temporary'):self.prepare()
    def test_hardlinked_git_metadata_refuses_before_intent(self):
        config=self.root/'.git/config';other=Path(self.fixture.tmp.name)/'config-retained';os.link(config,other)
        with self.assertRaisesRegex(ValueError,'hardlinked-metadata'):self.prepare()
        self.assertFalse((self.root/'.git/operator-review-materialization-intent.txt').exists())
