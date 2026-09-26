"""Opt-in real Docker lifecycle faults. These are runtime tests, not business evidence."""
from pathlib import Path
import argparse
import json
import secrets
import threading
import time
from unittest.mock import patch
from lightyear_calibration.journey_runtime import LocalRunner, JourneySigner, docker, inspect, JourneyAbort
from lightyear_calibration.journey_order import RUNS, save
from lightyear_calibration.contracts import read_json
from lightyear_execution.journey_network import InternalOnlyNetwork


def run_fault(root, kind, image):
    run_id='journey-'+secrets.token_hex(16);run=root/RUNS/run_id;run.mkdir(parents=True)
    signer=JourneySigner(root);(run/'authority.public.pem').write_bytes(signer.public)
    plan={'declaration':{'policy':{'max_elapsed_seconds':60}},'implementation_sha256':{}}
    runner=LocalRunner(root,run,plan,lambda *_:None)
    name=run_id+'-runner';network=run_id+'-net';runner.runner=name;runner.password='ephemeral-fault-test'
    stub=run/'stub/lightyear_calibration';stub.mkdir(parents=True)
    (stub/'__init__.py').write_text('')
    (stub/'journey_worker.py').write_text('import json,sys,time\njson.load(sys.stdin)\ntime.sleep(30)\nprint("{}")\n')
    docker(*InternalOnlyNetwork(run_id).create_args(network))
    failure=None;cleanup=None
    try:
        docker('create','--name',name,'--label',runner.label,'--network',network,'--cap-drop','ALL','--security-opt','no-new-privileges',
               '--mount',f'type=bind,src={stub.parent.resolve()},dst=/fault,readonly','-e','PYTHONPATH=/fault',image)
        docker('start',name)
        def inject():
            time.sleep(2)
            if kind=='killed-container':docker('kill',name)
            elif kind=='cancel':save(run/'cancel-request.json',signer.sign({'action':'cancel','run_id':run_id,'actor':'fault-test'}))
        thread=threading.Thread(target=inject);thread.start()
        try:runner.worker('probe',{},timeout=3 if kind=='timeout' else 15)
        except Exception as exc:failure=exc.code if isinstance(exc,JourneyAbort) else type(exc).__name__
        thread.join()
    finally:cleanup=runner.cleanup(retain=True)
    assert failure and cleanup['complete'] and cleanup['credentials_destroyed'], (failure,cleanup)
    if kind=='cancel':assert failure=='cancelled'
    if kind=='timeout':assert failure=='timeout'
    receipt=signer.sign({'artifact_type':'lightyear-runtime-fault-injection','kind':kind,'failure':failure,'cleanup':cleanup,
                         'native_business_evidence':False,'cloud_resources_started':False})
    save(run/'receipt.json',receipt);return receipt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--image',required=True)
    a=parser.parse_args();results=[run_fault(a.root.resolve(),kind,a.image) for kind in ('killed-container','cancel','timeout')]
    save(a.root/'results.json',results)
    print(json.dumps([{'kind':r['kind'],'failure':r['failure'],'cleaned':r['cleanup']['complete']} for r in results]))

if __name__=='__main__':main()
