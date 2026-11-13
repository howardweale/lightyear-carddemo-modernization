"""Fresh human-proof role scope checks; no machine-issued credential or grant.

The eventual execution context must combine this with its same-process one-use
reservation and actual OCI boundary. A returned scope record alone is not an
admission receipt, cannot resume a reservation, and never qualifies output.
"""
from datetime import datetime, timezone
from hashlib import sha256

from lightyear_factory.model_admission import FactoryModelAdmission
from .contracts import ExecutionContractError, ExecutionPolicy, canonical_hash
from .tower_drill_admission import verify_human_drill_plan


def verify_human_drill_role(admission, order, policy, role, action, *, now=None):
    if (type(admission) is not FactoryModelAdmission or type(policy) is not ExecutionPolicy
            or policy.signature_algorithm != 'FACTORY-TOWER-PROOF'
            or policy.allowed_secret_names or len(policy.trusted_key_ids) != 1
            or not isinstance(admission.public_key, bytes)
            or sha256(admission.public_key).hexdigest() != policy.trusted_key_ids[0]):
        raise ExecutionContractError('human-drill-public-trust-policy')
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ExecutionContractError('human-drill-timezone-required')
    # This rechecks the genuine signature, external current head, exact plan,
    # work order, source tree, caps and signed time window on EVERY role use.
    review = verify_human_drill_plan(admission, order, policy, now=current)
    if role not in policy.role_actions or action not in policy.role_actions[role]:
        raise ExecutionContractError('human-drill-role-action-refused')
    result = dict(schema='factory-human-drill-role-scope/1', status='verified-scope-only',
        execution_authorized=False, role=role, action=action,
        work_order_sha256=order.content_sha256, execution_policy_sha256=policy.content_sha256,
        public_key_sha256=policy.trusted_key_ids[0],
        plan_review_sha256=review['content_sha256'],
        plan_sha256=review['verified_model_admission']['plan_sha256'],
        decision_sha256=review['verified_model_admission']['decision_sha256'],
        trusted_journal_head=review['verified_model_admission']['trusted_journal_head'],
        nonce_sha256=review['drill_binding']['nonce_sha256'],
        credentials_issued=False, secrets_leased=False)
    result['content_sha256'] = canonical_hash(result)
    return result
