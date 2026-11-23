"""Unsigned configured-case formatter; no proof, fixed model output or execution.

Planner/analyst/builder invocations and responses are produced by the native
controller at execution time. This formatter binds inputs, never invents them.
"""
import argparse
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

DOCUMENTS='docs/factory/p5-human-clean-control/configured-build-control/'
WORKER='tests/fixtures/p5_public/human-public-build-control/worker.py'
WORKER_SHA256='db4d559f1badcf6a6473d6ade51fd463f91b814f67d1a7b3bc20f31076d3d47a'
REPOSITORY='howardweale/lightyear-carddemo-modernization'


def require(value,reason):
    if not value:raise ValueError(reason)


def _review_workflow_entry(raw,job):
    # Text consistency only. Native main identity and committed-workflow proof
    # remain mandatory; this does not authenticate a workflow or run it.
    require(type(raw) is bytes and job=='configured-build-control',
            'configured-pack-reviewed-workflow-job')
    jobs=re.findall(rb'^  configured-build-control:[ \t]*\r?$',raw,re.M)
    commands=re.findall(rb'^ +python -B -m ([A-Za-z0-9_.]+)(?:[ \t]|\r?$)',raw,re.M)
    require(len(jobs)==1 and commands.count(b'tools.ci.p5_configured_receipt_supervisor')==1
            and b'tools.ci.p5_configured_receipt_positive' not in commands,
            'configured-pack-reviewed-workflow-job')


def build_unsigned_documents(order,policy,models,executable,bound,isolation,model_binding,
                             order_binding,observer_sha256,window,nonce_sha256,workflow,job,public_bindings):
    from lightyear_factory.contracts import canonical_hash
    from lightyear_control_tower.factory_policy import validate_contract
    from lightyear_execution.configured_human_models import validate_control_model_document
    from lightyear_execution.configured_receipt_admission import _validate_configured_binding
    from lightyear_execution.configured_receipt_policy import parse_configured_receipt_policy
    require(type(executable) is str and re.fullmatch('[0-9a-f]{40}',executable), 'configured-pack-executable')
    require(type(nonce_sha256) is str and re.fullmatch('[0-9a-f]{64}',nonce_sha256),'configured-pack-nonce')
    require(type(window) is dict and set(window)=={'start','end'},'configured-pack-window')
    start,end=(datetime.fromisoformat(window[k]) for k in ('start','end'))
    require(start.tzinfo is not None and end.tzinfo is not None
            and 0<(end-start).total_seconds()<=policy.max_work_order_ttl_seconds,'configured-pack-window')
    require(order.order_id=='configured-build-control' and order.baseline_first is True
        and order.max_attempts==1 and order.max_model_calls==3 and order.max_model_cost_usd==10.0
        and not order.allow_network and order.allowed_paths==(WORKER,) and order.graph_node_ids==()
        and len(order.gates)==1 and order.gates[0].gate_id=='public-arithmetic'
        and order.gates[0].command==('python3',WORKER) and order.gates[0].timeout_seconds==60
        and order.gates[0].expose_output_to_builder is False,'configured-pack-case-scope')
    require(parse_configured_receipt_policy(policy.to_dict()).to_dict()==policy.to_dict(),
            'configured-pack-human-policy')
    require(workflow=='.github/workflows/p5-configured-human-main.yml'
        and job=='configured-build-control',
        'configured-pack-workflow')
    names={'scope':'scope.json','freeze':'freeze.json','workspace':'workspace.json',
           'execution_policy':'receipt-execution-policy.json'}
    require(type(bound) is dict and set(bound)==set(names),'configured-pack-inputs')
    for row,name in [*((bound[k],v) for k,v in names.items()),(isolation,'public-isolation.json'),
                     (model_binding,'models.json'),(order_binding,'work-order.json')]:
        require(type(row) is dict and set(row)=={'path','sha256'} and row['path']==DOCUMENTS+name
            and re.fullmatch('[0-9a-f]{64}',row['sha256']),'configured-pack-input')
    from lightyear_execution.configured_receipt_materials import SIGNERS,KEY_ID
    require(type(public_bindings) is dict and set(public_bindings)=={SIGNERS,KEY_ID},
            'configured-receipt-pack-public-bindings')
    for path,row in public_bindings.items():
        require(type(row) is dict and set(row)=={'path','sha256'} and row['path']==path
                and re.fullmatch('[0-9a-f]{64}',row['sha256']),
                'configured-receipt-pack-public-binding')
    require(re.fullmatch('[0-9a-f]{64}',observer_sha256),'configured-pack-observer')
    model=models['models'][models['default']]['model']
    roles={role:dict(provider='openai-responses',model=model) for role in ('planner','analyst','builder')}
    validate_control_model_document(models,roles)
    caps=dict(max_attempts=1,max_repair_loops=1,max_elapsed_seconds=order.max_elapsed_seconds,
              max_model_calls=3,max_model_tokens=order.max_model_tokens,cost_cap_microusd=10000000)
    binding=dict(schema='factory-human-drill-admission/1',case_id='configured-build-control',
        nonce_sha256=nonce_sha256,work_order_sha256=order.content_sha256,
        execution_policy_sha256=policy.content_sha256,
        role_actions={r:list(a) for r,a in policy.role_actions.items()},
        ci=dict(repository=REPOSITORY,workflow_ref=REPOSITORY+'/'+workflow+'@'+executable,
                job=job,run_attempt=1),stub_only=False,external_model_calls=3,max_attempts=1)
    _validate_configured_binding(binding,order,policy,executable)
    plan=dict(schema='factory-build-plan/1',work_order_sha256=order.content_sha256,
        executable_commit=executable,caps=caps,bound_inputs=bound,roles=roles,
        public_drill_isolation=isolation,drill_admission=binding)
    plan['content_sha256']=canonical_hash(plan)
    contract=dict(schema='factory-contract/1',kind='engineering-run-approval',program='factory',
        sources=[dict(row,commit=executable) for row in [*bound.values(),isolation,model_binding,order_binding,*public_bindings.values()]],
        details=dict(executable_commit=executable,request_seal=plan['content_sha256'],
            observer_sha256=observer_sha256,class_hashes={'PublicArithmeticWorker':WORKER_SHA256},
            window=window,caps=caps))
    validate_contract(contract,check_evidence=False)
    return plan,contract


