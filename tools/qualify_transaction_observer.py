"""Qualify engine observers on disposable native copies, without generation."""
import hashlib
import json
from pathlib import Path
import time
import uuid
from lightyear_calibration.contracts import canonical,read_json,require,seal
from lightyear_calibration.journey_order import make_plan,archived,save,RUNS
from lightyear_calibration.journey_runtime import LocalRunner,read_local,inventory,JourneySigner,docker
from lightyear_calibration.observer_runtime import Observer


def qualify(root):
    run=root/RUNS/('journey-'+uuid.uuid4().hex);run.mkdir(parents=True)
    plan=make_plan(root,read_local(root),inventory(root));plan['observer_policy']='native-transaction-observer-v1'
    plan['qualification_only']=True;plan=seal({k:v for k,v in plan.items() if k!='content_sha256'})
    signer=JourneySigner(root);save(run/'plan.json',plan)
    import shutil
    for name in ('transaction_observer.py','observer_runtime.py','observer_probe.py'):
        (run/'qualification-source').mkdir(exist_ok=True)
        shutil.copyfile(root/'src/lightyear_calibration'/name,run/'qualification-source'/name)
    save(run/'authorization.json',signer.sign({'artifact_type':'observer-qualification-authorization',
         'run_id':run.name,'plan_sha256':plan['content_sha256'],
         'scope':'Controlled local observer qualification on isolated copies; no model calls or scored journeys',
         'approval':'User requested engine-side lock/rollback observation first.'}))
    (run/'inputs').mkdir()
    for name,data in archived(root).items():(run/'inputs'/name).write_bytes(data)
    results={};observer=None;error=None
    def emit(kind,payload):print(json.dumps({'event':kind,**payload}),flush=True)
    runner=LocalRunner(root,run,plan,emit)
    try:
        folder=runner.prepare('observer-qualification',1)
        for lane in ('oracle','postgresql'):
            observer=Observer(runner,lane).start()
            payload=canonical({'lane':lane,'password':runner.password})
            p=docker('exec','-i',runner.runner,'python','-m','lightyear_calibration.observer_probe',input=payload,timeout=40)
            save(folder/(lane+'-fixture.json'),json.loads(p.stdout))
            results[lane]=observer.stop();observer=None
            runner.worker('capture',{'lane':lane,'output':runner.inside(folder/'after'/lane)},timeout=1800)
            before=read_json(folder/'baseline'/lane/'entry/state.json') if (folder/'baseline'/lane/'entry/state.json').exists() else None
            from lightyear_calibration.native_reconciliation import state
            before=state(folder/'baseline'/lane/'entry',lane);after=state(folder/'after'/lane,lane)
            require({k:v['row_multiset'] for k,v in before['tables'].items()}=={k:v['row_multiset'] for k,v in after['tables'].items()},'Observer qualification changed application rows')
            emit('observer-qualified',{'lane':lane,'lock_witnesses':len(results[lane]['lock_witnesses']),'rollback_witnesses':len(results[lane]['rollback_witnesses'])})
        require(all(v['passed'] for v in results.values()),'Observer did not capture both native events on every lane')
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        emit('failed',error)
    finally:
        if observer:
            try:observer.stop()
            except Exception:pass
        cleaned=runner.cleanup()
        save(run/'cleanup.json',signer.sign({'run_id':run.name,**cleaned}))
        for lane in ('oracle','postgresql'):
            source=root/'work/ms92/observer-private'/run.name/lane/'capture'
            if source.exists():
                import shutil
                shutil.copytree(source,run/'observers'/lane)
        receipt=signer.sign({'artifact_type':'native-observer-qualification','run_id':run.name,
            'plan_sha256':plan['content_sha256'],'passed':error is None and cleaned['complete'] and len(results)==2,
            'results':results,'error':error,'cleanup_complete':cleaned['complete'],
            'model_calls':0,'scored_journeys':0,'fixture_is_not_application_equivalence':True})
        save(run/'receipt.json',receipt)
    print(json.dumps({'run':run.as_posix(),'passed':receipt['passed'],'error':error}),flush=True)
    return receipt


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));args=p.parse_args()
    raise SystemExit(0 if qualify(args.root.resolve())['passed'] else 1)
