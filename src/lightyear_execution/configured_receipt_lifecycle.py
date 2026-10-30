"""Original receipt recorder/history binding; no qualification shortcut."""
from pathlib import Path
from lightyear_factory.contracts import ContractError
from lightyear_factory.model_admission import _bounded_regular_bytes
from .configured_human_lifecycle import original_scanner_relations


def verify_receipt_signer_inputs(controller):
    from lightyear_factory.authorship import CICommitSigner
    from .configured_receipt_materials import SIGNERS
    context=controller.execution_context
    paths=controller.candidate_signing_paths
    if type(paths) is not tuple or len(paths)!=2:
        raise ContractError('configured-receipt-native-signer-paths')
    workspace=controller.runs_root/'uncreated-signer-boundary'
    # The native constructor checks trusted-main and external RUNNER_TEMP
    # paths; it does not sign, generate, copy or open the private key contents.
    signer=CICommitSigner(*paths,workspace)
    for path in (signer.key_path,signer.allowed_signers):
        resolved=path.resolve()
        if (any(part.casefold()=='onedrive' for part in path.parts)
                or resolved.is_relative_to(Path(controller.source_root).resolve())
                or resolved.is_relative_to(controller.runs_root.resolve())):
            raise ContractError('configured-receipt-external-signer-only')
    expected=context._binding['public_materials'][SIGNERS]['raw'].encode('ascii')
    if _bounded_regular_bytes(signer.allowed_signers,4096,'configured-receipt-signer-trust')!=expected:
        raise ContractError('configured-receipt-signed-signer-trust-mismatch')


def verify_finalized_receipt_objects(controller,order):
    from .configured_receipt_controller import _CONTROLLERS,_ROUTERS
    from lightyear_factory.model_transport_records import ModelTransportRecorder
    from lightyear_factory.authorship import CandidateHistory,CICommitSigner
    context=controller.execution_context;saved=_CONTROLLERS.get(context)
    if saved is None or not saved.get('finalized'):return
    recorder=saved['recorder'];history=saved['history'];provider=_ROUTERS[context][1]
    if (type(recorder) is not ModelTransportRecorder or provider.transport_recorder is not recorder
            or recorder.store is not saved['artifacts'] or recorder.ledger is not saved['ledger']
            or recorder.isolation_scan is not saved['scanner'] or recorder.require_model_admission is not True
            or recorder.work_order_sha256!=order.content_sha256 or recorder.attempt!=1
            or recorder.key is not saved['transport_key']
            or recorder.key_id!=context._binding['public_materials']['key_id']
            or type(history) is not CandidateHistory or type(history.signer) is not CICommitSigner
            or history.workspace is not saved['workspace'] or history.ledger is not saved['ledger']
            or history.run_id!=saved['run_dir'].name
            or history.history!=saved['run_dir']/'candidate-history.git'
            or history.signer.key_path!=Path(controller.candidate_signing_paths[0]).absolute()
            or history.signer.allowed_signers!=Path(controller.candidate_signing_paths[1]).absolute()):
        raise ContractError('configured-receipt-original-recorder-history-changed')
    if saved['scanner_relations']!=original_scanner_relations(controller,order,saved['workspace'],saved['ledger'],controller.agents.isolation_scan):
        raise ContractError('configured-receipt-original-scanner-changed')


def finalize_receipt_controller(controller,order,workspace,artifacts,ledger,run_dir):
    from lightyear_factory.orchestrator import ArtifactStore
    from lightyear_factory.workspace import IsolatedWorkspace
    from lightyear_factory.model_transport_records import ModelTransportRecorder
    from lightyear_factory.authorship import CandidateHistory,CICommitSigner
    from .configured_receipt_controller import verify_configured_controller,_CONTROLLERS,_ROUTERS
    from .configured_receipt_terminal import capture_configured_terminal_origin,_original_callback_bindings
    verify_configured_controller(controller,order)
    context=controller.execution_context;saved=_CONTROLLERS.get(context)
    if (saved is None or saved['controller'] is not controller or saved['ledger'] is not ledger
            or saved['run_dir']!=Path(run_dir) or saved.get('finalized') is not False
            or context._controller_bound or type(workspace) is not IsolatedWorkspace
            or type(artifacts) is not ArtifactStore or artifacts.sequence!=0
            or artifacts.root!=Path(run_dir)/'artifacts' or artifacts.run_id!=Path(run_dir).name
            or workspace.root!=(Path(run_dir)/'workspace').resolve()
            or workspace.source_root!=Path(controller.source_root).resolve()
            or workspace.read_manifest!=context._manifest or workspace.allowed_paths!=order.allowed_paths):
        raise ContractError('configured-receipt-original-finalization-required')
    provider=_ROUTERS[context][1];budget=controller.agents.bounded_provider.budget
    if provider.transport_recorder is not None or provider._transport_started or budget.calls:
        raise ContractError('configured-receipt-recorder-reuse')
    scanner=controller.agents.isolation_scan
    relations=original_scanner_relations(controller,order,workspace,ledger,scanner)
    _original_callback_bindings(controller,budget)
    try:
        signer=CICommitSigner(*controller.candidate_signing_paths,workspace.root)
        key,key_id=context.lease_transport_key(controller,workspace,artifacts,ledger,run_dir)
        recorder=ModelTransportRecorder(artifacts,ledger,key=key,key_id=key_id,attempt=1,
            isolation_scan=scanner,work_order_sha256=order.content_sha256,require_model_admission=True)
        provider.bind_transport_recorder(recorder)
        # Original AccountedModelProvider remains bound to the same provider,
        # admission and physical callbacks; do not replace it with a new budget.
        history=CandidateHistory(workspace,Path(run_dir)/'candidate-history.git',artifacts.run_id,ledger,signer=signer)
        history.initialize()
        context._live();verify_receipt_signer_inputs(controller)
        # In-memory object identity only; never hash, serialize or persist key
        # material. This adds no zeroization or abrupt-crash assurance.
        saved.update(workspace=workspace,artifacts=artifacts,scanner=scanner,scanner_relations=relations,
            recorder=recorder,history=history,transport_key=key,finalized=True)
        verify_finalized_receipt_objects(controller,order)
        context._controller_bound=True
        capture_configured_terminal_origin(controller,order,ledger,run_dir)
        ledger.append('ACCEPTED','candidate_controller_bound',dict(run_id=artifacts.run_id,
            order_sha256=order.content_sha256,encryption_key_id=key_id,candidate_start=history.start_commit))
        return history,recorder
    except BaseException:
        context._controller_bound=False;context.close();raise
