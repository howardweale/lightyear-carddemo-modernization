"""CI-only real public file boundary probes; no valid proof or API substitute."""
import os,tempfile,unittest
from pathlib import Path
from tools.ci.operator_flow_publication_review import _prepared_trust,_independent_expectations


class PublicationReviewBoundaries(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.e=self.root/'E';self.m=self.root/'M'
        self.e.mkdir();self.m.mkdir();self.trust=self.root/'external';self.trust.mkdir()
        self.files={'trust.json':b'{"scope":"inert invalid fixture"}', 'public.pem':b'not a public key'}
        for name,raw in self.files.items():(self.trust/name).write_bytes(raw)
        self.args=dict(executable='1'*40,metadata_head='2'*40,producer_run_id=1,artifact_id=2,
            archive_sha256='3'*64,plan_sha256='4'*64,decision_sha256='5'*64,
            journal_head_sha256='6'*64,public_key_sha256='7'*64,nonce_sha256='8'*64,commit_epoch=1700000000)
    def read(self,path=None):
        return _prepared_trust(self.e,self.m,path or self.trust/'trust.json',self.files)
    def test_matching_public_bytes_return_no_authority(self):
        before={p.name:p.read_bytes() for p in self.trust.iterdir()}
        self.assertIsNone(self.read())
        self.assertEqual({p.name:p.read_bytes() for p in self.trust.iterdir()},before)
        self.assertNotIn('publication_authorized',_independent_expectations(**self.args))
    def test_changed_trust_or_public_key_refuses(self):
        for name in self.files:
            with self.subTest(name=name):
                path=self.trust/name;path.write_bytes(self.files[name]+b'changed')
                with self.assertRaisesRegex(ValueError,'prepared-trust-mismatch'):self.read()
                path.write_bytes(self.files[name])
    def test_trust_inside_either_checkout_refuses(self):
        for root in (self.e,self.m):
            for name,raw in self.files.items():(root/name).write_bytes(raw)
            with self.subTest(root=root),self.assertRaisesRegex(ValueError,'external-trust'):
                self.read(root/'trust.json')
    def test_hardlinked_public_key_refuses(self):
        # Native bounded reader requires a sole regular file; no fake key loader.
        (self.trust/'public.pem').unlink()
        original=self.root/'original-public';original.write_bytes(self.files['public.pem'])
        os.link(original,self.trust/'public.pem')
        with self.assertRaisesRegex(Exception,'trust-bytes'):self.read()
    def test_missing_or_oversize_public_key_refuses(self):
        path=self.trust/'public.pem';path.unlink()
        with self.assertRaisesRegex(Exception,'trust-bytes'):self.read()
        path.write_bytes(b'x'*65537)
        with self.assertRaisesRegex(Exception,'trust-bytes'):self.read()
    def test_relative_or_wrong_named_trust_refuses(self):
        with self.assertRaisesRegex(ValueError,'prepared-trust-path'):self.read(Path('trust.json'))
        other=self.trust/'other.json';other.write_bytes(self.files['trust.json'])
        with self.assertRaisesRegex(ValueError,'prepared-trust-path'):self.read(other)
    def test_independent_expectation_types_and_values_refuse(self):
        for key,value in (('metadata_head','1'*40),('executable','bad'),('plan_sha256','bad'),
            ('producer_run_id',True),('artifact_id',0),('commit_epoch',True),('commit_epoch',0)):
            args=dict(self.args);args[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):_independent_expectations(**args)
