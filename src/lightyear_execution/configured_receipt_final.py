"""Supply original configured objects to the unchanged final build verifier."""
from pathlib import Path
from lightyear_factory.contracts import ContractError


def original_receipt_budget(controller,order,ledger,run_dir):
    from lightyear_factory.routing import RoutedBudget
    from lightyear_factory.budgeted_providers import AccountedModelProvider
    from lightyear_factory.model_transport_records import ModelTransportRecorder
    from .configured_receipt_controller import verify_configured_controller,_CONTROLLERS,_ROUTERS
    from .configured_receipt_terminal import _require_origin
    verify_configured_controller(controller,order);origin=_require_origin(controller)
    context=controller.execution_context;saved=_CONTROLLERS[context]
    routed=controller.agents.bounded_provider
    if type(routed) is not RoutedBudget:raise ContractError('configured-receipt-original-routing-budget')
    bound=routed.budget;provider=_ROUTERS[context][1];transport=provider.transport_recorder
    if (type(bound) is not AccountedModelProvider or bound.provider is not provider or bound.order is not order
            or routed.router is not controller.agents.provider or origin['budget']() is not bound
            or saved['run_dir']!=Path(run_dir) or saved['ledger'] is not ledger
            or type(transport) is not ModelTransportRecorder or transport is not saved['recorder']
            or transport.ledger is not ledger or transport.store is not saved['artifacts']
            or transport.pending is not None or transport.admitted_call is not None or transport.failed
            or transport.require_model_admission is not True):
        raise ContractError('configured-receipt-original-final-binding-required')
    return bound
