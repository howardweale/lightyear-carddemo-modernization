"""B05 r2 process boundary covering work, cleanup, signing, archive and replay.

No result is accepted at or after the hard deadline. Timeout recovery is recorded
as a failed trial and charged separately, never disguised as an in-budget finish.
"""
import hashlib,json,os,signal,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,canonical
from lightyear_calibration.journey_order import save,RUNS
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_signer_v5 import JourneySigner

HARD_SECONDS=7190
RESERVE_SECONDS=600

def remaining_work(root,campaign):
    start=read_json(campaign/'supervision-start.json')
    key=(root/'work/ms87/operator/authority.public.pem').read_bytes()
    require(verify_envelope(start,key),'Missing signed trial supervision')
    require(start['snapshot_sha256']==read_json(root/'execution-snapshot.json')['content_sha256'], 'Supervisor snapshot differs')
    require(start['campaign_directory']==campaign.relative_to(root).as_posix(),'Supervisor trial differs')
    value=start['work_deadline_monotonic']-time.monotonic()
    require(value>0,'Trial work deadline exhausted; finalization reserve retained')
    return value

def wait_process(process,deadline,poll=time.monotonic,on_tick=lambda:None):
    while True:
        on_tick()
        require(poll()<deadline,'Total trial deadline exhausted, including finalization')
        code=process.poll()
        if code is not None:
            require(code==0,'Supervised worker exited unsuccessfully')
            return
        time.sleep(min(.2,max(.001,deadline-poll())))

def terminate(process):
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=30,check=False)
    else:os.killpg(process.pid,signal.SIGKILL)
    process.wait(timeout=30)

def recover(root,campaign):
    """Only signed native runs belonging to this exact interrupted trial."""
    from lightyear_calibration.journey_runtime import LocalRunner
    from lightyear_calibration.measured_native import cleanup_owned
    from tools.ms94_b05_admission import actual_cleanup
    signer=JourneySigner(root);records=[]
    for p in sorted((root/RUNS).glob('*/plan.json')):
        plan=read_json(p)
        if plan.get('campaign_directory')!=campaign.relative_to(root).as_posix():continue
        run=p.parent;auth=read_json(run/'authorization.json')
        require(verify_envelope(auth,signer.public) and auth['run_id']==run.name
            and auth['plan']['plan_sha256']==plan['content_sha256'],'Untrusted recovery inventory')
        runner=LocalRunner(root,run,plan,lambda *_:None)
        cleaned=cleanup_owned(runner)
        require(cleaned['complete'],'Recovery cleanup incomplete')
        records+=actual_cleanup(run)
    return records

def launch_worker(command,root):
    return subprocess.Popen(command,cwd=root,start_new_session=os.name!='nt')

