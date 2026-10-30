"""CI-only configured human dispatch proposal, with unchanged receipt schemas.

This isolated source is not authorization to consume, lease or execute. Inputs,
workflow wiring and positive integration evidence remain under exact review.
"""
import json
import os
from pathlib import Path

from lightyear_factory.contracts import ContractError,WorkOrder
from lightyear_factory.model_admission import FactoryModelAdmission,_bounded_regular_bytes
from .contracts import ExecutionPolicy
from .configured_human_context import _preflight,admit_configured_human_context
from .configured_human_admission import verify_configured_human_plan
from .configured_human_controller import create_configured_human_router
from .configured_human_terminal import read_original_configured_terminal
from .human_drill_dispatch import _fresh_directory,_public_path


def _independent_source(value):
    path=Path(value)
    if (not path.is_absolute() or not path.is_dir()
            or any(p.casefold()=='onedrive' for p in path.parts)
            or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)()
                   for p in (path,*path.parents))):
        raise ContractError('configured-dispatch-independent-source-required')
    metadata=path/'.git'
    if (not metadata.is_dir() or metadata.is_symlink()
            or getattr(metadata,'is_junction',lambda:False)()
            or (metadata/'commondir').exists()
            or (metadata/'objects/info/alternates').exists()
            or (metadata/'objects/info/http-alternates').exists()):
        raise ContractError('configured-dispatch-shared-git-refused')
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)()
           for p in (metadata/'objects',metadata/'objects/info')):
        raise ContractError('configured-dispatch-shared-git-refused')
    return path


def _prepare(args):
    from .backend import OCIContainerBackend
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise ContractError('configured-dispatch-ci-only')
    source=_independent_source(args.source_root)
    admission=FactoryModelAdmission.from_external_trust(source,args.factory_plan,
        args.factory_approval,args.factory_contract,args.factory_trust)
    order=WorkOrder.load(args.work_order)
    policy=ExecutionPolicy.from_configured_human_dict(json.loads(
        _bounded_regular_bytes(args.execution_policy,1024*1024,'configured-dispatch-policy')))
    review=verify_configured_human_plan(admission,order,policy)
    plan=admission._committed_json(admission.paths[0])
    inputs={key:admission.root/row['path'] for key,row in plan['bound_inputs'].items()}
    manifest=admission._committed_json(plan['bound_inputs']['workspace']['path'])
    isolation=_public_path(args.public_isolation_plan)
    backend=OCIContainerBackend(policy,args.execution_runtime,execute=True)
    # Backend construction is configuration only. All trust/input/workflow
    # checks precede root allocation, irreversible reservation and secret read.
    bound=_preflight(admission,order,policy,backend,admission.root,inputs,manifest,
                     args.model_config,isolation)
    if bound['review']!=review:
        raise ContractError('configured-dispatch-preflight-changed')
    return dict(admission=admission,order=order,policy=policy,backend=backend,
                inputs=inputs,manifest=manifest,isolation=isolation,review=review)


def review_configured_human_dispatch(args):
    # Existing verified-plan-only schema: never an execution/admission receipt.
    return _prepare(args)['review']


def _retain_original_terminal(root,controller):
    # Diagnostic failure cannot replace the original controller exception.
    # This method never retries proof, consumes a nonce or resumes a context.
    try:
        originals=read_original_configured_terminal(controller)
        destination=root/'terminal-originals'
        destination.mkdir(exist_ok=False)
        for name,raw in originals.items():
            with (destination/name).open('xb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
        return True
    except Exception:
        return False


def dispatch_configured_human(args):
    from lightyear_factory.agents import ModelAgentSet
    from lightyear_factory.orchestrator import FactoryOrchestrator
    bundle=_prepare(args)
    admission=bundle['admission'];order=bundle['order'];policy=bundle['policy']
    if any(p.casefold()=='onedrive' for p in Path(args.runs_root).parts):
        raise ContractError('configured-dispatch-onedrive-evidence-refused')
    root=_fresh_directory(args.runs_root,admission.root)
    run_id='drill-'+bundle['review']['drill_binding']['nonce_sha256'][:32]
    root.mkdir()
    context=None;controller=None
    try:
        context=admit_configured_human_context(admission,order,policy,bundle['backend'],
            source_root=admission.root,input_paths=bundle['inputs'],read_manifest=bundle['manifest'],
            model_config_path=args.model_config,public_isolation_path=bundle['isolation'],
            evidence_path=root/'human-admission.json')
        # Mirror only the already genuinely consumed digest for the unchanged,
        # abort-only reader. No local nonce file substitutes for remote consume.
        with (root/'admission-nonces.sha256').open('x',encoding='ascii',newline='\n') as stream:
            stream.write(context.admission_receipt['nonce_sha256']+'\n')
            stream.flush();os.fsync(stream.fileno())
        router=create_configured_human_router(context)
        controller=FactoryOrchestrator(admission.root,root,ModelAgentSet(router),
            execution_context=context,model_admission=admission,factory_input_paths=bundle['inputs'],
            workspace_read_manifest=bundle['manifest'],memory_store=None)
        # Existing native sequence owns baseline, planner, failure analyst,
        # builder, deterministic gates, shared accounting and original receipts.
        receipt=controller.run(order,run_id)
        if receipt.get('status')=='passed':
            from .configured_human_success import verify_original_configured_success
            verify_original_configured_success(controller)
        return receipt
    finally:
        if context is not None:context.close()
        if controller is not None:_retain_original_terminal(root,controller)
