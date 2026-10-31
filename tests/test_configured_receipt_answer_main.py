"""CI-only synthetic identity relations; no API, signature or passed context."""
import os,unittest
from copy import deepcopy
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.configured_receipt_answer_identity import _validate_main_identity,REPOSITORY,WORKFLOW,JOB


class AnswerMainIdentityTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.head='a'*40
        self.binding={'ci':dict(repository=REPOSITORY,workflow_ref=REPOSITORY+'/'+WORKFLOW+'@'+'b'*40,job=JOB,run_attempt=1)}
        self.environment=dict(GITHUB_ACTIONS='true',GITHUB_REPOSITORY=REPOSITORY,GITHUB_REF='refs/heads/main',
            GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_SHA=self.head,GITHUB_WORKFLOW_SHA=self.head,
            GITHUB_WORKFLOW_REF=REPOSITORY+'/'+WORKFLOW+'@refs/heads/main',GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='123',GITHUB_JOB=JOB)
        self.run=dict(id=123,run_attempt=1,event='workflow_dispatch',status='in_progress',head_sha=self.head,
            head_branch='main',head_repository={'full_name':REPOSITORY},workflow_id=42)
        self.workflow=dict(id=42,path=WORKFLOW,state='active')
        self.jobs=dict(total_count=1,jobs=[dict(id=456,name=JOB,status='in_progress',head_sha=self.head,run_id=123)])
        self.main=dict(ref='refs/heads/main',object=dict(type='commit',sha=self.head))

    def relation(self):
        return _validate_main_identity(self.binding,self.head,self.environment,self.run,self.workflow,self.jobs,self.main)

    def test_distinct_signed_revision_and_current_metadata_head_are_retained(self):
        before=deepcopy(self.binding)
        result=self.relation()
        self.assertEqual(result['head_sha'],self.head)
        self.assertEqual(result['workflow_ref'],self.binding['ci']['workflow_ref'])
        self.assertEqual(self.binding,before)
        self.assertNotIn('status',result)
        self.assertEqual(JOB,'answer-fragment')
        self.assertEqual(WORKFLOW,'.github/workflows/p5-configured-answer-main.yml')
        from lightyear_execution.configured_human_main_identity import _validate_main_identity as control
        with self.assertRaises(ExecutionContractError):
            control(self.binding,self.head,self.environment,self.run,self.workflow,self.jobs,self.main)

    def test_pr_push_nonmain_and_retry_environment_refused(self):
        for key,value in (('GITHUB_EVENT_NAME','pull_request'),('GITHUB_EVENT_NAME','push'),
                ('GITHUB_REF','refs/heads/topic'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_WORKFLOW_SHA','c'*40)):
            with self.subTest(key=key,value=value):
                original=self.environment[key];self.environment[key]=value
                with self.assertRaises(ExecutionContractError):self.relation()
                self.environment[key]=original

    def test_remote_main_must_match_original_verified_head(self):
        self.main['object']['sha']='c'*40
        with self.assertRaises(ExecutionContractError):self.relation()

    def test_fork_and_api_event_cannot_supply_main_identity(self):
        self.run['head_repository']['full_name']='other/repository'
        with self.assertRaises(ExecutionContractError):self.relation()
        self.run['head_repository']['full_name']=REPOSITORY;self.run['event']='pull_request'
        with self.assertRaises(ExecutionContractError):self.relation()

    def test_wrong_workflow_or_boolean_id_refused(self):
        self.workflow['path']='.github/workflows/other.yml'
        with self.assertRaises(ExecutionContractError):self.relation()
        self.workflow['path']=WORKFLOW;self.run['id']=True
        with self.assertRaises(ExecutionContractError):self.relation()

    def test_partial_duplicate_or_terminal_job_refused(self):
        self.jobs['total_count']=2
        with self.assertRaises(ExecutionContractError):self.relation()
        self.jobs['jobs'].append(deepcopy(self.jobs['jobs'][0]))
        with self.assertRaises(ExecutionContractError):self.relation()
        self.jobs['jobs'].pop();self.jobs['total_count']=1;self.jobs['jobs'][0]['status']='completed'
        with self.assertRaises(ExecutionContractError):self.relation()

    def test_answer_identity_entry_refuses_asserted_review_before_environment_or_api(self):
        from lightyear_execution.configured_receipt_answer_main import review_answer_receipt_main_identity
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            review_answer_receipt_main_identity({'status':'passed'},object(),object())

    def test_answer_reservation_entry_refuses_asserted_review_before_environment_or_api(self):
        from lightyear_execution.configured_receipt_answer_main import reserve_answer_receipt_main_plan
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            reserve_answer_receipt_main_plan({'status':'passed'},object(),object())
