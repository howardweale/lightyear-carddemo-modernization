"""Native qualification equipment; no builder calls, no autonomous-success credit."""
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys,time,uuid
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,require,seal
from lightyear_calibration.journey_order import make_plan,archived,save,RUNS,file_hash
from lightyear_calibration.journey_runtime import LocalRunner,read_local,inventory,docker
from tools.ms94_signer_v5 import JourneySigner
from lightyear_calibration.measured_native import cleanup_owned,REGISTER,INVENTORY
from lightyear_calibration.qualification_observer_runtime_v4 import Observer
from lightyear_calibration.qualified_judge_v3 import result
from tools.ms94_v6_gate import evaluate,VERSION,EQUIPMENT_REVISION
from lightyear_calibration.ms94_faults_v2 import FAULTS
from tools.ms94_v3_negative_checks import negative_checks

AREA=Path('factory/idempiere/qualification-ms94-v3')
DB_FAULTS=FAULTS
FAULTS={**DB_FAULTS,'candidate-reposts-own-match':'Candidate bypasses the public posting API','duplicate-trace-key':'Duplicate trace key'}
EXPECTED_REJECTION=FAULTS


def execute_native(root,campaign,build,builder,remaining_seconds):
    from tools.ms94_b05_supervisor import remaining_work
    remaining_seconds=min(remaining_seconds,remaining_work(root,campaign))
    from tools.ms94_b05_controller import frozen
    cp=frozen(root,campaign,live=True)
    equipment_plan=read_json(root/cp['equipment_plan_path'])
    output=build.parent/'native';fault='none';scenario='operations';profile='agent-with-public-support';isolated_application=True
    source=build/'workspace/LightyearOperationsTest.java'
    require(file_hash(source)==builder['harness_sha256'],'Builder candidate changed')
    from lightyear_control_tower.decisions import verify_envelope
    require(verify_envelope(builder,(root/'work/ms87/operator/authority.public.pem').read_bytes()),'Candidate authorization signature differs')
    if cp['preflight_only']:
        from tools.ms94_b05_admission import PREFLIGHT
        from tools.ms94_calendar_sources import source as fixture_source
        allowed={root/PREFLIGHT/f'attempt-{i}'/'build':fixture_source(root,'retained',fault)[0]
                 for i,fault in ((1,'invoice-null-dereference'),(2,None))}
        require(build in allowed and source.read_bytes()==allowed[build].read_bytes()
                and builder['provider_invocations']==0 and builder['fixture_only'] is True,'Unapproved preflight candidate or slot')
    else:
        require(builder['plan_sha256']==cp['content_sha256'] and builder['provider_invocations']>0,'Missing model candidate provenance')
    require(not output.exists(),'Native attempts cannot be restarted')
    manifest={'harness_sha256':builder['harness_sha256'],'public_support_sha256':cp['support_sha256']}
    register_path=REGISTER
    judge_version=VERSION
    from tools.ms94_calendar_runner import CalendarRunner
    runner_type=CalendarRunner
    extra_tools=[root/'tools/ms94_calendar_runner.py',root/'tools/ms94_calendar_application_worker.py',root/'tools/ms94_calendar_evidence.py',
                 root/AREA/'public/JourneySupport.java',root/AREA/'public/operations-shapes.json']
    run=root/RUNS/('journey-'+uuid.uuid4().hex);run.mkdir(parents=True);output.mkdir(parents=True)
    signer=JourneySigner(root);plan=json.loads(json.dumps(equipment_plan['base_plan']))
    plan['implementation_sha256']=dict(cp['implementation_sha256'])
    inputs=archived(root);inputs['operations.java']=source.read_bytes()
    inputs['JourneySupport.java']=(root/AREA/'public/JourneySupport.java').read_bytes()
    inputs['invoice-type-contract.json']=(root/'factory/idempiere/qualification-ms94-v5/public/operations-shapes.json').read_bytes()
    inputs['history-bound.json']=(root/AREA/'private/history-bound.json').read_bytes()
    inputs['comparison-register.json']=(root/register_path).read_bytes()
    inputs['datatype-inventory.json']=(root/INVENTORY).read_bytes()
    plan=seal({**{k:v for k,v in plan.items() if k!='content_sha256'},
        'qualification_only':bool(cp['preflight_only']),'calendar':cp['calendar'],'reference_manifest':manifest,
        'host_started_utc':datetime.now(timezone.utc).isoformat(),'preflight_only':cp['preflight_only'],
        'equipment_revision':EQUIPMENT_REVISION,'a3_checkpoint_profile':'admitted',
        'a3_preparation_verification_sha256':'9bf52b816897f351e6a8261abae0b590aa184309d2d1c1859ba6b33a9ab0711f',
        'campaign_directory':campaign.relative_to(root).as_posix(),'campaign_plan_sha256':cp['content_sha256'],'reference_profile':profile,
        'isolated_application':isolated_application,'fault':fault,'scenario':scenario,
        'cases':['operations'],'harness_sha256':hashlib.sha256(inputs['operations.java']).hexdigest(),'judge_version':judge_version,
        'comparison_register_sha256':read_json(root/register_path)['content_sha256'],
        'assessed_on':cp['assessed_on'],'model_calls':builder['provider_invocations'],
        'inputs_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in inputs.items()}})
    # Pin public contracts, driver and reference in addition to the native implementation.
    plan['implementation_sha256'].update({p.relative_to(root).as_posix():file_hash(p)
        for p in [root/'tools/ms94_b05_native.py',root/'tools/ms94_v6_gate.py',root/'tools/ms94_v3_negative_checks.py',source,*extra_tools,*sorted((root/AREA/'public').glob('*.json'))]})
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
         ('User-approved zero-model B05 preflight ' if cp['preflight_only'] else 'User-approved B05 model measurement ')+cp['content_sha256']}))
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
    def before_candidate(lane):
        save(run/('candidate-started-'+lane+'.json'),signer.sign({'lane':lane,'real_utc':datetime.now(timezone.utc).isoformat(),
            'calendar_sha256':plan['calendar']['content_sha256'],'entry_admission_sha256':read_json(run/'a3-entry-admission.json')['content_sha256']}))
    started=time.monotonic()
    try:
        runner=runner_type(root,run,plan,emit)
        runner.before_candidate=before_candidate
        runner.deadline=min(runner.deadline,time.monotonic()+remaining_seconds)
        folder=runner.prepare('operations',1);save(run/'selected-attempts.json',{'operations':1})
        from tools.ms94_a3_entry_v2 import admit
        admit(run,signer)
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
                except Exception as exc:
                    emit('observer-assessment-error',{'lane':lane,'type':type(exc).__name__});raise
            emit('native-execution',{'lane':lane,'exit_code':execution['exit_code']})
            runner.worker('capture',{'lane':lane,'output':runner.inside(folder/'after'/lane)},timeout=1800)
        runner.record_guard('pair-complete')
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc).replace((getattr(runner,'password',None) or 'UNSET_SECRET'),'[redacted]')}
        emit('execution-error',error)
        from tools.ms94_b05_stops import notify
        notify(root,campaign,'halted-controller-failure',{'native_run':run.name,'error_type':type(exc).__name__})
    finally:
        if active:
            try:active.stop()
            except Exception as exc:emit('observer-stop-error',{'type':type(exc).__name__})
        try:cleaned=cleanup_owned(runner) if runner else {'complete':True,'remaining_containers':[], 'remaining_networks':[], 'remaining_volumes':[], 'inventory_known':True,'resources_created':False}
        except Exception as exc:
            cleaned={'complete':False,'errors':[type(exc).__name__],'remaining_containers':[],
                     'remaining_networks':[],'remaining_volumes':[],'inventory_known':False}
        save(run/'cleanup.json',signer.sign({'run_id':run.name,**cleaned}))
        if not cleaned['complete']:
            from tools.ms94_b05_stops import notify
            notify(root,campaign,'void-equipment-failure',{'native_run':run.name,'reason':'cleanup'})
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
        from tools.ms94_calendar_evidence import replay_calendar
        try:calendar_checks=replay_calendar(run)
        except Exception as exc:
            calendar_checks={};error=error or {'type':type(exc).__name__,'message':str(exc)}
        from tools.ms94_b05_evidence import projection
        projected=signer.sign(projection(root,run))
        save(run/'diagnostic-projection.json',projected)
        if projected['equipment_suspect']:
            from tools.ms94_b05_stops import signal_review
            signal_review(root,campaign,'equipment-suspect')
        expected='passed'
        receipt=signer.sign({'artifact_type':'ms94-native-factory-attempt','run_id':run.name,
            'plan_sha256':plan['content_sha256'],'judge_version':judge_version,'fault':fault,'scenario':scenario,
            'reference_profile':profile,'isolated_application':isolated_application,
            'gate_sha256':gate['content_sha256'],'status':gate['status'],'expected_status':expected,
            'qualification_check_passed':False,'calendar_checks':calendar_checks,
            'negative_checks':{},'intended_rejection':False,
            'equipment_suspect':projected['equipment_suspect'],
            'diagnostic_projection_sha256':projected['content_sha256'],
            'reference_human_reviewed':False,'reference_review_status':'not-a-reference',
            'reference_sha256':manifest['harness_sha256'],'model_calls':builder['provider_invocations'],'agent_generated':not cp['preflight_only'],
            'autonomous_success':False,'scored_journeys':0,'elapsed_seconds':round(time.monotonic()-started,3),
            'cleanup_complete':cleaned['complete'],'error':error,'mutation_complete':False})
        save(run/'receipt.json',receipt);save(output/'receipt.json',receipt)
        emit('terminal',{'status':gate['status'],'qualification_check_passed':receipt['qualification_check_passed']})
    return run,receipt
