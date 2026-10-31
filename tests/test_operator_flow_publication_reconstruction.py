"""CI-only actual Git byte reconstruction with inert non-proof metadata."""
import copy,json,os,unittest
from hashlib import sha256
import test_operator_flow_metadata as fixtures
from tools.ci.operator_flow_handoff import LIMITS
from tools.ci.operator_flow_metadata import PREFIX
from tools.ci.operator_flow_publication_reconstruction import reconstruct_publication_objects


class PublicationReconstruction(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.fixture=fixtures.MetadataObjects();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.candidate=self.fixture.build()
        self.files={name:self.fixture.raw[PREFIX+name] for name in ('plan.json','contract.json','proof.json')}
        self.files.update({'public.pem':b'inert not a public key','trust.json':b'{}'})
        self.report={'metadata_candidate':{k:self.candidate[k] for k in
            ('parent','commit','commit_epoch','base_tree','tree','files')}}
        self.refresh()
    def refresh(self):
        self.report['public_handoff_hashes']={k:sha256(v).hexdigest() for k,v in self.files.items() if k!='producer.json'}
        self.files['producer.json']=json.dumps(self.report,sort_keys=True).encode()
    def reconstruct(self,**kwargs):
        params=dict(expected_executable=self.fixture.head,expected_candidate=self.candidate['commit'],commit_epoch=1700000000)
        params.update(kwargs)
        return reconstruct_publication_objects(self.fixture.root,self.files,**params)
    def test_original_objects_reconstructed_without_writes_or_authority(self):
        before=copy.deepcopy(self.files)
        def git_bytes():return {p.relative_to(self.fixture.root/'.git').as_posix():sha256(p.read_bytes()).hexdigest()
            for p in (self.fixture.root/'.git').rglob('*') if p.is_file()}
        metadata_before=git_bytes();result,requests=self.reconstruct()
        self.assertEqual(git_bytes(),metadata_before)
        self.assertEqual(result,self.candidate);self.assertEqual(self.files,before)
        self.assertEqual(requests[-1][1],self.candidate['commit'])
        self.assertFalse(result['native_proof_verified']);self.assertFalse(result['publication_authorized'])
        self.assertFalse(result['publish_ready']);self.assertEqual(self.fixture.git('status','--porcelain=v1'),b'')
        self.assertEqual(self.fixture.git('rev-parse','HEAD').decode().strip(),self.fixture.head)
    def test_changed_proof_even_with_refreshed_report_refuses_exact_candidate(self):
        self.files['proof.json']+=b' ';self.refresh()
        with self.assertRaisesRegex(ValueError,'candidate-mismatch'):self.reconstruct()
    def test_wrong_independent_heads_and_epoch_refuse(self):
        for change in ({'expected_executable':'0'*40},{'expected_candidate':'0'*40},
                       {'commit_epoch':1700000001},{'commit_epoch':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.reconstruct(**change)
    def test_candidate_tree_base_or_inventory_substitution_refuses(self):
        for field in ('base_tree','tree','files'):
            saved=copy.deepcopy(self.report)
            self.report['metadata_candidate'][field]=[] if field=='files' else '0'*40;self.refresh()
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'candidate-summary'):self.reconstruct()
            self.report=saved;self.refresh()
    def test_original_public_hashes_required(self):
        self.files['public.pem']+=b'changed'
        with self.assertRaisesRegex(ValueError,'original-byte-hashes'):self.reconstruct()
    def test_missing_extra_nonbytes_and_oversize_handoff_refuse(self):
        saved=copy.deepcopy(self.files)
        for change in ('missing','extra','text','large'):
            self.files=copy.deepcopy(saved)
            if change=='missing':del self.files['trust.json']
            elif change=='extra':self.files['other']=b'x'
            elif change=='text':self.files['proof.json']='text'
            else:self.files['producer.json']=b'x'*(LIMITS['producer.json']+1)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'bounded-handoff'):self.reconstruct()
    def test_duplicate_report_key_refuses(self):
        self.files['producer.json']=b'{"metadata_candidate":{},"metadata_candidate":{}}'
        with self.assertRaises(ValueError):self.reconstruct()
    def test_dirty_source_refuses_without_repair(self):
        path=self.fixture.root/'executable.py';path.write_bytes(b'changed original')
        with self.assertRaisesRegex(ValueError,'clean-E'):self.reconstruct()
        self.assertEqual(path.read_bytes(),b'changed original')
