"""Inactive configured role and reservation proposal; no CLI dispatch.

Production entries always obtain the genuine current human plan verification.
They accept no passed receipt, API injection, reverify callback or resume flag.
The existing atomic nonce namespace/algorithm and public entry are unchanged.
Reservation, if eventually approved and invoked, is irreversible consumption,
not permission to call a model. This module issues no machine credentials.
"""
import os

from .contracts import ExecutionContractError, canonical_hash
from .configured_human_admission import verify_configured_human_plan
from .tower_drill_reservation import _consume_verified_plan, _GitHubAPI


def verify_configured_human_role(admission,order,policy,role,action):
    # Verify the original human decision again for every role use. Do not accept
    # caller timestamps or policy-only authorization in place of a proof.
    review = verify_configured_human_plan(admission,order,policy)
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


def reserve_configured_human_plan(admission,order,policy):
    """Proposed sole configured consumption entry; never call before approval.

    This shared private algorithm has a separate synthetic unit-test boundary,
    but this production entry accepts only genuine Factory verifier arguments.
    Existing ref, ambiguous POST or changed proof stops without retry/resume.
    """
    review = verify_configured_human_plan(admission,order,policy)
    environment = {key:os.environ.get(key,'') for key in (
        'GITHUB_ACTIONS','GITHUB_REPOSITORY','GITHUB_EVENT_NAME',
        'GITHUB_RUN_ATTEMPT','GITHUB_RUN_ID','GITHUB_JOB')}
    return _consume_verified_plan(review,_GitHubAPI(),environment,
        lambda:verify_configured_human_plan(admission,order,policy))
