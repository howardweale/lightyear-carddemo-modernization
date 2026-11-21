"""Fixed native case selection, never a proof or admission authority.

The original native verifiers still validate the complete case/order/policy
binding. No caller-selected API, verifier, clock, callback or context class.
"""
from lightyear_factory.contracts import WorkOrder
from .contracts import ExecutionContractError

CONTROL='configured-build-control'
ANSWER='answer-fragment'

def is_answer_order(order):
    return type(order) is WorkOrder and order.order_id==ANSWER

def review_case(review):
    binding=review.get('drill_binding') if type(review) is dict else None
    case=binding.get('case_id') if type(binding) is dict else None
    if type(case) is not str or case not in (CONTROL,ANSWER):
        raise ExecutionContractError('configured-receipt-case-required')
    # Selection only. This does not authenticate an asserted review mapping.
    return case

def policy_parser(order):
    if is_answer_order(order):
        from .configured_receipt_answer_policy import parse_answer_receipt_policy
        return parse_answer_receipt_policy
    from .configured_receipt_policy import parse_configured_receipt_policy
    return parse_configured_receipt_policy

def plan_verifier(order):
    if is_answer_order(order):
        from .configured_receipt_answer_admission import verify_answer_receipt_plan
        return verify_answer_receipt_plan
    from .configured_receipt_admission import verify_configured_receipt_plan
    return verify_configured_receipt_plan

def role_verifier(order):
    if is_answer_order(order):
        from .configured_receipt_answer_scopes import verify_answer_receipt_role
        return verify_answer_receipt_role
    from .configured_receipt_scopes import verify_configured_receipt_role
    return verify_configured_receipt_role

def reservation_entry(case):
    if type(case) is not str:
        raise ExecutionContractError('configured-receipt-case-required')
    if case==ANSWER:
        from .configured_receipt_answer_main import reserve_answer_receipt_main_plan
        return reserve_answer_receipt_main_plan
    if case==CONTROL:
        from .configured_receipt_main import reserve_configured_receipt_main_plan
        return reserve_configured_receipt_main_plan
    raise ExecutionContractError('configured-receipt-case-required')

def consumption_tools(case):
    if type(case) is not str:
        raise ExecutionContractError('configured-receipt-case-required')
    if case==ANSWER:
        from .configured_receipt_answer_consumption_evidence import consumption_message_bytes,check_consumption_admission_relations
        from .configured_receipt_answer_consumption_observation import observe_existing_consumption
    elif case==CONTROL:
        from .configured_consumption_evidence import consumption_message_bytes,check_consumption_admission_relations
        from .configured_consumption_observation import observe_existing_consumption
    else:
        raise ExecutionContractError('configured-receipt-case-required')
    return consumption_message_bytes,check_consumption_admission_relations,observe_existing_consumption

def signer_path(case):
    if type(case) is not str:
        raise ExecutionContractError('configured-receipt-case-required')
    if case==ANSWER:
        from .configured_receipt_answer_materials import SIGNERS
    elif case==CONTROL:
        from .configured_receipt_materials import SIGNERS
    else:
        raise ExecutionContractError('configured-receipt-case-required')
    return SIGNERS
