"""CI-only structural message tests; synthetic records confer no authority."""
from copy import deepcopy
import json,unittest,os
from lightyear_execution.contracts import ExecutionContractError,canonical_hash
from lightyear_execution.configured_receipt_answer_consumption_evidence import consumption_message_bytes,check_consumption_admission_relations

def sample():
    record=dict(schema='factory-human-drill-consumption/1',case_id='answer-fragment',
        nonce_sha256='a'*64,plan_sha256='b'*64,decision_sha256='c'*64,
        trusted_journal_head='d'*64,work_order_sha256='e'*64,execution_policy_sha256='f'*64,
        ci={'synthetic':True},consumed_before_execution=True,execution_authorized=False,
        admission_receipt_issued=False)
    record['content_sha256']=canonical_hash(record)
    return record

def joined(record):
    admission={k:deepcopy(record[k]) for k in ('nonce_sha256','plan_sha256','decision_sha256',
        'trusted_journal_head','work_order_sha256','execution_policy_sha256','ci')}
    admission.update(consumption_record_sha256=record['content_sha256'],
        consumed_ref='refs/tags/factory-human-drill-consumed-'+record['nonce_sha256'],consumed_tag_object='1'*40)
    return admission

class AnswerConsumptionMessageRelationsTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_serialization_matches_original_tag_message(self):
        record=sample()
        self.assertEqual(consumption_message_bytes(record),json.dumps(record,sort_keys=True,separators=(',',':')).encode())
        from lightyear_execution.configured_consumption_evidence import consumption_message_bytes as control
        with self.assertRaises(ExecutionContractError):control(record)
    def test_relations_return_no_authority(self):
        record=sample();self.assertIsNone(check_consumption_admission_relations(record,joined(record)))
    def test_changed_record_digest_refused(self):
        record=sample();record['plan_sha256']='9'*64
        with self.assertRaises(ExecutionContractError):consumption_message_bytes(record)
    def test_extra_record_field_refused(self):
        record=sample();record['resume']=True
        with self.assertRaises(ExecutionContractError):consumption_message_bytes(record)
    def test_integer_false_refused(self):
        record=sample();record['execution_authorized']=0;record['content_sha256']=canonical_hash(record,{'content_sha256'})
        with self.assertRaises(ExecutionContractError):consumption_message_bytes(record)
    def test_every_admission_join_refuses_substitution(self):
        record=sample()
        for key in joined(record):
            with self.subTest(key=key):
                admission=joined(record);admission[key]='substituted'
                with self.assertRaises(ExecutionContractError):check_consumption_admission_relations(record,admission)

    def test_answer_identity_refuses_cross_case_workflow_job_ids_and_extra_fields(self):
        from lightyear_execution import configured_receipt_answer_consumption_observation as observation
        ci=dict(repository=observation.REPOSITORY,run_id=11,run_attempt=1,job=observation.JOB,
            job_id=12,workflow_id=13,workflow_ref=observation.REPOSITORY+'/'+observation.WORKFLOW+'@'+'2'*40,head_sha='1'*40)
        record=sample();record['ci']=deepcopy(ci)
        self.assertEqual(observation._identity(record),ci)
        for key,value in (('job','configured-build-control'),('workflow_ref',ci['workflow_ref'].replace('p5-configured-answer-main','p5-configured-human-main')),
                          ('run_id',True),('job_id',0),('workflow_id',10**20),('run_attempt',2),('head_sha','x'*40),('extra',True)):
            changed=deepcopy(record);changed['ci'][key]=value
            with self.subTest(key=key),self.assertRaises(ExecutionContractError):observation._identity(changed)

    def test_invalid_record_stops_before_service_and_public_entry_has_no_api_argument(self):
        from lightyear_execution import configured_receipt_answer_consumption_observation as observation
        record=sample();admission=joined(record)
        # Deliberately unusable object: any service access would raise AttributeError.
        with self.assertRaisesRegex(ExecutionContractError,'identity-shape'):
            observation._observe_consumption(record,admission,object())
        changed=deepcopy(record);changed['case_id']='configured-build-control'
        changed['content_sha256']=canonical_hash(changed,{'content_sha256'})
        with self.assertRaisesRegex(ExecutionContractError,'record-shape'):
            observation._observe_consumption(changed,joined(changed),object())
        with self.assertRaises(TypeError):
            observation.observe_existing_consumption(record,admission,api=object())
