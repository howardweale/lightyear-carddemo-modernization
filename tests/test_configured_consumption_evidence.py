"""CI-only structural message tests; synthetic records confer no authority."""
from copy import deepcopy
import json,unittest
from lightyear_execution.contracts import ExecutionContractError,canonical_hash
from lightyear_execution.configured_consumption_evidence import consumption_message_bytes,check_consumption_admission_relations

def sample():
    record=dict(schema='factory-human-drill-consumption/1',case_id='configured-build-control',
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

class ConsumptionMessageRelationsTests(unittest.TestCase):
    def test_serialization_matches_original_tag_message(self):
        record=sample()
        self.assertEqual(consumption_message_bytes(record),json.dumps(record,sort_keys=True,separators=(',',':')).encode())
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
