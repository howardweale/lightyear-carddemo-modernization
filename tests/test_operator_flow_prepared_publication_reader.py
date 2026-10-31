"""CI-only original Git reads and untrusted report refusals, never evidence."""
import ast,copy,hashlib,json,os,subprocess,unittest
from pathlib import Path
import test_operator_flow_publication_reconstruction as fixtures
from tools.ci.operator_flow_publication_reconstruction import read_prepared_publication
from tools.ci.operator_flow_handoff import _reported_public_handoff,LIMITS
from tools.ci.operator_flow_metadata import PREFIX

class PreparedPublicationReader(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.f=fixtures.PublicationReconstruction();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.e=self.f.fixture.root;self.m=self.e.parent/'prepared-M'
        subprocess.run(['git','clone','--no-hardlinks',str(self.e),str(self.m)],check=True,capture_output=True,env=self.f.fixture.env)
        for oid,(kind,body) in self.f.candidate['objects'].items():
            self.assertEqual(self.f.fixture.git('hash-object','-w','-t',kind,'--stdin',data=body,root=self.m).decode().strip(),oid)
        self.f.fixture.git('checkout','--detach',self.f.candidate['commit'],root=self.m)
    def read(self,**changes):
        args=dict(expected_executable=self.f.fixture.head,expected_candidate=self.f.candidate['commit'],commit_epoch=1700000000)
        args.update(changes)
        return read_prepared_publication(self.e,self.m,self.f.files,**args)
    def snapshot(self):
        return {str(root)+':'+str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for root in (self.e,self.m) for p in root.rglob('*') if p.is_file()}
    def test_prepared_read_matches_original_builder_requests_without_writes(self):
        before=self.snapshot();self.assertEqual(self.read(),self.f.reconstruct());self.assertEqual(before,self.snapshot())
        self.assertFalse(self.read()[0]['publication_authorized'])
    def test_dirty_metadata_checkout_refuses(self):
        (self.m/PREFIX/'proof.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'clean-source'):self.read()
    def test_same_checkout_cannot_supply_both_E_and_M(self):
        self.m=self.e
        with self.assertRaisesRegex(ValueError,'independent-E-M'):self.read()
    def test_changed_archive_bytes_even_with_new_report_hash_refuse(self):
        self.f.files['proof.json']+=b' ';self.f.refresh()
        with self.assertRaisesRegex(ValueError,'byte-exact-published-handoff'):self.read()
    def test_original_report_summary_cannot_replace_actual_tree(self):
        self.f.report['metadata_candidate']['tree']='0'*40;self.f.refresh()
        with self.assertRaisesRegex(ValueError,'candidate-summary'):self.read()
    def test_independent_epoch_not_adopted_from_report(self):
        with self.assertRaisesRegex(ValueError,'reported-heads-epoch'):self.read(commit_epoch=1700000001)
    def test_actual_M_head_must_match_independent_expectation(self):
        self.f.fixture.git('checkout','--detach',self.f.fixture.head,root=self.m)
        with self.assertRaisesRegex(ValueError,'exact-M'):self.read()

class OriginalReportBinding(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.files={name:b'inert public nonproof bytes' for name in LIMITS}
        self.observed=dict(repository='untrusted relationship only',executable='a'*40,run_id=1,run_attempt=1,job_id=2,workflow_id=3,workflow_path='inert')
        self.files['trust.json']=json.dumps(dict(scope='factory',public_key='public.pem',journal_head_sha256='b'*64)).encode()
        self.report=dict(producer_stage_passed=True,fixture_only=True,full_route_passed=False,real_pack_ready=False,producer=dict(self.observed),public_handoff_hashes={k:hashlib.sha256(v).hexdigest() for k,v in self.files.items() if k!='producer.json'})
    def check(self):
        self.files['producer.json']=json.dumps(self.report).encode();return _reported_public_handoff(self.files,self.observed)
    def test_report_cannot_claim_full_route(self):
        self.report['full_route_passed']=True
        with self.assertRaisesRegex(ValueError,'report-state'):self.check()
    def test_report_must_bind_original_observed_producer(self):
        self.report['producer']['job_id']=7
        with self.assertRaisesRegex(ValueError,'reported-producer-binding'):self.check()
    def test_report_cannot_bind_changed_bytes(self):
        self.files['public.pem']+=b'changed'
        with self.assertRaisesRegex(ValueError,'public-bytes-binding'):self.check()
