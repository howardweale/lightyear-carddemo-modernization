"""Release original configured attempt references after terminal observation.

This is reference removal, not secure erasure, revocation, process-death
evidence or authority. Never detach the recorder or reopen a closed context.
"""
import os
from pathlib import Path
from lightyear_factory.contracts import ContractError


def release_closed_receipt_references(context, controller):
    from .configured_receipt_context import ConfiguredReceiptExecutionContext, _LIVE
    from .configured_receipt_controller import _CONTROLLERS, _ROUTERS
    from .configured_human_controller import _ROUTERS as public_routers
    from .configured_receipt_terminal import _ORIGINAL
    from .configured_receipt_security import _AUTH, _LEASES, _GATES, _PENDING
    from .configured_human_recorded_transport import _NATIVE
    from .configured_receipt_wire_boundary import _ATTEMPTED
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
    from lightyear_factory.model_transport_records import ModelTransportRecorder

    # No _live(), proof, environment credential read, callback or API reentry.
    if (type(context) is not ConfiguredReceiptExecutionContext
            or getattr(context, '_closed', None) is not True
            or getattr(context, '_pid', None) != os.getpid() or context in _LIVE):
        raise ContractError('configured-release-closed-original-process-required')
    bound = _CONTROLLERS.get(context)
    original = _ROUTERS.get(context)
    if controller is not None and (
            type(controller) is not FactoryOrchestrator
            or controller.execution_context is not context):
        raise ContractError('configured-release-controller-owner-mismatch')
    if bound is not None and bound['controller'] is not controller:
        raise ContractError('configured-release-bound-controller-mismatch')
    origin = None if controller is None else _ORIGINAL.get(controller)
    if origin is not None and origin['context']() is not context:
        raise ContractError('configured-release-terminal-owner-mismatch')
    provider = None if original is None else original[1]
    recorder = None
    if provider is not None:
        if (type(provider) is not SnapshotOpenAIResponsesProvider
                or provider._recorded_call_active is not False):
            raise ContractError('configured-release-original-provider-required')
        if controller is not None and controller.agents.provider is not original[0]:
            raise ContractError('configured-release-router-owner-mismatch')
        recorder = provider.transport_recorder
        if recorder is not None and type(recorder) is not ModelTransportRecorder:
            raise ContractError('configured-release-original-recorder-required')
        if bound is not None and bound.get('finalized') is True and (
                bound['recorder'] is not recorder):
            raise ContractError('configured-release-recorder-owner-mismatch')
        # Reject shared owners rather than clearing another attempt's state.
        if any(owner is not context and row[1] is provider
               for owner, row in list(_ROUTERS.items())):
            raise ContractError('configured-release-shared-provider-refused')
        if any(row[1] is provider for row in list(public_routers.values())):
            raise ContractError('configured-release-public-provider-refused')

    # Original terminal reading has already finished/refused in dispatcher.
    # Retain recorder attachment: setting transport_recorder=None would select
    # the unrecorded provider branch. Existing missing-registry checks refuse.
    if provider is not None:
        provider.api_key = ''
    if recorder is not None:
        recorder.key = None
    if controller is not None:
        _ORIGINAL.pop(controller, None)
    _CONTROLLERS.pop(context, None)
    _ROUTERS.pop(context, None)
    if provider is not None:
        _NATIVE.pop(provider, None)
        _ATTEMPTED.pop(provider, None)
    for registry in (_AUTH, _LEASES, _GATES, _PENDING):
        registry.pop(context, None)
    # _STARTED remains a weak-key Boolean tombstone. _LIVE stays absent and
    # _closed stays True. No nonce, invocation marker or admission is reset.
    # Original child environment, Python temporaries and traceback references
    # are outside this operation; no complete key-lifetime claim is made.


def require_no_retained_receipt_attempt(run_dir):
    """CI diagnostic on actual post-dispatch registries, never admission."""
    from .configured_receipt_controller import _CONTROLLERS, _ROUTERS
    from .configured_receipt_terminal import _ORIGINAL
    root = Path(run_dir)
    if not root.is_absolute() or not root.name.startswith('drill-'):
        raise ContractError('configured-release-exact-run-directory-required')
    if any(row['run_dir'] == root for row in list(_CONTROLLERS.values())):
        raise ContractError('configured-release-controller-still-retained')
    if any(row['run_dir'] == root for row in list(_ORIGINAL.values())):
        raise ContractError('configured-release-terminal-still-retained')
    if any('drill-' + context.admission_receipt['nonce_sha256'][:32] == root.name
           for context in list(_ROUTERS)):
        raise ContractError('configured-release-router-still-retained')
