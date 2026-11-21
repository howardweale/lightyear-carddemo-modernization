"""Inactive answer consumption message relations only; no authority or remote API.

These checks do not authenticate an annotated tag, establish process death,
create admission or authorize retry. The caller owns genuine reservation.
"""
import json,re
from .contracts import ExecutionContractError,canonical_hash

def consumption_message_bytes(record):
    fields={'schema','case_id','nonce_sha256','plan_sha256','decision_sha256',
        'trusted_journal_head','work_order_sha256','execution_policy_sha256','ci',
        'consumed_before_execution','execution_authorized','admission_receipt_issued','content_sha256'}
    if (type(record) is not dict or set(record)!=fields
            or record.get('schema')!='factory-human-drill-consumption/1'
            or record.get('case_id')!='answer-fragment'
            or record.get('consumed_before_execution') is not True
            or record.get('execution_authorized') is not False
            or record.get('admission_receipt_issued') is not False
            or type(record.get('ci')) is not dict):
        raise ExecutionContractError('configured-consumption-record-shape')
    for key in ('nonce_sha256','plan_sha256','decision_sha256','trusted_journal_head',
                'work_order_sha256','execution_policy_sha256','content_sha256'):
        if type(record[key]) is not str or re.fullmatch('[0-9a-f]{64}',record[key]) is None:
            raise ExecutionContractError('configured-consumption-digest-shape')
    if record['content_sha256']!=canonical_hash(record,{'content_sha256'}):
        raise ExecutionContractError('configured-consumption-record-digest')
    return json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def check_consumption_admission_relations(record,admission):
    # Pure relation predicate. Neither input can establish genuine admission.
    consumption_message_bytes(record)
    if (type(admission) is not dict
            or admission.get('consumption_record_sha256')!=record['content_sha256']
            or admission.get('consumed_ref')!='refs/tags/factory-human-drill-consumed-'+record['nonce_sha256']
            or type(admission.get('consumed_tag_object')) is not str
            or re.fullmatch('[0-9a-f]{40}',admission['consumed_tag_object']) is None
            or any(admission.get(k)!=record[k] for k in ('nonce_sha256','plan_sha256',
                'decision_sha256','trusted_journal_head','work_order_sha256','execution_policy_sha256','ci'))):
        raise ExecutionContractError('configured-consumption-admission-binding')
    return None
