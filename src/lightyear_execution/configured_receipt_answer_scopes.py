"""Inactive answer signed receipt-role scope review; no reservation or secret reads."""
from .contracts import ExecutionContractError,canonical_hash
from .configured_receipt_answer_admission import verify_answer_receipt_plan

def verify_answer_receipt_role(admission,order,policy,role,action):
    # Verify the original human decision again for every role use. Do not accept
    # caller timestamps or policy-only authorization in place of a proof.
    review = verify_answer_receipt_plan(admission,order,policy)
    if role not in policy.role_actions or action not in policy.role_actions[role]:
        raise ExecutionContractError('configured-human-role-action-refused')
    model = review['verified_model_admission']
    binding = review['drill_binding']
    result = dict(schema='factory-human-drill-role-scope/1',
        status='verified-scope-only',execution_authorized=False,role=role,action=action,
        work_order_sha256=order.content_sha256,execution_policy_sha256=policy.content_sha256,
        public_key_sha256=policy.trusted_key_ids[0],plan_review_sha256=review['content_sha256'],
        plan_sha256=model['plan_sha256'],decision_sha256=model['decision_sha256'],
        trusted_journal_head=model['trusted_journal_head'],nonce_sha256=binding['nonce_sha256'],
        credentials_issued=False,secrets_leased=False)
    result['content_sha256'] = canonical_hash(result)
    return result
