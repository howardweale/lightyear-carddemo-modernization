"""Untrusted service/log relations only; no fabricated API or native admission."""
import copy,os,subprocess,unittest
from pathlib import Path
import test_operator_flow_review_observation as fixtures
from tools.ci.operator_flow_review_workflow import _review_observation
from tools.ci.operator_flow_review_cli import SCALARS
from tools.ci.operator_flow_completed_review import (_relationships,_log_identity,
    read_reviewed_publication,REPOSITORY,REVIEW_WORKFLOW,REVIEW_JOB,STEP,LIMIT)

class CompletedReview(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.fixture=fixtures.ReviewObservation();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.identity=self.fixture.identity;head=self.identity['executable'];base=self.identity['base'];merge=self.identity['tested_merge']
        self.expected={k:self.identity[k] for k in ('run','job','pr','executable','base','tested_merge')}
        self.run=dict(id=1,run_attempt=1,event='pull_request',head_sha=head,status='completed',conclusion='success',
            repository=dict(full_name=REPOSITORY),head_repository=dict(full_name=REPOSITORY),workflow_id=3)
        self.workflow=dict(id=3,path=REVIEW_WORKFLOW)
        names=['Run actions/checkout@v7','Run actions/setup-python@v6','Install native public verification dependency',
            'Fetch original tested merge and workflow revision',STEP]
        self.job=dict(id=2,run_id=1,head_sha=head,name=REVIEW_JOB,status='completed',conclusion='success',
            steps=[dict(number=i+1,name=name,status='completed',conclusion='success') for i,name in enumerate(names)])
        self.listing=dict(total_count=1,jobs=[self.job])
        self.pr=dict(number=471,state='open',head=dict(sha=head,repo=dict(full_name=REPOSITORY)),
            base=dict(sha=base,ref='main',repo=dict(full_name=REPOSITORY)),merge_commit_sha=merge)
        self.merge=dict(sha=merge,parents=[dict(sha=base),dict(sha=head)])
    def observe(self):return _relationships(self.run,self.workflow,self.listing,self.pr,self.merge,self.expected)
    def line(self):return ('2026-10-30T17:00:00.1234567Z '+self.fixture.observe()+'\n').encode()
    def parse(self,raw=None):
        return _log_identity(self.line() if raw is None else raw,self.fixture.candidate,self.fixture.requests,self.fixture.values,self.observe())
    def test_matching_records_and_line_are_only_observations(self):
        self.assertEqual(self.parse(),self.identity);self.assertEqual(self.observe()['step'],5)
        self.assertNotIn('publication_authorized',self.observe())
        self.assertFalse(self.fixture.candidate['publication_authorized'])
    def test_failed_rerun_wrong_head_and_boolean_identity_refuse(self):
        original=copy.deepcopy(self.run)
        for key,value in (('conclusion','failure'),('run_attempt',2),('head_sha','0'*40),('id',True)):
            self.run=dict(original,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):self.observe()
    def test_wrong_job_and_incomplete_or_extra_membership_refuse(self):
        self.job['id']=9
        with self.assertRaisesRegex(ValueError,'job'):self.observe()
        self.job['id']=2;self.listing['total_count']=2
        with self.assertRaisesRegex(ValueError,'single-job'):self.observe()
        self.listing['jobs'].append(copy.deepcopy(self.job))
        with self.assertRaisesRegex(ValueError,'single-job'):self.observe()
    def test_missing_skipped_duplicate_or_reordered_steps_refuse(self):
        original=copy.deepcopy(self.job['steps'])
        cases=[original[1:],list(reversed(original)),original+[copy.deepcopy(original[-1])]]
        skipped=copy.deepcopy(original);skipped[0]['conclusion']='skipped';cases.append(skipped)
        for steps in cases:
            self.job['steps']=steps
            with self.subTest(steps=steps),self.assertRaises(ValueError):self.observe()
    def test_pr_advance_to_M_or_changed_base_refuses(self):
        self.pr['head']['sha']=self.fixture.candidate['commit']
        with self.assertRaisesRegex(ValueError,'current-E'):self.observe()
        self.pr['head']['sha']=self.expected['executable'];self.pr['base']['sha']='0'*40
        with self.assertRaisesRegex(ValueError,'current-E'):self.observe()
    def test_tested_merge_wrong_order_refuses(self):
        self.merge['parents'].reverse()
        with self.assertRaisesRegex(ValueError,'tested-merge'):self.observe()
    def test_diagnostic_cannot_substitute_external_expectations_or_requests(self):
        raw=self.line();self.fixture.values['artifact_id']=3
        with self.assertRaisesRegex(ValueError,'exact-request-binding'):self.parse(raw)
        self.fixture.values['artifact_id']=2;rows=list(self.fixture.requests);rows[0],rows[1]=rows[1],rows[0];self.fixture.requests=tuple(rows)
        with self.assertRaisesRegex(ValueError,'exact-request-binding'):self.parse(raw)
    def test_duplicate_malformed_missing_or_oversize_logs_refuse(self):
        raw=self.line()
        for value in (raw+raw,raw.replace(b'2026-10-30T17:00:00.1234567Z ',b''),b'no observation',b'x'*(LIMIT+1)):
            with self.subTest(length=len(value)),self.assertRaises(ValueError):self.parse(value)
    def test_self_consistent_forged_service_identity_refuses(self):
        self.fixture.identity=dict(self.identity,job=9)
        with self.assertRaisesRegex(ValueError,'service-log-join'):self.parse()
    def test_scratch_without_active_workflow_refuses_before_api(self):
        root=Path(__file__).resolve().parents[1]
        self.assertFalse((root/REVIEW_WORKFLOW).exists())
        head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()
        values={k:self.fixture.values[k] for k in SCALARS};values['executable']=head
        with self.assertRaisesRegex(ValueError,'consumer-git-refused'):
            read_reviewed_publication(root,reviewer_run_id=1,reviewer_job_id=2,pr_number=471,
                base='a'*40,tested_merge='b'*40,values=values)
