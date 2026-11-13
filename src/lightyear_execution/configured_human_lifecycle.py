"""Finalize original configured controller objects before any role authorization.

This is source-level identity checking inside the reviewed process, not remote
attestation. No authority, replacement receipt, key lease or qualification.
"""
from pathlib import Path
from types import CodeType,FunctionType
from lightyear_factory.contracts import ContractError


def original_scanner_relations(controller,order,workspace,ledger,scanner):
    # No scanner invocation or live-proof call: also safe for terminal identity
    # comparisons after expiry. A returned tuple alone cannot register origin.
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from lightyear_factory.workspace import IsolatedWorkspace
    from lightyear_factory.ledger import RunLedger
    from lightyear_factory.isolation_scan import scan
    if (type(controller) is not FactoryOrchestrator or type(workspace) is not IsolatedWorkspace
            or type(ledger) is not RunLedger or type(scanner) is not FunctionType):
        raise ContractError('configured-lifecycle-original-scanner-types')
    method=FactoryOrchestrator._bind_isolation_scan
    codes={c.co_name:c for c in method.__code__.co_consts if type(c) is CodeType}
    if scanner.__code__ is not codes.get('inspect'):
        raise ContractError('configured-lifecycle-native-scanner-code')
    def cells(function):
        return dict(zip(function.__code__.co_freevars,(cell.cell_contents for cell in function.__closure__ or ())))
    bound=cells(scanner);expected=bound.get('expected_values')
    if (bound.get('self') is not controller or bound.get('ledger') is not ledger
            or bound.get('scan') is not scan or type(bound.get('canaries')) is not dict
            or bound['canaries']!=workspace.canaries
            or type(expected) is not FunctionType or expected.__code__ is not codes.get('expected_values')):
        raise ContractError('configured-lifecycle-original-scanner-closure')
    values=cells(expected)
    if (values.get('self') is not controller or values.get('order') is not order
            or values.get('workspace') is not workspace):
        raise ContractError('configured-lifecycle-original-values-closure')
    return scanner,expected


def finalize_configured_controller(controller,order,workspace,artifacts,ledger,run_dir):
    from lightyear_factory.orchestrator import ArtifactStore
    from lightyear_factory.workspace import IsolatedWorkspace
    from .configured_human_controller import verify_configured_controller,_CONTROLLERS,_ROUTERS
    from .configured_human_terminal import capture_configured_terminal_origin,_original_callback_bindings
    verify_configured_controller(controller,order)
    context=controller.execution_context;saved=_CONTROLLERS.get(context)
    if (saved is None or saved['controller'] is not controller or saved['ledger'] is not ledger
            or saved['run_dir']!=Path(run_dir) or context._controller_bound
            or saved.get('finalized') is not False
            or type(workspace) is not IsolatedWorkspace or type(artifacts) is not ArtifactStore
            or workspace.root!=(Path(run_dir)/'workspace').resolve()
            or workspace.source_root!=Path(controller.source_root).resolve()
            or workspace.read_manifest!=context._manifest
            or workspace.allowed_paths!=order.allowed_paths
            or artifacts.root!=Path(run_dir)/'artifacts' or artifacts.run_id!=Path(run_dir).name
            or artifacts.sequence!=0 or not workspace.root.is_dir()):
        raise ContractError('configured-lifecycle-original-finalization-required')
    provider=_ROUTERS[context][1];budget=controller.agents.bounded_provider.budget
    # The current exact provider-only policy grants no encryption-key scope.
    # A later coherent receipt-policy route must bind its recorder here through
    # a genuine scoped lease, never by injecting an optional controller field.
    if (provider.transport_recorder is not None or controller.transport_encryption is not None
            or budget.calls or provider._transport_started):
        raise ContractError('configured-lifecycle-unapproved-recorder-or-started-call')
    scanner=controller.agents.isolation_scan
    relations=original_scanner_relations(controller,order,workspace,ledger,scanner)
    _original_callback_bindings(controller,budget)
    saved.update(workspace=workspace,artifacts=artifacts,scanner=scanner,scanner_relations=relations,finalized=True)
    context._controller_bound=True
    try:
        capture_configured_terminal_origin(controller,order,ledger,run_dir)
    except BaseException:
        context._controller_bound=False
        context.close()
        raise
