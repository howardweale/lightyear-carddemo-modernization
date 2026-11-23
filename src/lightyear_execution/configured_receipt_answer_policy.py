"""Inactive answer-fragment policy parser; structural scope, never authority.

Use the existing receipt scope validator without widening its fixed control ID.
No new serialized policy shape, context, input pack or workflow is introduced.
"""
from copy import deepcopy
from dataclasses import replace
from .contracts import ExecutionContractError
from .configured_receipt_policy import POLICY_ID as CONTROL_POLICY_ID, parse_configured_receipt_policy

POLICY_ID = 'lightyear:configured-receipt:answer-fragment'


def parse_answer_receipt_policy(payload):
    if type(payload) is not dict or payload.get('id') != POLICY_ID:
        raise ExecutionContractError('configured-answer-policy-exact-id')
    original = deepcopy(payload)
    projected = deepcopy(original)
    projected['id'] = CONTROL_POLICY_ID
    parsed = parse_configured_receipt_policy(projected)
    result = replace(parsed, policy_id=POLICY_ID)
    if result.to_dict() != original:
        raise ExecutionContractError('configured-answer-policy-lossy-roundtrip')
    return result
