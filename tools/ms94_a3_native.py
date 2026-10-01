"""Native qualification equipment; no builder calls, no autonomous-success credit."""
from datetime import date
import hashlib,json,os,subprocess,sys,time,uuid
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,require,seal
from lightyear_calibration.journey_order import archived,save,RUNS,file_hash
from tools.ms94_signer_v5 import JourneySigner
from lightyear_calibration.measured_native import cleanup_owned,REGISTER,INVENTORY
from lightyear_calibration.qualification_observer_runtime_v4 import Observer
from tools.ms94_v6_gate import evaluate,VERSION,EQUIPMENT_REVISION
from tools.ms94_a3_controls import CONTROLS as CONTROL_FAULTS,assess,control
from tools.qualification_feedback_v4 import export,equipment_suspect

AREA=Path('factory/idempiere/qualification-ms94-v3')


def qualify(root,output,fault,equipment_plan,remaining_seconds,checkpoint_profile):
    from tools.ms94_execution_snapshot import guard
    from lightyear_calibration.contracts import verify
    guard(root);verify(equipment_plan)
    require(fault in CONTROL_FAULTS,'Unknown planted control')
    for name,expected in equipment_plan['implementation_sha256'].items():
        require(file_hash(root/name)==expected,'Frozen qualification implementation changed')
    require(not output.exists() and output.resolve().is_relative_to(root.resolve()),'Use a new qualification directory')
    scenario='operations';profile=fault;isolated_application=True
    source,manifest=control(root,fault)
    require(file_hash(source)==manifest['harness_sha256'],'Planted source changed')
    register_path=REGISTER
    judge_version=VERSION
    from tools.ms94_a3_private_runner import A3Runner
    runner_type=A3Runner
    extra_tools=[root/'tools/qualification_private_runner.py',root/'tools/qualification_application_worker.py',
                 root/AREA/'public/JourneySupport.java',root/AREA/'public/operations-shapes.json']
    run=root/RUNS/('journey-'+uuid.uuid4().hex);run.mkdir(parents=True);output.mkdir(parents=True)
    signer=JourneySigner(root);plan=json.loads(json.dumps(equipment_plan['base_plan']))
    plan['implementation_sha256']=dict(equipment_plan['implementation_sha256'])
    inputs=archived(root);inputs['operations.java']=source.read_bytes()
    inputs['JourneySupport.java']=(root/AREA/'public/JourneySupport.java').read_bytes()
    if manifest['test_only_support_change']:
        inputs['JourneySupport.java']=source.read_text(encoding='utf-8').split('final class JourneySupport {',1)[1].encode('utf-8')
        inputs['JourneySupport.java']=b'final class JourneySupport {'+inputs['JourneySupport.java']
    inputs['invoice-type-contract.json']=(root/'factory/idempiere/qualification-ms94-v5/public/operations-shapes.json').read_bytes()
    inputs['history-bound.json']=(root/AREA/'private/history-bound.json').read_bytes()
    inputs['comparison-register.json']=(root/register_path).read_bytes()
    inputs['datatype-inventory.json']=(root/INVENTORY).read_bytes()
    require(checkpoint_profile in ('admitted','perturbed'),'Unknown checkpoint profile')
    if checkpoint_profile=='perturbed':
        for lane in ('oracle','postgresql'):
            inputs[lane+'-admitted-entry-multisets.json']=inputs[lane+'-entry-multisets.json']
        for name,relative in equipment_plan['private_checkpoint_inputs'].items():
            require(file_hash(root/relative)==equipment_plan['private_checkpoint_input_sha256'][name], 'Private checkpoint input changed')
            inputs[name]=(root/relative).read_bytes()
    plan=seal({**{k:v for k,v in plan.items() if k!='content_sha256'},
        'a3_checkpoint_profile':checkpoint_profile,
        'a3_preparation_verification_sha256':equipment_plan['preparation_verification_sha256'],
        'qualification_only':True,'equipment_revision':EQUIPMENT_REVISION,'reference_manifest':manifest,
        'test_only_support_change':manifest['test_only_support_change'],
        'equipment_plan_sha256':equipment_plan['content_sha256'],'reference_profile':profile,
        'isolated_application':isolated_application,'fault':fault,'scenario':scenario,
        'cases':['operations'],'harness_sha256':hashlib.sha256(inputs['operations.java']).hexdigest(),'judge_version':judge_version,
        'comparison_register_sha256':read_json(root/register_path)['content_sha256'],
        'assessed_on':date.today().isoformat(),'model_calls':0,
        'inputs_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in inputs.items()}})
    # Pin public contracts, driver and reference in addition to the native implementation.
    plan['implementation_sha256'].update({p.relative_to(root).as_posix():file_hash(p)
        for p in [root/'tools/ms94_a3_native.py',root/'tools/ms94_v6_gate.py',root/'tools/ms94_v3_negative_checks.py',source,*extra_tools,*sorted((root/AREA/'public').glob('*.json'))]})
    plan=seal({k:v for k,v in plan.items() if k!='content_sha256'})
    save(run/'plan.json',plan);(run/'authority.public.pem').write_bytes(signer.public)
    import shutil
    for relative in plan['implementation_sha256']:
        destination=run/'qualification-source'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/relative,destination)
    for name,data in inputs.items():
        p=run/'inputs'/name;p.parent.mkdir(exist_ok=True);p.write_bytes(data)
    save(run/'authorization.json',signer.sign({'record_type':'native-journey-authorization','run_id':run.name,
         'plan':{'plan_sha256':plan['content_sha256']},'operator_authorization':
         'User-authorized A3 paired native value-invariance qualification; no model calls. '+equipment_plan['content_sha256']}))
    save(output/'run.json',{'run_directory':run.relative_to(root).as_posix(),'plan_sha256':plan['content_sha256']})
    watch_options={'cwd':root,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,
                   'env':{**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}}
    if os.name=='nt':watch_options['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
    else:watch_options['start_new_session']=True
    subprocess.Popen([sys.executable,'-m','tools.ms94_watch_v5',str(root),str(run),str(os.getpid())],**watch_options)
    def emit(kind,payload):
        event={'at':time.time(),'event':kind,**payload}
        with (run/'qualification-events.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(event)+'\n')
        print(json.dumps({'run':run.name,**event}),flush=True)
    runner=None;observers=[];active=None;gate=None;error=None;folder=None
    started=time.monotonic()
    try:
        runner=runner_type(root,run,plan,emit)
        runner.deadline=min(runner.deadline,time.monotonic()+remaining_seconds)
        folder=runner.prepare('operations',1);save(run/'selected-attempts.json',{'operations':1})
        from tools.ms94_a3_entry import check as check_entry
        save(run/'a3-entry-admission.json',signer.sign(check_entry(run)))
        for lane in ('oracle','postgresql'):
            runner.checkpoint('execute-lane:'+lane)
            if scenario=='operations':active=Observer(runner,lane);observers.append(active);active.start()
            execution=runner.worker('execute',{'lane':lane,'output':runner.inside(folder/'execution'/lane),
                'harness':'/output/inputs/operations.java','harness_sha256':plan['harness_sha256'],
                'test':'LightyearOperationsTest','source_commit':plan['declaration']['application']['source_commit'],
                'timeout_seconds':1200},timeout=1250)
            if active:
                stopped=active;active=None
                try:stopped.stop()
                except Exception as exc:emit('observer-assessment-error',{'lane':lane,'type':type(exc).__name__})
            emit('native-execution',{'lane':lane,'exit_code':execution['exit_code']})
            runner.worker('capture',{'lane':lane,'output':runner.inside(folder/'after'/lane)},timeout=1800)
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc).replace((getattr(runner,'password',None) or 'UNSET_SECRET'),'[redacted]')}
        emit('execution-error',error)
    finally:
        if active:
            try:active.stop()
            except Exception as exc:emit('observer-stop-error',{'type':type(exc).__name__})
        try:cleaned=cleanup_owned(runner) if runner else {'complete':True,'remaining_containers':[], 'remaining_networks':[], 'remaining_volumes':[], 'inventory_known':True,'resources_created':False}
        except Exception as exc:
            cleaned={'complete':False,'errors':[type(exc).__name__],'remaining_containers':[],
                     'remaining_networks':[],'remaining_volumes':[],'inventory_known':False}
        save(run/'cleanup.json',signer.sign({'run_id':run.name,**cleaned}))
        for observer in observers:
            try:observer.publish_after_application_stopped(folder/'observers'/observer.lane)
            except Exception as exc:emit('observer-publication-error',{'type':type(exc).__name__})
        if error or not cleaned['complete']:
            save(run/'controller-outcome.json',signer.sign({'run_id':run.name,
                'plan_sha256':plan['content_sha256'],'cleanup_sha256':read_json(run/'cleanup.json')['content_sha256'],
                'status':'execution-failure','error':error or {'type':'CleanupIncomplete'}}))
        gate=evaluate(run)
        if judge_version!=VERSION:
            gate=seal({**{k:v for k,v in gate.items() if k!='content_sha256'},'judge_version':judge_version})
            save(run/'gate.json',gate)
        declaration=read_json(root/'factory/idempiere/qualification-ms94-v3/public/operations.json')
        api=read_json(root/'factory/idempiere/analyst-repair/api-provenance.json')
        diagnostics=export(run,declaration,root=root,api=api)
        suspect=equipment_suspect(run,declaration,root=root,api=api)
        intended=assess(gate,diagnostics,suspect,manifest)
        save(run/'diagnostic-projection.json',signer.sign({'diagnostics':diagnostics,
            'equipment_suspect':suspect,'disposition':'halted-equipment-suspect' if suspect else 'qualified-control',
            'diagnostic_bytes_sha256':hashlib.sha256(canonical(diagnostics)).hexdigest(),
            'gate_sha256':gate['content_sha256'],'candidate_sha256':manifest['harness_sha256']}))
        expected=manifest['expected']['status']
        receipt=signer.sign({'artifact_type':'ms94-a3-native-qualification-attempt','checkpoint_profile':checkpoint_profile,'run_id':run.name,
            'plan_sha256':plan['content_sha256'],'judge_version':judge_version,'fault':fault,'scenario':scenario,
            'reference_profile':profile,'isolated_application':isolated_application,
            'gate_sha256':gate['content_sha256'],'status':gate['status'],'expected_status':expected,
            'qualification_check_passed':intended and cleaned['complete'] and error is None,
            'negative_checks':{},'intended_rejection':intended,'equipment_suspect':suspect,
            'diagnostic_projection_sha256':read_json(run/'diagnostic-projection.json')['content_sha256'],
            'reference_human_reviewed':False,'reference_review_status':'planted test source; no independent human source attestation',
            'reference_sha256':manifest['harness_sha256'],'model_calls':0,'agent_generated':False,
            'autonomous_success':False,'scored_journeys':0,'elapsed_seconds':round(time.monotonic()-started,3),
            'cleanup_complete':cleaned['complete'],'error':error,'mutation_complete':False})
        save(run/'receipt.json',receipt);save(output/'receipt.json',receipt)
        emit('terminal',{'status':gate['status'],'qualification_check_passed':receipt['qualification_check_passed']})
    return receipt
