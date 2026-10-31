"""CI-only synthetic service model; no genuine authority or GitHub side effects."""
import os,unittest
from copy import deepcopy
from unittest.mock import patch
from test_tower_drill_reservation import SyntheticAPI
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.tower_drill_reservation import _consume_verified_plan,_PREFIX,_REPOSITORY
from lightyear_execution.configured_human_main_identity import WORKFLOW,JOB
from lightyear_execution.configured_human_main_reservation import _consume_verified_main_plan,reserve_configured_main_plan


class SyntheticMainAPI(SyntheticAPI):
    def __init__(self):
        super().__init__()
        self.run.update(event='workflow_dispatch',head_branch='main')
        self.jobs['jobs'][0]['name']=JOB
        self.workflow.update(id=9,path=WORKFLOW,state='active')
        self.main=dict(ref='refs/heads/main',object=dict(type='commit',sha='d'*40))
        self.advance_after_create=False

    def request(self,method,path,payload=None):
        if method=='GET' and path==_PREFIX+'/git/ref/heads/main':
            self.calls.append((method,path,deepcopy(payload)))
            return deepcopy(self.main)
        result=super().request(method,path,payload)
        if self.advance_after_create and method=='POST' and path==_PREFIX+'/git/refs':
            self.main['object']['sha']='f'*40
        return result


class ConfiguredMainReservationTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        guard=patch('lightyear_execution.tower_drill_reservation.subprocess.run',side_effect=AssertionError('No actual subprocess'))
        guard.start();self.addCleanup(guard.stop)
        self.api=SyntheticMainAPI()
        self.env=dict(GITHUB_ACTIONS='true',GITHUB_REPOSITORY=_REPOSITORY,GITHUB_EVENT_NAME='workflow_dispatch',
            GITHUB_REF='refs/heads/main',GITHUB_SHA='d'*40,GITHUB_WORKFLOW_SHA='d'*40,
            GITHUB_WORKFLOW_REF=_REPOSITORY+'/'+WORKFLOW+'@refs/heads/main',GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='123',GITHUB_JOB=JOB)
        self.review=dict(status='verified-plan-only',execution_authorized=False,nonce_consumed=False,
            drill_binding=dict(case_id='configured-build-control',nonce_sha256='c'*64,work_order_sha256='a'*64,
                execution_policy_sha256='b'*64,ci=dict(repository=_REPOSITORY,workflow_ref=_REPOSITORY+'/'+WORKFLOW+'@'+'e'*40,job=JOB,run_attempt=1)),
            verified_model_admission=dict(executable_commit='d'*40,plan_sha256='1'*64,decision_sha256='2'*64,trusted_journal_head='3'*64))

    def reserve(self,reverify=None):
        return _consume_verified_main_plan(self.review,self.api,self.env,reverify or (lambda:deepcopy(self.review)))

    def writes(self):return [row for row in self.api.calls if row[0]!='GET']

    def test_same_create_once_protocol_is_non_authorizing(self):
        result=self.reserve()
        self.assertEqual(result['ref'],'refs/tags/factory-human-drill-consumed-'+'c'*64)
        self.assertEqual(result['status'],'consumed-only')
        self.assertIs(result['execution_authorized'],False);self.assertIs(result['admission_receipt_issued'],False)
        self.assertEqual([row[:2] for row in self.writes()],[('POST',_PREFIX+'/git/tags'),('POST',_PREFIX+'/git/refs')])
        self.assertEqual(result['record']['ci']['head_sha'],'d'*40)

    def test_existing_pr_claim_blocks_main_even_for_changed_plan(self):
        prior=SyntheticAPI()
        old=deepcopy(self.review)
        old['drill_binding']['ci'].update(workflow_ref=_REPOSITORY+'/.github/workflows/p5-factory-drills.yml@'+'e'*40,job='disposable-drills')
        env=dict(GITHUB_ACTIONS='true',GITHUB_REPOSITORY=_REPOSITORY,GITHUB_EVENT_NAME='pull_request',GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='123',GITHUB_JOB='disposable-drills')
        _consume_verified_plan(old,prior,env,lambda:deepcopy(old))
        self.api.tags=deepcopy(prior.tags);self.api.refs=deepcopy(prior.refs)
        refs=deepcopy(self.api.refs);self.review['verified_model_admission']['plan_sha256']='4'*64
        with self.assertRaisesRegex(ExecutionContractError,'existing-ref'):self.reserve()
        self.assertEqual(self.api.refs,refs)
        self.assertTrue(all(row[0]=='POST' for row in self.writes()))

    def test_ambiguous_create_stops_without_probe_or_retry(self):
        self.api.ambiguous_ref=True
        with self.assertRaisesRegex(ExecutionContractError,'timeout-after-create'):self.reserve()
        self.assertEqual(len(self.writes()),2);self.assertEqual(len(self.api.refs),1)
        self.assertEqual(self.api.calls[-1][:2],('POST',_PREFIX+'/git/refs'))

    def test_changed_main_before_consumption_writes_nothing(self):
        self.api.main['object']['sha']='f'*40
        with self.assertRaises(ExecutionContractError):self.reserve()
        self.assertEqual(self.writes(),[])

    def test_changed_main_after_create_preserves_consumption_and_refuses(self):
        self.api.advance_after_create=True
        with self.assertRaises(ExecutionContractError):self.reserve()
        self.assertEqual(len(self.api.refs),1);self.assertEqual(len(self.writes()),2)

    def test_changed_proof_before_and_after_never_returns_authority(self):
        changed=deepcopy(self.review);changed['verified_model_admission']['trusted_journal_head']='5'*64
        with self.assertRaisesRegex(ExecutionContractError,'plan-or-trust-changed'):self.reserve(lambda:changed)
        self.assertEqual(self.writes(),[])
        values=iter([self.review,changed])
        with self.assertRaisesRegex(ExecutionContractError,'stop-consumed'):self.reserve(lambda:next(values))
        self.assertEqual(len(self.api.refs),1)

    def test_public_entry_refuses_supplied_status_before_api(self):
        with patch('lightyear_execution.configured_human_main_reservation._GitHubAPI') as api:
            with self.assertRaises(ExecutionContractError):reserve_configured_main_plan({'status':'passed'},object(),object())
            api.assert_not_called()
