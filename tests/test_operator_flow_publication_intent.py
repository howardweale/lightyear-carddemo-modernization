"""Real temporary filesystem CI probes; no remote operations or authority."""
import hashlib,os,tempfile,unittest
from pathlib import Path
from tools.ci.operator_flow_publication_intent import reserve_intent,verify_intent

class PublicationIntent(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.args=dict(executable='1'*40,metadata_head='2'*40,request_sha256='3'*64,
            branch_ref='refs/heads/codex/disposable-intent-test')
    def test_exclusive_file_is_labelled_and_exactly_rechecked(self):
        digest=reserve_intent(self.root,**self.args);raw=(self.root/'operator-publication-intent.txt').read_bytes()
        self.assertTrue(raw.startswith(b'DISPOSABLE PUBLICATION INTENT; NOT APPROVAL OR QUALIFICATION'))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),digest);self.assertEqual(verify_intent(self.root,**self.args),digest)
    def test_duplicate_same_operation_refuses_without_changes(self):
        reserve_intent(self.root,**self.args);path=self.root/'operator-publication-intent.txt';before=path.read_bytes()
        with self.assertRaises(FileExistsError):reserve_intent(self.root,**self.args)
        self.assertEqual(path.read_bytes(),before)
    def test_changed_operation_cannot_reuse_directory(self):
        reserve_intent(self.root,**self.args)
        with self.assertRaises(FileExistsError):reserve_intent(self.root,**dict(self.args,metadata_head='4'*40))
    def test_partial_intent_is_not_repaired(self):
        path=self.root/'operator-publication-intent.txt';path.write_bytes(b'partial')
        with self.assertRaises(FileExistsError):reserve_intent(self.root,**self.args)
        self.assertEqual(path.read_bytes(),b'partial')
    def test_modified_binding_refuses(self):
        reserve_intent(self.root,**self.args)
        with self.assertRaisesRegex(ValueError,'intent-binding-changed'):
            verify_intent(self.root,**dict(self.args,request_sha256='4'*64))
    def test_hardlinked_intent_refuses(self):
        reserve_intent(self.root,**self.args);os.link(self.root/'operator-publication-intent.txt',self.root/'second')
        with self.assertRaisesRegex(ValueError,'intent-file-shape'):verify_intent(self.root,**self.args)
    def test_symlinked_parent_refuses(self):
        real=self.root/'real';real.mkdir();link=self.root/'alias';link.symlink_to(real,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'intent-absolute-root'):reserve_intent(link,**self.args)
        self.assertEqual(list(real.iterdir()),[])
    def test_bad_head_or_ref_refuses_before_path_access(self):
        for change in (dict(metadata_head='1'*40),dict(executable=True),dict(branch_ref='refs/heads/main'),
                       dict(branch_ref='refs/heads/codex/x\ny'),dict(request_sha256=False)):
            with self.subTest(change=change),self.assertRaises(ValueError):
                reserve_intent(None,**dict(self.args,**change))
