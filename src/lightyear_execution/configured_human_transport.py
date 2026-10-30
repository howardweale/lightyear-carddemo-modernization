"""Configured-only freshness gate before the original physical reservation.

No replacement transport, authority, receipt or count-bound acceptance. This
checks admission before starting each count/generation request; it does not
cancel an already in-flight request or establish final provider billing.
"""
import time
from datetime import datetime,timezone
from lightyear_factory.contracts import ContractError


def configured_transport_action(reservation,model,sequence):
    # Pure scope validation. Returning an action is never admission.
    actions={'planner':'factory:plan','failure_analyst':'factory:analyze-failure',
             'builder':'factory:build'}
    if (type(reservation) is not dict or reservation.get('role') not in actions
            or reservation.get('provider')!='openai-responses'
            or reservation.get('model')!=model
            or reservation.get('transport_kind') not in ('input-token-count','responses')
            or type(reservation.get('provider_attempt')) is not int
            or reservation['provider_attempt']!=1
            or type(reservation.get('invocation')) is not dict
            or type(reservation['invocation'].get('call_sequence')) is not int
            or reservation['invocation']['call_sequence']!=sequence):
        raise ContractError('configured-transport-scope-refused')
    return actions[reservation['role']]


def require_configured_transport(controller,reservation):
    from .configured_human_controller import verify_configured_controller,_CONTROLLERS
    from .configured_human_context import ConfiguredHumanExecutionContext
    from lightyear_factory.orchestrator import FactoryOrchestrator
    if type(controller) is not FactoryOrchestrator:
        raise ContractError('configured-transport-native-controller-required')
    context=controller.execution_context
    if type(context) is not ConfiguredHumanExecutionContext:
        raise ContractError('configured-transport-native-context-required')
    verify_configured_controller(controller,context._order)
    saved=_CONTROLLERS.get(context)
    if (saved is None or saved['controller'] is not controller
            or not context._controller_bound
            or saved['journal'] is not controller._receipt_journal
            or saved['identity_sha256']!=controller._receipt_identity['content_sha256']):
        raise ContractError('configured-transport-original-controller-required')
    budget=controller.agents.bounded_provider.budget
    action=configured_transport_action(reservation,budget.provider.model,len(budget.calls)+1)
    # Includes genuine current proof, role, workflow and input revalidation.
    # authorize ignores its compatibility timestamp and uses current UTC.
    context.authorize(reservation['role'],action,datetime.now(timezone.utc).isoformat())
    # Hashing above can take time. Check the native original run clock last.
    if time.monotonic()>=controller._receipt_started+context._order.max_elapsed_seconds:
        raise ContractError('configured-transport-elapsed-deadline')