def prepare(root,executable,window,nonce_sha256,workflow,job):
    require(os.environ.get('GITHUB_ACTIONS')=='true','configured-pack-ci-only')
    from lightyear_factory.contracts import WorkOrder
    from lightyear_execution.configured_receipt_policy import parse_configured_receipt_policy
    from lightyear_execution.configured_human_isolation import validate_configured_isolation_document
    from lightyear_execution.configured_human_dispatch import _independent_source
    from lightyear_control_tower.decisions import canonical
    root=_independent_source(root)
    command=['git','--no-optional-locks','-C',str(root)]
    def git(*args):return subprocess.check_output(command+list(args))
    require(git('rev-parse','HEAD').decode().strip()==executable
        and not git('status','--porcelain=v1','--untracked-files=all'),'configured-pack-clean-head')
    def committed(relative):
        path=root/relative
        require(path.is_file() and path.stat().st_nlink==1 and path.stat().st_size<=1048576
            and all(not p.is_symlink() and not getattr(p,'is_junction',lambda:False)()
                    for p in (path,*path.parents)),'configured-pack-regular-input')
        raw=path.read_bytes()
        require(raw==git('show',executable+':'+relative),'configured-pack-committed-input')
        return raw
    def binding(relative):return dict(path=relative,sha256=sha256(committed(relative)).hexdigest())
    order_doc=json.loads(committed(DOCUMENTS+'work-order.json'));order=WorkOrder.from_dict(order_doc)
    require(order.to_dict()==order_doc,'configured-pack-normalized-order')
    policy=parse_configured_receipt_policy(json.loads(committed(DOCUMENTS+'receipt-execution-policy.json')))
    models=json.loads(committed(DOCUMENTS+'models.json'))
    require(sha256(committed(WORKER)).hexdigest()==WORKER_SHA256,'configured-pack-original-worker')
    require(json.loads(committed(DOCUMENTS+'workspace.json'))=={WORKER:WORKER_SHA256},
            'configured-pack-original-workspace')
    isolation=json.loads(committed(DOCUMENTS+'public-isolation.json'))
    validate_configured_isolation_document(isolation,order.content_sha256)
    workflow_raw=committed(workflow)
    _review_workflow_entry(workflow_raw,job)
    bound={k:binding(DOCUMENTS+n) for k,n in [('scope','scope.json'),('freeze','freeze.json'),
        ('workspace','workspace.json'),('execution_policy','receipt-execution-policy.json')]}
    from lightyear_execution.configured_receipt_materials import SIGNERS,KEY_ID,validate_public_material_bytes
    validate_public_material_bytes(committed(SIGNERS),committed(KEY_ID))
    public_bindings={path:binding(path) for path in (SIGNERS,KEY_ID)}
    plan,contract=build_unsigned_documents(order,policy,models,executable,bound,
        binding(DOCUMENTS+'public-isolation.json'),binding(DOCUMENTS+'models.json'),
        binding(DOCUMENTS+'work-order.json'),sha256(committed('src/lightyear_execution/configured_receipt_dispatch.py')).hexdigest(),
        window,nonce_sha256,workflow,job,public_bindings)
    require(git('rev-parse','HEAD').decode().strip()==executable
        and not git('status','--porcelain=v1','--untracked-files=all'),'configured-pack-source-changed')
    return {'plan.json':canonical(plan),'contract.json':canonical(contract)}


def main(argv=None):
    require(os.environ.get('GITHUB_ACTIONS')=='true','configured-pack-ci-only')
    parser=argparse.ArgumentParser(allow_abbrev=False)
    for name in ('source-root','output','executable','start','end','nonce-sha256','workflow','job'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(args.source_root);target=Path(args.output)
    require(target.is_absolute() and not target.exists() and target.parent.is_dir()
        and not target.resolve().is_relative_to(root.resolve())
        and not any(p.casefold()=='onedrive' for p in target.parts)
        and all(not p.is_symlink() and not getattr(p,'is_junction',lambda:False)()
                for p in (target,*target.parents)),'configured-pack-new-external-output')
    values=prepare(root,args.executable,dict(start=args.start,end=args.end),args.nonce_sha256,args.workflow,args.job)
    target.mkdir()
    for name,raw in values.items():
        with (target/name).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return 0


if __name__=='__main__':raise SystemExit(main())
