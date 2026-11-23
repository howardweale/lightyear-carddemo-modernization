"""Inactive answer-policy main identity and shared atomic nonce reservation.

Reservation consumes the original global nonce once. Never invoke without the
separate exact execution approval. No context/receipt input grants authority.
"""
from .contracts import ExecutionContractError
from .configured_receipt_answer_identity import _main_environment,_read_main_ci_identity
from .configured_receipt_answer_reservation import _consume_verified_answer_main_plan
from .tower_drill_reservation import _GitHubAPI

def review_answer_receipt_main_identity(admission,order,policy):
    from .configured_receipt_answer_admission import verify_answer_receipt_plan
    from .tower_drill_context import _workflow_source
    from .tower_drill_reservation import _GitHubAPI
    review=verify_answer_receipt_plan(admission,order,policy)
    environment=_main_environment()
    # Current verified HEAD may contain only the permitted proof metadata delta
    # from the original signed executable. Preserve both revisions unchanged.
    head=review['verified_model_admission']['executable_commit']
    identity=_read_main_ci_identity(review['drill_binding'],head,_GitHubAPI(),environment)
    source=_workflow_source(admission.root,review,environment)
    if (_main_environment()!=environment or verify_answer_receipt_plan(admission,order,policy)!=review):
        raise ExecutionContractError('configured-main-fresh-binding-changed')
    return dict(identity=identity,workflow_source=source,execution_authorized=False,
        nonce_consumed=False,secrets_leased=False,signing_authorized=False)


def reserve_answer_receipt_main_plan(admission,order,policy):
    # No caller-provided API, environment, review, reverify callback, old claim
    # or resume flag is accepted at this production boundary.
    from .configured_receipt_answer_admission import verify_answer_receipt_plan
    from .configured_receipt_answer_identity import _main_environment
    from .tower_drill_context import _workflow_source
    review=verify_answer_receipt_plan(admission,order,policy)
    environment=_main_environment()
    source=_workflow_source(admission.root,review,environment)
    def reverify():
        if (_main_environment()!=environment
                or _workflow_source(admission.root,review,environment)!=source):
            raise ExecutionContractError('configured-main-consumption-source-or-environment-changed')
        # Actual clock and original proof are verified last, after workflow IO.
        return verify_answer_receipt_plan(admission,order,policy)
    return _consume_verified_answer_main_plan(review,_GitHubAPI(),environment,reverify)
