"""Native qualification equipment; no builder calls, no autonomous-success credit."""
from datetime import date
import hashlib,json,os,subprocess,sys,time,uuid
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,require,seal
from lightyear_calibration.journey_order import make_plan,archived,save,RUNS,file_hash
from lightyear_calibration.journey_runtime import LocalRunner,read_local,inventory,JourneySigner,docker
from lightyear_calibration.measured_native import cleanup_owned,REGISTER,INVENTORY
from lightyear_calibration.qualification_observer_runtime_v4 import Observer
from lightyear_calibration.qualified_judge_v3 import result
from tools.ms94_v4_gate import evaluate,VERSION
from lightyear_calibration.ms94_faults_v2 import FAULTS
from tools.ms94_v3_negative_checks import negative_checks

AREA=Path('factory/idempiere/qualification-ms94-v3')
DB_FAULTS=FAULTS
FAULTS={**DB_FAULTS,'candidate-reposts-own-match':'Candidate bypasses the public posting API','duplicate-trace-key':'Duplicate trace key'}
EXPECTED_REJECTION=FAULTS


def qualify(root, output, fault='none', scenario='operations', reference_profile=None, isolated_application=True, equipment_plan=None):
    from tools.ms94_execution_snapshot import guard
    guard(root)
    require(equipment_plan is not None,'A frozen equipment plan is required')
    from lightyear_calibration.contracts import verify
    verify(equipment_plan)
    for name,expected in equipment_plan['implementation_sha256'].items():
        require(file_hash(root/name)==expected,'Frozen attempt implementation changed')
    require(isolated_application, 'MS94 requires isolated application execution')
    require(fault in ('none',*FAULTS),'Unknown mutation')
    require(scenario in ('operations','procure-to-pay'),'Unknown scenario')
    require(scenario==('procure-to-pay' if fault in ('costing-wrong-organization','candidate-reposts-own-match') else scenario),'Wrong mutation scenario')
    require(not output.exists() and output.resolve().is_relative_to(root.resolve()),'Use a new workspace result')
    profile=reference_profile or scenario
    require(profile==scenario,'Unknown reference profile')
    source=root/AREA/'references'/profile/'LightyearOperationsTest.java'
    require(source.exists(),'Reference not prepared')
    manifest=read_json(root/AREA/'references'/profile/'manifest.json')
    require(file_hash(source)==manifest['harness_sha256'],'Reference changed without its manifest')
    register_path=REGISTER
    judge_version=VERSION
    verifier=None
    extra_tools=[]
    if scenario=='procure-to-pay':
        from tools.ms94_v3_purchasing import verify_run
        verifier=verify_run
        register_path=AREA/'private/comparison-register.json'
        extra_tools=[root/'tools'/name for name in ('qualification_purchasing_comparison.py',
            'qualification_procurement_effects.py','qualification_procurement_scope.py')]
    runner_type=LocalRunner
    if isolated_application:
        from tools.qualification_private_runner import PrivateRunner
        runner_type=PrivateRunner
        extra_tools += [root/'tools/qualification_private_runner.py',root/'tools/qualification_application_worker.py']
    if profile in ('operations','procure-to-pay'):
        support=root/AREA/'public/JourneySupport.java'
        require(file_hash(support)==manifest['public_support_sha256'],'Public support changed')
        extra_tools.append(support)
    extra_tools.append(root/AREA/'public'/(scenario+'-shapes.json'))
    run=root/RUNS/('journey-'+uuid.uuid4().hex);run.mkdir(parents=True);output.mkdir(parents=True)
    signer=JourneySigner(root);plan=json.loads(json.dumps(equipment_plan['base_plan']))
    plan['implementation_sha256']=dict(equipment_plan['implementation_sha256'])
    inputs=archived(root);inputs['operations.java']=source.read_bytes()
    if fault in ('candidate-reposts-own-match','duplicate-trace-key'):
        from tools.ms94_v3_mutations import own_match_repost,duplicate_trace
        mutate=own_match_repost if fault=='candidate-reposts-own-match' else duplicate_trace
        inputs['operations.java']=mutate(inputs['operations.java'].decode('utf-8')).encode('utf-8')
    inputs['JourneySupport.java']=(root/AREA/'public/JourneySupport.java').read_bytes()
    inputs['history-bound.json']=(root/AREA/'private/history-bound.json').read_bytes()
    inputs['comparison-register.json']=(root/register_path).read_bytes()
    inputs['datatype-inventory.json']=(root/INVENTORY).read_bytes()
    plan=seal({**{k:v for k,v in plan.items() if k!='content_sha256'},
        'qualification_only':True,'reference_manifest':manifest,'reference_profile':profile,
        'isolated_application':isolated_application,'fault':fault,'scenario':scenario,
        'cases':['operations'],'harness_sha256':hashlib.sha256(inputs['operations.java']).hexdigest(),'judge_version':judge_version,
        'comparison_register_sha256':read_json(root/register_path)['content_sha256'],
        'assessed_on':date.today().isoformat(),'model_calls':0,
        'inputs_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in inputs.items()}})
    # Pin public contracts, driver and reference in addition to the native implementation.
    plan['implementation_sha256'].update({p.relative_to(root).as_posix():file_hash(p)
        for p in [root/'tools/ms94_native_v4.py',root/'tools/ms94_v4_gate.py',root/'tools/ms94_v3_negative_checks.py',source,*extra_tools,*sorted((root/AREA/'public').glob('*.json'))]})
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
         'User requested local native judge qualification and deliberate negative controls; no generation.'}))
    save(output/'run.json',{'run_directory':run.relative_to(root).as_posix(),'plan_sha256':plan['content_sha256']})
    watch_options={'cwd':root,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,
                   'env':{**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}}
    if os.name=='nt':watch_options['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
    else:watch_options['start_new_session']=True
    subprocess.Popen([sys.executable,'-m','lightyear_calibration.journey_runtime','watch',str(root),str(run),str(os.getpid())],**watch_options)
    def emit(kind,payload):
        event={'at':time.time(),'event':kind,**payload}
        with (run/'qualification-events.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(event)+'\n')
        print(json.dumps({'run':run.name,**event}),flush=True)
    runner=runner_type(root,run,plan,emit);observers=[];active=None;gate=None;error=None;folder=None
    started=time.monotonic()
    try:
        folder=runner.prepare('operations',1);save(run/'selected-attempts.json',{'operations':1})
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
            # Run both engines even when one reference fails; never inject a fault
            # into an already failed reference and count that as a killed mutant.
            if fault in DB_FAULTS and execution['exit_code']==0:
                p=docker('exec','-i',runner.runner,'python','-m','lightyear_calibration.ms94_faults_v2',
                    input=canonical({'lane':lane,'fault':fault,'password':runner.password}),timeout=120)
                save(folder/'mutations'/(lane+'.json'),json.loads(p.stdout))
            runner.worker('capture',{'lane':lane,'output':runner.inside(folder/'after'/lane)},timeout=1800)
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc).replace(runner.password or 'UNSET_SECRET','[redacted]')}
        emit('execution-error',error)
    finally:
        if active:
            try:active.stop()
            except Exception as exc:emit('observer-stop-error',{'type':type(exc).__name__})
        try:cleaned=cleanup_owned(runner)
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
        mutation_complete=fault in ('none','candidate-reposts-own-match','duplicate-trace-key') or all((folder/'mutations'/(lane+'.json')).exists() for lane in ('oracle','postgresql')) if folder else False
        rejected=negative_checks(run,fault,gate) if fault!='none' and mutation_complete else {}
        intended_rejection=fault=='none' or (len(rejected)==2 and all(v['passed'] for v in rejected.values())
            )
        expected=('passed' if fault=='none' else 'execution-failure' if fault=='duplicate-trace-key' else 'business-failure')
        receipt=signer.sign({'artifact_type':'native-judge-qualification-attempt','run_id':run.name,
            'plan_sha256':plan['content_sha256'],'judge_version':judge_version,'fault':fault,'scenario':scenario,
            'reference_profile':profile,'isolated_application':isolated_application,
            'gate_sha256':gate['content_sha256'],'status':gate['status'],'expected_status':expected,
            'qualification_check_passed':gate['status']==expected and mutation_complete and intended_rejection and cleaned['complete'],
            'negative_checks':rejected,'intended_rejection':intended_rejection,
            'reference_human_reviewed':False,'reference_review_status':'pending-human-review',
            'reference_sha256':manifest['harness_sha256'],'model_calls':0,'agent_generated':False,
            'autonomous_success':False,'scored_journeys':0,'elapsed_seconds':round(time.monotonic()-started,3),
            'cleanup_complete':cleaned['complete'],'error':error,'mutation_complete':mutation_complete})
        save(run/'receipt.json',receipt);save(output/'receipt.json',receipt)
        emit('terminal',{'status':gate['status'],'qualification_check_passed':receipt['qualification_check_passed']})
    return receipt

