"""CI-only synthetic record relationships; not authenticated CI evidence."""
from copy import deepcopy
import unittest
from tools.ci.operator_flow_ci_prerequisite import validate_prior_component,REQUIRED_STEPS,REPOSITORY,WORKFLOW

class PriorComponentRecords(unittest.TestCase):
    def setUp(self):
        self.head='a'*40
        self.producer=dict(id=20,head_sha=self.head,event='workflow_dispatch',status='in_progress',run_attempt=1,
            head_repository={'full_name':REPOSITORY},created_at='2026-10-30T03:00:00Z')
        self.run=dict(id=10,head_sha=self.head,event='pull_request',status='completed',conclusion='success',run_attempt=1,
            head_repository={'full_name':REPOSITORY},workflow_id=7,created_at='2026-10-30T01:00:00Z')
        self.workflow=dict(id=7,path=WORKFLOW)
        self.job=dict(id=30,run_id=10,head_sha=self.head,name='operator-component',status='completed',conclusion='success',
            started_at='2026-10-30T01:01:00Z',completed_at='2026-10-30T02:00:00Z',
            steps=[dict(name=n,status='completed',conclusion='success') for n in REQUIRED_STEPS])
        self.listed=dict(total_count=1,jobs=[self.job])
    def check(self):
        return validate_prior_component(self.head,20,10,self.producer,self.run,self.workflow,self.listed)
    def test_relationship_result_contains_no_admission_authority(self):
        result=self.check()
        self.assertEqual(result['validation_run_id'],10)
        self.assertNotIn('execution_authorized',result)
    def test_wrong_head_or_repository_refuses(self):
        for key,value in (('head_sha','b'*40),('head_repository',{'full_name':'other/repo'})):
            before=deepcopy(self.run);self.run[key]=value
            with self.assertRaises(ValueError):self.check()
            self.run=before
    def test_nonterminal_failed_or_rerun_refuses(self):
        for key,value in (('status','in_progress'),('conclusion','failure'),('run_attempt',2),('run_attempt',True)):
            before=deepcopy(self.run);self.run[key]=value
            with self.assertRaises(ValueError):self.check()
            self.run=before
    def test_wrong_workflow_refuses(self):
        self.workflow['path']='.github/workflows/other.yml'
        with self.assertRaises(ValueError):self.check()
    def test_incomplete_or_extra_job_list_refuses(self):
        self.listed['total_count']=2
        with self.assertRaises(ValueError):self.check()
        self.listed['jobs'].append(deepcopy(self.job))
        with self.assertRaises(ValueError):self.check()
    def test_skipped_or_missing_source_guard_refuses(self):
        self.job['steps'][0]['conclusion']='skipped'
        with self.assertRaises(ValueError):self.check()
        self.job['steps'].pop(0)
        with self.assertRaises(ValueError):self.check()
    def test_duplicate_required_step_refuses(self):
        self.job['steps'].append(deepcopy(self.job['steps'][0]))
        with self.assertRaises(ValueError):self.check()
    def test_validation_finishing_after_producer_start_refuses(self):
        self.job['completed_at']='2026-10-30T03:00:01Z'
        with self.assertRaises(ValueError):self.check()
    def test_naive_timestamp_and_wrong_job_head_refuse(self):
        self.job['completed_at']='2026-10-30T02:00:00'
        with self.assertRaises(ValueError):self.check()
        self.job['completed_at']='2026-10-30T02:00:00Z';self.job['head_sha']='b'*40
        with self.assertRaises(ValueError):self.check()
