"""CI-only inert metadata observations; matching hashes never grant origin."""
import ast,copy,hashlib,json,os,unittest
from pathlib import Path
import test_operator_flow_publication_objects as fixtures
from tools.ci.operator_flow_review_workflow import _review_observation

class ReviewObservation(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.fixture=fixtures.PublicationObjects();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.candidate=self.fixture.candidate;self.requests=self.fixture.requests()
        self.values=dict(executable=self.candidate['parent'],metadata_head=self.candidate['commit'],
            producer_run_id=1,artifact_id=2,archive_sha256='3'*64,plan_sha256='4'*64,
            decision_sha256='5'*64,journal_head_sha256='6'*64,public_key_sha256='7'*64,
            nonce_sha256='8'*64,commit_epoch=self.candidate['commit_epoch'],
            metadata_root='private-path-must-not-appear',trust_path='another-private-path')
        self.identity=dict(pr=471,run=1,job=2,workflow=3,executable=self.candidate['parent'],
            tested_merge='a'*40,base='b'*40,workflow_revision='c'*40,workflow_sha256='d'*64,event_sha256='e'*64)
    def observe(self):return _review_observation(self.candidate,self.requests,self.values,self.identity)
    def test_original_request_bytes_have_exact_hash_no_authority(self):
        before=copy.deepcopy((self.candidate,self.requests,self.values,self.identity));text=self.observe()
        digest=hashlib.sha256(json.dumps(self.requests,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        self.assertIn('requests_sha256='+digest,text);self.assertTrue(text.startswith('DISPOSABLE_REVIEW_BINDING '))
        self.assertIn('publication_authorized=false admission_authorized=false qualification_evidence=false',text)
        self.assertEqual(before,(self.candidate,self.requests,self.values,self.identity))
    def test_no_object_contents_paths_or_keys_are_emitted(self):
        text=self.observe();self.assertLess(len(text),1024)
        self.assertNotIn('private-path',text);self.assertNotIn('another-private-path',text)
        for row in self.requests:
            if row[0]=='blobs':self.assertNotIn(row[2]['content'],text)
    def test_request_order_change_alters_binding(self):
        before=self.observe();rows=list(self.requests);rows[0],rows[1]=rows[1],rows[0];self.requests=tuple(rows)
        self.assertNotEqual(before,self.observe())
    def test_external_expectation_change_alters_binding(self):
        before=self.observe();self.values['artifact_id']=3;self.assertNotEqual(before,self.observe())
    def test_cross_candidate_or_final_commit_refuses(self):
        original=self.candidate['commit'];self.candidate['commit']='0'*40
        with self.assertRaisesRegex(ValueError,'candidate'):self.observe()
        self.candidate['commit']=original;self.requests=self.requests[:-1]
        with self.assertRaisesRegex(ValueError,'final-commit'):self.observe()
    def test_authority_flags_cannot_be_promoted(self):
        for flag in ('native_proof_verified','full_guards_passed','publish_ready','publication_authorized','full_route_passed','real_pack_ready'):
            self.candidate[flag]=True
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'no-authority'):self.observe()
            self.candidate[flag]=False
    def test_identity_injection_and_boolean_ids_refuse(self):
        original=dict(self.identity)
        for key,value in (('run',True),('event_sha256','x\n'*32),('executable','0'*40)):
            self.identity=dict(original,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):self.observe()
        self.identity=dict(original,extra='asserted')
        with self.assertRaises(ValueError):self.observe()
    def test_emission_occurs_only_after_native_review_and_source_recheck(self):
        path=Path(__file__).resolve().parents[1]/'tools/ci/operator_flow_review_workflow.py'
        body=next(n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(body) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        native=[n for n in calls if n.func.id=='review_publication'];self.assertEqual(len(native),1)
        observation=[n for n in calls if n.func.id=='_review_observation'];self.assertEqual(len(observation),1)
        checks=[n.lineno for n in calls if n.func.id=='_source'];self.assertEqual(len(checks),2)
        self.assertLess(native[0].lineno,max(checks));self.assertLess(max(checks),observation[0].lineno)