def run_unit(root,campaign,mode,executable=None,remaining_seconds=93600):
    from tools.ms94_b05_admission import bindings,preflight_authorization,model_authorization
    from tools.ms94_b05_stops import notify
    started=time.monotonic();limit=min(HARD_SECONDS,remaining_seconds-1)
    require(limit>RESERVE_SECONDS,'Insufficient campaign time for a new trial and finalization reserve')
    preflight_authorization(root) if mode=='preflight' else model_authorization(root)
    _,snapshot=bindings(root,True);signer=JourneySigner(root)
    record=signer.sign({'artifact_type':'b05-r2-supervision-start','snapshot_sha256':snapshot['content_sha256'],
        'campaign_directory':campaign.relative_to(root).as_posix(),'mode':mode,
        'started_at_utc':datetime.now(timezone.utc).isoformat(),'started_monotonic':started,
        'work_deadline_monotonic':started+limit-RESERVE_SECONDS,'hard_deadline_monotonic':started+limit,
        'maximum_total_seconds':limit,'finalization_reserve_seconds':RESERVE_SECONDS,
        'includes':['admission','model-work','native-work','cleanup','audit','signing','archive','offline-replay','worker-exit'],
        'model_calls_authorized':mode=='measurement'})
    with (campaign/'supervision-start.json').open('xb') as f:f.write(canonical(record))
    command=[sys.executable,'-m','tools.ms94_b05_supervisor','--root',str(root),'--campaign',str(campaign),'--worker',mode]
    if executable:command+=['--executable',str(executable)]
    process=None;error=None;cleanup=[];recovery_seconds=0;result=None
    try:
        process=launch_worker(command,root)
        from tools.ms94_b05_plan import period_guard
        wait_process(process,started+limit,on_tick=lambda:period_guard(datetime.now(timezone.utc)))
        result=read_json(campaign/'supervised-result.json')
        require(verify_envelope(result,signer.public),'Worker result signature invalid')
        require(result['supervision_start_sha256']==record['content_sha256'],'Worker result supervision differs')
        require(time.monotonic()<started+limit,'Final result exceeded total trial deadline')
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        notify(root,campaign,'halted-trial-deadline' if time.monotonic()>=started+limit else 'halted-controller-failure',error)
        recovery_start=time.monotonic()
        try:
            if process:terminate(process)
            cleanup=recover(root,campaign)
        except Exception as cleanup_error:error['recovery_error']=str(cleanup_error)
        recovery_seconds=time.monotonic()-recovery_start
    elapsed=time.monotonic()-started
    # Signing itself is also inside the valid-result acceptance deadline.
    value=signer.sign({'artifact_type':'b05-r2-supervision-receipt','supervision_start_sha256':record['content_sha256'],
        'worker_result_sha256':result['content_sha256'] if result else None,'completed_within_budget':error is None and elapsed<limit,
        'total_elapsed_seconds':elapsed,'recovery_elapsed_seconds':recovery_seconds,'recovery_cleanup':cleanup,'error':error,
        'model_calls':0 if mode=='preflight' else None,'late_result_never_accepted':True})
    if time.monotonic()>=started+limit and error is None:
        notify(root,campaign,'halted-trial-deadline')
        value=signer.sign({**{k:v for k,v in value.items() if k not in ('signature','content_sha256')},
            'completed_within_budget':False,'error':{'type':'Deadline','message':'Supervisor finalization exceeded deadline'}})
    save(campaign/'supervision-receipt.json',value)
    if time.monotonic()>=started+limit:
        notify(root,campaign,'halted-trial-deadline')
        require(False,'Supervisor receipt write exceeded total deadline; no next slot')
    require(value['completed_within_budget'],'Supervised trial failed; no next slot')
    return result

def worker(root,campaign,mode,executable):
    from tools.ms94_b05_admission import PREFLIGHT,CAMPAIGN,actual_cleanup
    from tools.ms94_b05_publication import publish,replay
    from tools.ms94_b05_stops import IMMEDIATE,notify
    remaining_work(root,campaign)
    signer=JourneySigner(root)
    if mode=='preflight':
        require(campaign==root/PREFLIGHT,'Unexpected preflight path')
        from tools.ms94_b05_preflight import run
        result=run(root);require(result['passed'],'Preflight failed')
    else:
        require(campaign.parent==root/CAMPAIGN/'trials','Unexpected measurement path')
        from tools.ms94_b05_controller import run
        result=run(root,campaign,executable,remaining_work(root,campaign))
        from tools.ms94_b05_review import summarize_trial
        summarize_trial(root,campaign,result)
        if result['status'] in IMMEDIATE:notify(root,campaign,result['status'])
        for i,a in enumerate(result['attempts'],1):
            native=root/a['run_directory'];actual_cleanup(native)
            publication=root/CAMPAIGN/'publications'/f'{campaign.name}-{i}'
            publish(root,native,publication)
            verified=replay(root,publication,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
            require(all(verified.get(k) for k in ('verified','full_entry_replayed','complete_gate_replayed','diagnostic_replayed','calendar_replayed','provenance_replayed','delivery_replayed')),'Incomplete trial replay')
            save(publication/'verification.json',signer.sign(verified));actual_cleanup(native)
    save(campaign/'supervised-result.json',signer.sign({'result':result,
        'supervision_start_sha256':read_json(campaign/'supervision-start.json')['content_sha256'],
        'finalization_and_replay_complete':True}))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--campaign',type=Path)
    p.add_argument('--worker',choices=('preflight','measurement'));p.add_argument('--preflight',action='store_true');p.add_argument('--executable',type=Path)
    a=p.parse_args();root=a.root.resolve()
    if a.worker:worker(root,a.campaign.resolve(),a.worker,a.executable)
    else:
        require(a.preflight,'Only zero-model preflight may be directly supervised from CLI')
        from tools.ms94_b05_admission import PREFLIGHT
        run_unit(root,root/PREFLIGHT,'preflight')
