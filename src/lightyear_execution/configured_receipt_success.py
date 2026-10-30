"""Check original configured-control success relations without granting qualification.

The pure checker accepts synthetic data for CI relation tests, never authority.
Only the wrapper obtains original same-process controller objects and bytes.
Neither entry creates a receipt, proof, resume token or billing acceptance.
"""
from lightyear_factory.contracts import ContractError,canonical_hash
from .configured_receipt_terminal import (
    _require_origin,_original_json,_ledger_bytes,read_original_configured_terminal)


def check_successful_call_relations(calls,transports,model):
    roles=('planner','failure_analyst','builder')
    if type(calls) is not list or len(calls)!=3 or type(transports) is not list or len(transports)!=6:
        raise ContractError('configured-success-three-call-six-send-relations')
    for sequence,(call,role) in enumerate(zip(calls,roles),1):
        if (type(call) is not dict or call.get('content_sha256')!=canonical_hash(call,{'content_sha256'})
                or call.get('provider')!='openai-responses' or call.get('model')!=model
                or call.get('role')!=role or type(call.get('call_sequence')) is not int
                or call['call_sequence']!=sequence or call.get('status')=='failed'
                or call.get('usage')=='reserved-upper-bound'
                or call.get('input_token_preflight') is not True
                or call.get('attempts')!=1 or type(call.get('attempts')) is not int
                or call.get('retry_count')!=0 or type(call.get('retry_count')) is not int
                or call.get('token_count_attempts')!=1 or type(call.get('token_count_attempts')) is not int
                or call.get('token_count_retry_count')!=0 or type(call.get('token_count_retry_count')) is not int
                or call.get('routing',{}).get('fallback') is not False
                or call.get('billing_policy',{}).get('observed_service_tier')!='flex'
                or call.get('billing_policy',{}).get('billing_final') is not False):
            raise ContractError('configured-success-native-call-relations')
        count,generation=transports[2*(sequence-1):2*sequence]
        for row,kind in ((count,'input-token-count'),(generation,'responses')):
            reservation=row['reservation'];observed=row['observation']
            if (reservation['transport_kind']!=kind or reservation['provider']!='openai-responses'
                    or reservation['model']!=model or reservation['role']!=role
                    or reservation['invocation']['call_sequence']!=sequence
                    or type(reservation['provider_attempt']) is not int or reservation['provider_attempt']!=1
                    or type(observed) is not dict or observed.get('outcome')!='returned'):
                raise ContractError('configured-success-physical-call-relations')
        if (count['reservation']['invocation']!=generation['reservation']['invocation']
                or call.get('token_count_request_sha256')!=count['reservation']['canonical_request_sha256']
                or call.get('request_sha256')!=generation['reservation']['canonical_request_sha256']
                or call.get('input_tokens_preflight')!=count['observation'].get('input_token_count')
                or any(call.get(key)!=generation['observation']['response_usage'].get(key)
                       for key in ('input_tokens','output_tokens'))):
            raise ContractError('configured-success-request-usage-relations')
    # Deliberately no pass/authority/qualification record returned.


def verify_original_configured_success(controller):
    from lightyear_factory.orchestrator import _reconcile_accounting_journal
    saved=_require_origin(controller)
    original=read_original_configured_terminal(controller)
    receipt=_original_json(original['receipt.json']);context=controller.execution_context
    order=context._order;budget=saved['budget']()
    if (receipt.get('status')!='passed' or receipt.get('work_order_id')!='configured-build-control'
            or type(receipt.get('attempts')) is not int or receipt['attempts']!=1
            or receipt.get('changed_paths')!=list(order.allowed_paths)
            or receipt.get('verification',{}).get('status')!='passed'
            or [row.get('id') for row in receipt['verification']['gates']]!=['public-arithmetic']
            or any(row.get('status')!='passed' for row in receipt['verification']['gates'])):
        raise ContractError('configured-success-original-control-outcome')
    events=_ledger_bytes(original['attempt-accounting.jsonl'])
    replay=_reconcile_accounting_journal(events,saved['identity_sha256'])
    if (events[0]['payload'].get('protocol')!=5 or replay.get('calls')!=3
            or replay.get('in_flight_final_usage')!='none'
            or any(replay.get(key) for key in ('unresolved_model_transports',
                'uncheckpointed_model_transports','reserved_in_flight'))
            or receipt.get('count_financial_accounting')!=replay.get('count_financial_accounting')):
        raise ContractError('configured-success-original-accounting-relations')
    check_successful_call_relations(budget.calls,replay['model_transport_accounting'],budget.provider.model)
    intelligence=receipt['intelligence']
    if (intelligence.get('calls')!=3
            or intelligence.get('call_evidence_sha256')!=[c['content_sha256'] for c in budget.calls]
            or canonical_hash(intelligence,{'content_sha256'})!=intelligence.get('content_sha256')):
        raise ContractError('configured-success-original-intelligence-relations')
    _require_origin(controller)
    if read_original_configured_terminal(controller)!=original:
        raise ContractError('configured-success-original-bytes-changed')
    # Original receipt stays byte-identical. This is not strict qualification,
    # tokenization-bound acceptance or final provider billing verification.
