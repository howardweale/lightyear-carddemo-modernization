"""MS92 observed native lifecycle adapter; frozen before generation, no amendments."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from .contracts import canonical, read_json, require, seal, verify
from .journey_order import RUNS, archived, save, UNCLAIMED, file_hash
from .journey_runtime import JourneySigner, LocalRunner, JourneyAbort, run_folder, read_local, inventory
from .measured_judge import VERSION
from .observer_runtime import Observer
from lightyear_control_tower.decisions import verify_envelope
from lightyear_workflow.campaign_journals import signed_append, check
from lightyear_workflow.run_store import RunStore
from lightyear_workflow.run_index import RunIndex
from lightyear_workflow.convergence import INDEX_RELATIVE
REGISTER=Path('factory/idempiere/repeatability/comparison-register.json')
INVENTORY=Path('docs/calibration/idempiere-boundaries/mappings.json')
HARNESS='LightyearOperationsTest.java'


def native_plan(root,campaign,build,builder):
    from .measured_campaign import frozen
    cp=frozen(root,campaign)
    from tools.ms94_b06_engineering_boundary import refuse_engineering
    refuse_engineering(cp, campaign)
    refuse_engineering(builder, build)
    require(verify_envelope(builder,JourneySigner(root).public),'Builder signature differs')
    require(file_hash(build/'workspace'/HARNESS)==builder['harness_sha256'],'Candidate changed')
    for name,field in [('prompt.json','prompt_sha256'),('proposal.json','proposal_sha256'),('events.jsonl','events_sha256')]:
        require(file_hash(build/name)==builder[field],'Builder provenance changed')
    base=cp['base_plan']
    require(read_local(root)==base['local'],'Native environment changed')
    inv=inventory(root)
    require(inv['free_bytes']>=60*1024**3 and inv['memory_bytes']>=12*1024**3,'Insufficient native resources')
    declaration=read_json(root/cp['variant_input_dir']/'work-order.json')
    return seal({**{k:v for k,v in base.items() if k!='content_sha256'},
        'mode':'extend','cases':['operations'],'extension_declaration':declaration,'scenario':cp['scenario'],
        'extension_declaration_sha256':file_hash(root/cp['variant_input_dir']/'work-order.json'),
        'builder_receipt_sha256':builder['content_sha256'],'builder_directory':build.relative_to(root).as_posix(),
        'harness_sha256':builder['harness_sha256'],'model_calls':builder['provider_invocations'],
        'implementation_sha256':cp['implementation_sha256'],'judge_sha256':cp['judge_sha256'],
        'builder_client':cp['builder_client'],'campaign_directory':campaign.relative_to(root).as_posix(),
        'campaign_plan_sha256':cp['content_sha256'],'comparison_register_sha256':cp['comparison_register_sha256'],
        'assessed_on':cp['assessed_on'],'human_authored_repair_bytes':0})


def bounded_gate(runner):
    output=runner.run/'gate-logs/declared.log';output.parent.mkdir(exist_ok=True)
    args=[sys.executable,'-m','lightyear_calibration.measured_judge','--run',str(runner.run)]
    with output.open('wb') as stream:
        process=subprocess.Popen(args,cwd=runner.root,stdout=stream,stderr=subprocess.STDOUT,
            env={**os.environ,'PYTHONPATH':str(runner.root/'src'),'PYTHONUTF8':'1'})
        started=time.monotonic()
        try:
            while process.poll() is None:
                runner.check_cancel()
                if time.monotonic()-started>=1800:raise JourneyAbort('timeout')
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
        finally:
            if process.poll() is None:process.kill();process.wait()
    require(process.returncode==0,'Declared readback gate failed')
    value=read_json(runner.run/'gate.json');verify(value)
    require(value['plan_sha256']==runner.plan['content_sha256'],'Wrong gate plan')
    return value


def cleanup_owned(runner):
    # Captured observations/logs are retained; do not accumulate database volumes
    # or unbounded Oracle filesystem exports across a failure-rate experiment.
    value=runner.cleanup(retain=False)
    remaining=runner.owned('volume')
    return {**value,'remaining_volumes':remaining,'complete':value['complete'] and not remaining}


def execute_native(root, campaign, build, builder, remaining_seconds):
    plan=native_plan(root,campaign,build,builder)
    for path in (root/RUNS).glob('journey-*'):
        require((path/'receipt.json').exists() and read_json(path/'cleanup.json')['complete'],'An existing native run needs recovery')
    run=run_folder(root,'journey-'+uuid.uuid4().hex);run.mkdir(parents=True)
    signer=JourneySigner(root);save(run/'plan.json',plan);(run/'authority.public.pem').write_bytes(signer.public)
    inputs=archived(root);candidate=(build/'workspace'/HARNESS).read_bytes()
    for h in plan['declaration']['application']['harnesses']:inputs[h['id']+'.java']=(root/h['file']).read_bytes()
    inputs['operations.java']=candidate
    inputs['comparison-register.json']=(root/REGISTER).read_bytes()
    inputs['datatype-inventory.json']=(root/INVENTORY).read_bytes()
    plan['inputs_sha256']={name:hashlib.sha256(data).hexdigest() for name,data in inputs.items()}
    plan=seal({k:v for k,v in plan.items() if k!='content_sha256'})
    save(run/'plan.json',plan)
    (run/'inputs').mkdir()
    for name,data in inputs.items():(run/'inputs'/name).write_bytes(data)
    auth=signer.sign({'record_type':'native-journey-authorization','run_id':run.name,'plan':{'plan_sha256':plan['content_sha256']},
        'campaign_authorization_sha256':read_json(campaign/'authorization.json')['content_sha256'],
        'operator_authorization':'Fresh operations generation under the frozen MS92 judge/register/controller and separately approved campaign budget.'})
    save(run/'authorization.json',auth)
    kwargs={'cwd':root,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,
        'env':{**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}}
    if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
    else:kwargs['start_new_session']=True
    subprocess.Popen([sys.executable,'-m','lightyear_calibration.journey_runtime','watch',str(root),str(run),str(os.getpid())],**kwargs)
    store=RunStore(run/'journal');gate=None;error=None;started=time.monotonic();observers=[];active_observer=None
    def emit(kind,payload):return signed_append(store,signer,auth,kind,{k:v for k,v in payload.items() if k not in ('signature','content_sha256')},'journey')
    runner=LocalRunner(root,run,plan,emit);runner.deadline=min(runner.deadline,time.monotonic()+remaining_seconds)
    def interrupted(*_):raise JourneyAbort('cancelled')
    handlers={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM)}
    emit('started',{'mode':'extend','campaign_plan_sha256':plan['campaign_plan_sha256'],
        'judge_sha256':plan['judge_sha256'],'builder_client':plan['builder_client'],'human_authored_repair_bytes':0})
    print(json.dumps({'run_id':run.name,'stage':'native-started'}),flush=True)
    try:
        folder=runner.prepare('operations',1)
        save(run/'selected-attempts.json',{'operations':1})
        for lane in ('oracle','postgresql'):
            runner.checkpoint('execute-lane:operations:'+lane)
            if plan['scenario']=='operations':
                active_observer=Observer(runner,lane);observers.append(active_observer)
                active_observer.start()
            value=runner.worker('execute',{'lane':lane,'output':runner.inside(folder/'execution'/lane),
                'harness':'/output/inputs/operations.java','harness_sha256':plan['harness_sha256'],
                'test':'LightyearOperationsTest','source_commit':plan['declaration']['application']['source_commit'],'timeout_seconds':1200},timeout=1250)
            if active_observer:
                active_observer.stop();active_observer=None
            emit('native-execution',{'case':'operations','lane':lane,'exit_code':value['exit_code'],'execution_sha256':value['content_sha256']})
            if value['exit_code']:raise JourneyAbort('timeout' if value['exit_code']==124 else 'harness-exception')
            runner.worker('capture',{'lane':lane,'output':runner.inside(folder/'after'/lane)},timeout=1800)
        cleaned=cleanup_owned(runner);emit('pair-cleanup',cleaned);require(cleaned['complete'],'Cleanup failure')
        for observer in observers:
            observer.publish_after_application_stopped(folder/'observers'/observer.lane)
        runner.checkpoint('verify')
        gate=bounded_gate(runner);emit('gate',{'command':'verify-operations','passed':gate['passed'],'receipt_sha256':gate['content_sha256']})
        require(gate['passed'],'Business or equivalence gate failed')
        emit('result',{'case':'operations','boundary':{'model_calls':plan['model_calls']}})
    except Exception as exc:
        error={'classification':exc.code if isinstance(exc,JourneyAbort) else 'gate-failed','exception_type':type(exc).__name__}
        emit('exception',error)
    finally:
        if active_observer:
            try:active_observer.stop()
            except Exception:pass
        cleaned=cleanup_owned(runner)
        observer_integrity=True
        for observer in observers:
            destination=folder/'observers'/observer.lane
            try:
                from .transaction_observer import verify_capture
                verify_capture(observer.private/'capture')
                if cleaned['complete'] and not destination.exists():
                    observer.publish_after_application_stopped(destination)
            except Exception:
                observer_integrity=False
        cleanup=signer.sign({'artifact_type':'lightyear-journey-cleanup','run_id':run.name,'plan_sha256':plan['content_sha256'],**cleaned})
        save(run/'cleanup.json',cleanup);emit('cleanup',cleanup)
        if not cleaned['complete']:error={'classification':'cleanup-failure'}
        passed=bool(gate and gate['passed'] and error is None and observer_integrity)
        receipt=signer.sign({'artifact_type':'lightyear-native-journey-run','run_id':run.name,'mode':'extend',
            'plan_sha256':plan['content_sha256'],'declaration_sha256':plan['extension_declaration_sha256'],
            'status':'passed-bounded-observed-journey-equivalence' if passed else 'failed','reason':'native-judge-completed',
            'builder_receipt_sha256':builder['content_sha256'],'agent_generated':True,'model_calls':plan['model_calls'],
            'known_findings_reproduced':False,'bounded_operations_equivalence':False,'bounded_partial_invoicing_equivalence':False,'bounded_declared_operations_equivalence':False,'bounded_observed_journey_equivalence':passed,'scenario':plan['scenario'],
            'executed_cases':['operations'],'inherited_cases':[],'human_interventions_outside_designed_stops':sum(e['type']=='intervention' for e in store.events()),
            'unattended_run':False,'unattended_extension':passed,'human_authored_repair_bytes':0,
            'judge_sha256':plan['judge_sha256'],'builder_client':plan['builder_client'],'comparison_register_sha256':plan['comparison_register_sha256'],
            'observer_capture_integrity':observer_integrity,'judge_version':VERSION,'campaign_directory':plan['campaign_directory'],'cleanup_sha256':cleanup['content_sha256'],
            'elapsed_seconds':round(time.monotonic()-started,3),'requests':[],'error':error,'cloud_resources_started':False,**UNCLAIMED})
        emit('halted',receipt);save(run/'receipt.json',receipt)
        try:events=check(store.events(),auth,signer.public,'journey')
        finally:store.close()
        archive=run/(run.name+'.json.gz');archive.write_bytes(gzip.compress(canonical({'events':events}),mtime=0))
        RunIndex(root/INDEX_RELATIVE).record(run.name,'idempiere','ms92-measured-factory',events,archive);save(run/'journal.json',events)
        for sig,handler in handlers.items():signal.signal(sig,handler)
    return run,receipt

