"""Draft CI-only public-proof dispatch. No keys, signing, model API or resume."""
from hashlib import sha256
import json
import os
from pathlib import Path,PurePosixPath

from lightyear_factory.contracts import ContractError,WorkOrder,canonical_hash
from lightyear_factory.model_admission import FactoryModelAdmission,_bounded_regular_bytes
from .contracts import ExecutionPolicy
from .tower_drill_admission import verify_human_drill_plan
from .public_drill_outputs import review_public_drill_outputs, require_public_contract_source


def _public_path(path):
    value=PurePosixPath(str(path))
    if (value.is_absolute() or '..' in value.parts or '\\' in str(path)
            or not str(value).startswith('docs/factory/p5-human-clean-control/') or value.suffix!='.json'):
        raise ContractError('human-drill-public-input-path')
    return str(value)


def load_public_isolation(admission,order,policy,manifest,path):
    review=verify_human_drill_plan(admission,order,policy);path=_public_path(path)
    plan=admission._committed_json(admission.paths[0]);binding=plan.get('public_drill_isolation')
    if (type(binding) is not dict or set(binding)!={'path','sha256'} or binding['path']!=path
            or path in manifest):
        raise ContractError('human-drill-public-isolation-binding')
    require_public_contract_source(admission._committed_json(admission.paths[2]), binding)
    value=admission._committed_json(path)
    raw=_bounded_regular_bytes(admission.root/path,65536,'human-drill-public-isolation-file')
    if (sha256(raw).hexdigest()!=binding['sha256']
            or type(value) is not dict or set(value)!={'schema','case_id','work_order_sha256','values','content_sha256'}
            or value['schema']!='factory-public-drill-isolation/1'
            or value['case_id']!=review['drill_binding']['case_id']
            or value['work_order_sha256']!=order.content_sha256
            or value['content_sha256']!=canonical_hash(value,{'content_sha256'})
            or type(value['values']) is not list or not 3<=len(value['values'])<=32
            or any(type(v) is not str or len(''.join(v.casefold().split()))<40 for v in value['values'])
            or len(set(value['values']))!=len(value['values'])):
        raise ContractError('human-drill-public-isolation-content')
    return tuple(value['values'])


def validate_public_domain(order,manifest,output_path,isolation_path):
    prefix='tests/fixtures/p5_public/'
    def safe(path):
        if type(path) is not str:return False
        p=PurePosixPath(path)
        return (not p.is_absolute() and '..' not in p.parts
                and '\\' not in path and path.startswith(prefix) and str(p)==path)
    if (type(manifest) is not dict or not manifest or not order.allowed_paths
            or any(not safe(p) for p in [*manifest,*order.allowed_paths])
            or any(p not in manifest for p in order.allowed_paths)
            or output_path in manifest or isolation_path in manifest
            or order.allow_network or type(order.max_attempts) is not int or order.max_attempts!=1
            or order.metadata.get('graph','packed')!='packed' or order.metadata.get('graph_policy')
            or order.metadata.get('context_schema','1.0')!='1.0' or order.graph_node_ids):
        raise ContractError('human-drill-public-workspace-only')


def _fresh_directory(path,source):
    p=Path(path)
    if (not p.is_absolute() or p.exists() or not p.parent.is_dir()
            or p.resolve().is_relative_to(source.resolve())):
        raise ContractError('human-drill-new-external-evidence-directory-required')
    if any(x.is_symlink() or getattr(x,'is_junction',lambda:False)() for x in (p,*p.parents)):
        raise ContractError('human-drill-evidence-link')
    return p


def _write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
        stream.flush();os.fsync(stream.fileno())


def dispatch_human_drill(args):
    from lightyear_factory.agents import ModelAgentSet
    from lightyear_factory.orchestrator import FactoryOrchestrator
    from .backend import OCIContainerBackend
    from .tower_drill_context import admit_human_drill_context
    from .public_drill_runtime import PublicDrillProvider
    if os.environ.get('GITHUB_ACTIONS')!='true':raise ContractError('human-drill-ci-only')
    admission=FactoryModelAdmission.from_external_trust(args.source_root,args.factory_plan,
        args.factory_approval,args.factory_contract,args.factory_trust)
    order=WorkOrder.load(args.work_order);policy=ExecutionPolicy.load(args.execution_policy)
    review=verify_human_drill_plan(admission,order,policy)
    plan=admission._committed_json(admission.paths[0])
    inputs={key:admission.root/row['path'] for key,row in plan['bound_inputs'].items()}
    runtime=admission.verify_runtime(order,source_root=admission.root,input_paths=inputs,policy=policy)
    manifest=runtime['workspace_read_manifest']
    output_path=_public_path(args.public_output_plan);isolation_path=_public_path(args.public_isolation_plan)
    validate_public_domain(order,manifest,output_path,isolation_path)
    review_public_drill_outputs(admission,order,policy,output_path)
    load_public_isolation(admission,order,policy,manifest,isolation_path)
    script=admission._committed_json(output_path)
    root=_fresh_directory(args.runs_root,admission.root)
    run_id='drill-'+review['drill_binding']['nonce_sha256'][:32]
    # All read-only preflight happens before allocation or irreversible consume.
    root.mkdir()
    context=None
    try:
        context=admit_human_drill_context(admission,order,policy,
            OCIContainerBackend(policy,args.execution_runtime,execute=True),source_root=admission.root,
            input_paths=inputs,read_manifest=manifest,evidence_path=root/'human-admission.json',
            public_output_plan=output_path,public_isolation_plan=isolation_path)
        # Mirror the already consumed digest for the existing abort-only recovery
        # reader. This does not replace the atomic, cross-job consumed ref.
        with (root/'admission-nonces.sha256').open('x',encoding='ascii',newline='\n') as stream:
            stream.write(context.admission_receipt['nonce_sha256']+'\n');stream.flush();os.fsync(stream.fileno())
        provider=PublicDrillProvider(context,script)
        controller=FactoryOrchestrator(admission.root,root,ModelAgentSet(provider),
            execution_context=context,model_admission=admission,factory_input_paths=inputs,
            workspace_read_manifest=manifest,memory_store=None)
        failure=False
        try:receipt=controller.run(order,run_id)
        except ContractError:
            failure=True
            receipt=json.loads(_bounded_regular_bytes(root/run_id/'receipt.json',1024*1024,'human-drill-blocked-receipt'))
        provenance=provider.provenance(receipt)
        _write(root/'controller-output-provenance.json',provenance)
        result=dict(schema='factory-human-drill-dispatch/1',run_id=run_id,controller_status=receipt['status'],
            controller_raised_refusal=failure,receipt_sha256=receipt['content_sha256'],
            provenance_sha256=provenance['content_sha256'],external_model_calls=0,signatures_created=0,
            production_qualified=False,qualifies_for_factory_receipt=False,
            gaps=['full-production-build-receipt-route-not-integrated'])
        result['content_sha256']=canonical_hash(result);_write(root/'dispatch-summary.json',result)
        return result
    finally:
        if context is not None:context.close()
