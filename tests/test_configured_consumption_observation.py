"""CI-only synthetic GET relations; no genuine reservation or passed authority."""
from copy import deepcopy
import os,unittest
from unittest.mock import patch
from lightyear_execution.contracts import ExecutionContractError,canonical_hash
from lightyear_execution.configured_consumption_evidence import consumption_message_bytes
from lightyear_execution import configured_consumption_observation as module

def sample():
    ci=dict(repository=module.REPOSITORY,run_id=11,run_attempt=1,job=module.JOB,job_id=12,
        workflow_id=13,workflow_ref=module.REPOSITORY+'/'+module.WORKFLOW+'@'+'2'*40,head_sha='1'*40)
    record=dict(schema='factory-human-drill-consumption/1',case_id='configured-build-control',
        nonce_sha256='a'*64,plan_sha256='b'*64,decision_sha256='c'*64,trusted_journal_head='d'*64,
        work_order_sha256='e'*64,execution_policy_sha256='f'*64,ci=ci,
        consumed_before_execution=True,execution_authorized=False,admission_receipt_issued=False)
    record['content_sha256']=canonical_hash(record)
    admission={k:deepcopy(record[k]) for k in ('nonce_sha256','plan_sha256','decision_sha256',
        'trusted_journal_head','work_order_sha256','execution_policy_sha256','ci')}
    name='factory-human-drill-consumed-'+record['nonce_sha256']
    admission.update(consumption_record_sha256=record['content_sha256'],consumed_ref='refs/tags/'+name,
        consumed_tag_object='3'*40)
    ref=dict(ref=admission['consumed_ref'],object={'type':'tag','sha':'3'*40})
    tag=dict(sha='3'*40,tag=name,message=consumption_message_bytes(record).decode(),
        object={'type':'commit','sha':'1'*40,'url':'https://api.github.com'+module.PREFIX+'/git/commits/'+'1'*40})
    run=dict(id=11,run_attempt=1,workflow_id=13,event='workflow_dispatch',head_branch='main',
        head_sha='1'*40,status='completed',conclusion='failure',head_repository={'full_name':module.REPOSITORY})
    workflow=dict(id=13,path=module.WORKFLOW)
    job=dict(id=12,run_id=11,name=module.JOB,head_sha='1'*40,status='completed',conclusion='failure')
    responses=[ref,tag,run,workflow,job,deepcopy(ref),deepcopy(tag)]
    return record,admission,responses

class FakeAPI:
    def __init__(self,rows):self.rows=deepcopy(rows);self.calls=[]
    def request(self,method,path):
        if method!='GET' or not path.startswith(module.PREFIX+'/'):raise AssertionError('write-or-scope')
        self.calls.append((method,path));return self.rows.pop(0)

class ConsumptionObservationTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_matching_service_documents_remain_observations_only(self):
        record,admission,rows=sample();api=FakeAPI(rows)
        result=module._observe_consumption(record,admission,api)
        self.assertEqual(set(result),{'ref','tag','run','workflow','job'})
        self.assertEqual(result['job']['conclusion'],'failure')
        self.assertEqual(len(api.calls),7)
        self.assertTrue(all(method=='GET' for method,path in api.calls))

    def test_tag_message_and_target_substitution_refused(self):
        for key,value in (('message','forged'),('object',{'type':'commit','sha':'4'*40}),('sha','5'*40)):
            with self.subTest(key=key):
                record,admission,rows=sample();rows[1][key]=value
                with self.assertRaises(ExecutionContractError):module._observe_consumption(record,admission,FakeAPI(rows))

    def test_ref_change_during_observation_refused(self):
        record,admission,rows=sample();rows[5]['object']['sha']='4'*40
        with self.assertRaisesRegex(ExecutionContractError,'tag-changed'):
            module._observe_consumption(record,admission,FakeAPI(rows))

    def test_job_or_run_reentry_and_other_repository_refused(self):
        for index,key,value in ((2,'run_attempt',2),(4,'run_id',99),(4,'name','other'),(2,'head_repository',{'full_name':'other/repo'})):
            with self.subTest(index=index,key=key):
                record,admission,rows=sample();rows[index][key]=value
                with self.assertRaises(ExecutionContractError):module._observe_consumption(record,admission,FakeAPI(rows))

    def test_bad_identity_refuses_before_service(self):
        record,admission,rows=sample();record['ci']['run_id']=True
        record['content_sha256']=canonical_hash(record,{'content_sha256'})
        admission['ci']=deepcopy(record['ci']);admission['consumption_record_sha256']=record['content_sha256']
        api=FakeAPI(rows)
        with self.assertRaises(ExecutionContractError):module._observe_consumption(record,admission,api)
        self.assertEqual(api.calls,[])

    def test_production_entry_rejects_caller_api(self):
        record,admission,rows=sample()
        with self.assertRaises(TypeError):module.observe_existing_consumption(record,admission,api=FakeAPI(rows))

    def test_abort_original_mutation_across_service_read_refused(self):
        from lightyear_execution import configured_abort_evidence as abort
        from lightyear_factory.contracts import ContractError
        raw={'human-consumption.json':b'{}','human-admission.json':b'{}'}
        with patch.object(abort,'read_abort_candidate_files',side_effect=[raw,dict(raw,changed=b'changed')]),patch.object(module,'observe_existing_consumption',return_value={'synthetic':True}):
            with self.assertRaisesRegex(ContractError,'changed-during-service-read'):
                abort.read_abort_candidate_observations('synthetic-unused-root')
