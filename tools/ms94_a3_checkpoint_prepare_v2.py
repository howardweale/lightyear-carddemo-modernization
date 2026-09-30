"""One-shot native private checkpoint preparation, not A3 fault qualification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from lightyear_calibration.contracts import canonical, read_json, require, seal, verify
from lightyear_calibration.journey_order import archived, file_hash, RUNS, save
from lightyear_calibration.journey_runtime import LocalRunner, docker
from lightyear_calibration.measured_native import cleanup_owned
from lightyear_calibration.ms94_a3_checkpoint_v2 import RECIPE, audit
from lightyear_calibration.native_reconciliation import reconcile, state, HISTORY_POLICY
from lightyear_calibration.schema_equivalence import assess
from lightyear_calibration.native_catalog import read_capture
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard
from tools.ms94_signer_v5 import JourneySigner


def prepare(root, output):
    root,output=Path(root).resolve(),Path(output).resolve();manifest=guard(root)
    require(output.is_relative_to(root) and not output.exists(), 'Use a new preparation directory')
    prior=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a2-r1'
    report=read_json(prior/'report.json');terminal=read_json(prior/'terminal-verification.json')
    signer=JourneySigner(root)
    require(all(verify_envelope(x,signer.public) for x in (report,terminal)), 'A2 revision signatures invalid')
    require(report['passed'] and len(report['results'])==18 and report['unstarted_slots']==0
            and terminal['report_sha256']==report['content_sha256'] and terminal['cleanup_verified']
            and len(terminal['publications'])==18 and all(x['verified'] for x in terminal['publications']),
            'A2 revision prerequisite incomplete')
    value=seal({'artifact_type':'ms94-a3-native-checkpoint-preparation-v2-plan',
        'prior_failed_report_sha256':'76fe807e3a7ee26a0f79ce15f4c43d6f27094db4e96f0552ae0338aa8f7c9163',
        'revision':'Preserve required shared MS84 predecessor binding; recipe provenance stays separate.',
        'base_plan':read_json(prior/'plan.json')['base_plan'],
        'a2_report_sha256':report['content_sha256'],'a2_verification_sha256':terminal['content_sha256'],
        'execution_snapshot_sha256':manifest['content_sha256'],'implementation_sha256':manifest['files'],
        'recipe':RECIPE,'max_elapsed_seconds':7200,'native_database_pairs':1,
        'model_calls':0,'java_compilations':0,'candidate_executions':0,
        'a3_qualified':False,'b04_admitted':False,'restarts_allowed':False,
        'scope':'Derive and admit a genuine private database checkpoint before freezing A3 fault comparisons.'})
    save(output/'plan.json',value);save(output/'declaration.json',signer.sign({'plan_sha256':value['content_sha256'],
         'model_calls':0,'qualification_claim':False}))
    return value


def native_derive(runner, lane, folder, admitted):
    process=subprocess.Popen(['docker','exec','-i',runner.runner,'python','-m',
                              'lightyear_calibration.ms94_a3_checkpoint_v2'],
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    data=canonical({'lane':lane,'password':runner.password,'output':runner.inside(folder),
                    'admitted_entry':runner.inside(admitted),'admitted_checkpoint':runner.inside(runner.run/'inputs/checkpoint.json'),'recipe_sha256':RECIPE['content_sha256']})
    try:
        while True:
            try:out,err=process.communicate(input=data,timeout=1);break
            except subprocess.TimeoutExpired:data=None;runner.check_cancel()
        if process.returncode:
            safe=(out+err).decode(errors='replace').replace(runner.password,'[redacted]')
            save(runner.run/'derivation-errors'/f'{lane}.json',{'diagnostic':safe[-8000:]})
            raise RuntimeError('Native checkpoint derivation failed; private diagnostic preserved for '+lane)
        return json.loads(out)
    finally:
        if process.poll() is None:
            process.kill();process.communicate();docker('kill',runner.runner,check_code=False)


def run(root, output):
    root,output=Path(root).resolve(),Path(output).resolve();manifest=guard(root);signer=JourneySigner(root)
    cp=read_json(output/'plan.json');verify(cp)
    require(cp['implementation_sha256']==manifest['files'] and cp['recipe']==RECIPE, 'Preparation freeze differs')
    for name in ('declaration.json','authorization.json'):
        x=read_json(output/name)
        require(verify_envelope(x,signer.public) and x['plan_sha256']==cp['content_sha256'], 'Preparation approval missing')
    require(read_json(output/'authorization.json')['explicit_user_authorization'], 'Preparation not authorized')
    with (output/'started.json').open('x') as f:json.dump({'at':time.time(),'plan_sha256':cp['content_sha256']},f)
    started=time.monotonic();native=root/RUNS/('journey-'+uuid.uuid4().hex);native.mkdir(parents=True)
    inputs=archived(root)
    for name,data in inputs.items():
        p=native/'inputs'/name;p.parent.mkdir(exist_ok=True);p.write_bytes(data)
    plan=seal({**{k:v for k,v in cp['base_plan'].items() if k!='content_sha256'},
        'implementation_sha256':manifest['files'],'inputs_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in inputs.items()},
        'model_calls':0,'checkpoint_preparation_only':True,'preparation_plan_sha256':cp['content_sha256']})
    save(native/'plan.json',plan);(native/'authority.public.pem').write_bytes(signer.public)
    save(native/'authorization.json',signer.sign({'run_id':native.name,'plan':{'plan_sha256':plan['content_sha256']},
         'operator_authorization':'Howard authorized genuine private A3 checkpoint preparation; no candidate/model execution.'}))
    save(output/'run.json',{'run_directory':native.relative_to(root).as_posix()})
    options={'cwd':root,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,
             'env':{**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}}
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
    else:options['start_new_session']=True
    subprocess.Popen([sys.executable,'-m','tools.ms94_watch_v5',str(root),str(native),str(os.getpid())],**options)
    def emit(kind,payload):
        value={'at':time.time(),'event':kind,**payload}
        with (native/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(value)+'\n')
        print(json.dumps(value),flush=True)
    runner=LocalRunner(root,native,plan,emit);runner.deadline=time.monotonic()+cp['max_elapsed_seconds']
    error=None;checkpoint=None;audits={};derived={}
    try:
        folder=runner.prepare('operations',1)
        for lane in ('oracle','postgresql'):
            runner.checkpoint('derive-private-checkpoint:'+lane)
            target=native/'derived-checkpoint'/lane
            derived[lane]=native_derive(runner,lane,target,folder/'baseline'/lane/'entry')
            verify(derived[lane]);audits[lane]=audit(target/'before',target/'entry',lane)
            save(native/'host-audits'/f'{lane}.json',audits[lane])
            emit('checkpoint-derived',{'lane':lane,'audit_passed':True})
        catalogs={lane:read_capture(native/'derived-checkpoint'/lane/'catalog.json') for lane in derived}
        assessment=assess(catalogs);counts=assessment['counts']
        require(counts['foreign_key_catalog_matches']==3826 and counts['foreign_key_missing_relationships']==
                counts['nullable_differences']==0,'Derived checkpoint schema equivalence failed')
        save(native/'derived-schema-assessment.json',assessment)
        before={lane:folder/'baseline'/lane/'entry' for lane in derived}
        after={lane:native/'derived-checkpoint'/lane/'entry' for lane in derived}
        prior=read_json(native/'inputs/checkpoint.json');verify(prior)
        prior=seal({**{k:v for k,v in prior.items() if k!='content_sha256'},
                    'replayed_checkpoint_sha256':prior['content_sha256'],
                    'state_sha256':{lane:state(f,lane)['content_sha256'] for lane,f in before.items()}})
        checkpoint=reconcile(after,read_json(native/'inputs/primary-keys.json'),before=before,prior=prior,policy=HISTORY_POLICY)
        require(checkpoint['admitted'] and not checkpoint['unresolved_differences'], 'Derived checkpoint reconciliation failed')
        save(native/'derived-checkpoint/checkpoint.json',checkpoint)
        for lane,f in after.items():
            save(native/'derived-checkpoint'/f'{lane}-entry-multisets.json',
                 {k:v['row_multiset'] for k,v in state(f,lane)['tables'].items()})
        guard(root)
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc).replace(runner.password or 'UNSET_SECRET','[redacted]')}
        save(output/'stopping.json',signer.sign({'error':error,'notify_immediately':True}))
        emit('stopping',{'error_type':type(exc).__name__,'message':error['message']})
    finally:
        try:cleaned=cleanup_owned(runner)
        except Exception as exc:cleaned={'complete':False,'error_type':type(exc).__name__}
        save(native/'cleanup.json',signer.sign({'run_id':native.name,**cleaned}))
        passed=error is None and checkpoint is not None and cleaned['complete']
        report=signer.sign({'artifact_type':'ms94-a3-native-checkpoint-preparation-v2-result',
            'plan_sha256':cp['content_sha256'],'run_directory':native.relative_to(root).as_posix(),
            'passed':passed,'error':error,'cleanup_complete':cleaned['complete'],
            'checkpoint_sha256':checkpoint['content_sha256'] if checkpoint else None,
            'recipe_sha256':RECIPE['content_sha256'],
            'audits':{lane:v['content_sha256'] for lane,v in audits.items()},
            'model_calls':0,'java_compilations':0,'candidate_executions':0,
            'elapsed_seconds':round(time.monotonic()-started,3),'a3_qualified':False,'b04_admitted':False})
        save(native/'receipt.json',report);save(output/'report.json',report)
        emit('terminal',{'passed':passed,'a3_qualified':False,'cleanup_complete':cleaned['complete']})
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.root,a.output),indent=2))
