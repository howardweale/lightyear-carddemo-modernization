"""CI-only untrusted public-byte/source boundaries, never native approval."""
import copy,hashlib,os,subprocess,tempfile,unittest
from pathlib import Path
import test_operator_flow_metadata as fixtures
from tools.ci.operator_flow_review_workflow import _trust_bytes
from tools.ci.operator_flow_review_cli import SCALARS
from tools.ci.operator_flow_publisher_preflight import (_metadata_files,_public_materials,
    _source_snapshot,preflight_publication)

class PublisherPreflight(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.fixture=fixtures.MetadataObjects();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.candidate=self.fixture.build();self.values=dict(executable=self.fixture.head,
            metadata_head=self.candidate['commit'],producer_run_id=1,artifact_id=2,archive_sha256='3'*64,
            plan_sha256='4'*64,decision_sha256='5'*64,journal_head_sha256='6'*64,
            public_key_sha256='7'*64,nonce_sha256='8'*64,commit_epoch=1700000000)
        self.base=Path(self.fixture.tmp.name);self.e=self.base/'E';self.m=self.base/'M';self.trust=self.base/'public'
        self.e.mkdir();self.m.mkdir();self.trust.mkdir();self.public=b'inert public fixture bytes, not a key'
        self.values['public_key_sha256']=hashlib.sha256(self.public).hexdigest()
        (self.trust/'public.pem').write_bytes(self.public)
        (self.trust/'trust.json').write_bytes(_trust_bytes(self.values['journal_head_sha256']))
    def material(self):return _public_materials(self.e,self.m,self.trust/'trust.json',self.values)
    def test_original_three_metadata_bytes_preserved(self):
        before=copy.deepcopy(self.candidate);files=_metadata_files(self.candidate,self.values)
        self.assertEqual(set(files),{'plan.json','contract.json','proof.json'})
        for name,raw in files.items():self.assertEqual(raw,self.fixture.raw[fixtures.PREFIX+name])
        self.assertEqual(before,self.candidate);self.assertFalse(self.candidate['publication_authorized'])
    def test_changed_expected_candidate_refuses(self):
        values=dict(self.values,metadata_head='0'*40)
        with self.assertRaisesRegex(ValueError,'exact-candidate'):_metadata_files(self.candidate,values)
    def test_false_flags_cannot_be_promoted(self):
        for flag in ('native_proof_verified','full_guards_passed','publish_ready','publication_authorized','full_route_passed','real_pack_ready'):
            self.candidate[flag]=True
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'no-authority'):_metadata_files(self.candidate,self.values)
            self.candidate[flag]=False
    def test_missing_or_extra_metadata_refuses(self):
        rows=self.candidate['files']
        for replacement in (rows[:-1],rows+[copy.deepcopy(rows[0])]):
            self.candidate['files']=replacement
            with self.assertRaisesRegex(ValueError,'inventory'):_metadata_files(self.candidate,self.values)
        self.candidate['files']=rows
    def test_changed_blob_refuses_even_with_asserted_new_hash(self):
        row=self.candidate['files'][0];kind,raw=self.candidate['objects'][row['git_blob']]
        changed=raw+b'changed';self.candidate['objects'][row['git_blob']]=(kind,changed)
        row['sha256']=hashlib.sha256(changed).hexdigest()
        with self.assertRaisesRegex(ValueError,'digests'):_metadata_files(self.candidate,self.values)
    def test_exact_inert_public_bytes_return_no_authority(self):
        files=self.material();self.assertEqual(files['public.pem'],self.public)
        self.assertEqual(files['trust.json'],_trust_bytes('6'*64));self.assertEqual(len(files),2)
    def test_changed_public_key_or_current_head_refuses(self):
        path=self.trust/'public.pem';path.write_bytes(self.public+b'changed')
        with self.assertRaisesRegex(ValueError,'independent-public-key'):self.material()
        path.write_bytes(self.public);self.values['journal_head_sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'prepared-trust-mismatch'):self.material()
    def test_public_materials_inside_checkout_refuse(self):
        for name in ('trust.json','public.pem'):(self.e/name).write_bytes((self.trust/name).read_bytes())
        with self.assertRaisesRegex(ValueError,'external-trust'):_public_materials(self.e,self.m,self.e/'trust.json',self.values)
    def test_actual_source_snapshot_and_other_original_root_refusal(self):
        root=Path(__file__).resolve().parents[1]
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()
        first=_source_snapshot(root,head);self.assertEqual(len(first),17);self.assertEqual(_source_snapshot(root,head),first)
        with self.assertRaisesRegex(ValueError,'module-origin'):_source_snapshot(self.fixture.root,self.fixture.head)
    def test_same_checkout_refuses_before_native_proof_or_api(self):
        with self.assertRaisesRegex(ValueError,'independent-prepared-checkouts'):
            preflight_publication(self.fixture.root,self.fixture.root,self.trust/'trust.json',
                reviewer_run_id=1,reviewer_job_id=2,pr_number=471,base='a'*40,tested_merge='b'*40,values=self.values)
