"""Publish every observer qualification outcome, including pre-freeze failures."""
import argparse
import hashlib
from pathlib import Path
import shutil
from lightyear_calibration.contracts import read_json,require
from lightyear_calibration.journey_order import file_hash,save
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_calibration.transaction_observer import verify_capture
from lightyear_control_tower.decisions import verify_envelope

RUN_IDS=(
    'journey-e28a0c204db04e4880c7929585954bb1',
    'journey-90d75fc601b84ddb87a2591e42947f0f',
    'journey-fa89ca1c8b8640a79d3dc7ba8e1f8ffb',
    'journey-0876955b3bc14e65b18a530ba6882a88',
)


def publish(root,output):
    require(not output.exists(),'Use a new publication directory')
    signer=JourneySigner(root);output.mkdir(parents=True);outcomes=[]
    for run_id in RUN_IDS:
        source=root/'factory/idempiere/ms86-journeys/runs'/run_id
        result=read_json(source/'receipt.json')
        require(verify_envelope(result,signer.public),'Invalid qualification signature')
        dest=output/run_id;dest.mkdir()
        for name in ('plan.json','authorization.json','cleanup.json','receipt.json'):
            shutil.copyfile(source/name,dest/name)
        for name in ('observers','qualification-source'):
            if (source/name).exists():shutil.copytree(source/name,dest/name)
        outcomes.append({'run_id':run_id,'passed':result['passed'],
            'cleanup_complete':result['cleanup_complete'],'error':result['error'],
            'lanes':{lane:{'lock_witnesses':len(v['lock_witnesses']),'rollback_witnesses':len(v['rollback_witnesses'])} for lane,v in result['results'].items()},
            'original_source_available':(source/'qualification-source').exists()})
    files={p.relative_to(output).as_posix():file_hash(p) for p in output.rglob('*') if p.is_file()}
    manifest=signer.sign({'artifact_type':'native-observer-qualification-publication','files':files,
        'outcomes':outcomes,'final_qualification':RUN_IDS[-1],'model_calls':0,'scored_journeys':0,
        'authority_sha256':hashlib.sha256(signer.public).hexdigest(),
        'scope':'Engine observer qualification only; application row snapshots remain in local qualification runs.',
        'failed_pre_freeze_attempts_preserved':True,'independently_attested':False})
    save(output/'manifest.json',manifest);(output/'authority.public.pem').write_bytes(signer.public)
    return manifest


def verify(output,trusted_key_sha256):
    key=(output/'authority.public.pem').read_bytes();m=read_json(output/'manifest.json')
    require(hashlib.sha256(key).hexdigest()==trusted_key_sha256 and verify_envelope(m,key),'Untrusted manifest')
    for name,expected in m['files'].items():
        p=(output/name).resolve();require(p.is_relative_to(output.resolve()) and file_hash(p)==expected,'Changed publication file: '+name)
    final=output/m['final_qualification'];receipt=read_json(final/'receipt.json')
    require(verify_envelope(receipt,key) and receipt['passed'] and receipt['cleanup_complete'],'Final qualification failed')
    source=Path(__file__).resolve().parents[1]/'src/lightyear_calibration'
    for name in ('transaction_observer.py','observer_runtime.py','observer_probe.py'):
        require(file_hash(source/name)==file_hash(final/'qualification-source'/name),'Verifier is not qualified implementation')
    for lane in ('oracle','postgresql'):
        result=verify_capture(final/'observers'/lane)
        require(result==receipt['results'][lane] and result['passed'],'Native observer replay differs')
    return {'status':'verified-native-observer-qualification','outcomes':len(m['outcomes']),
            'final_passed':True,'new_native_executions':0,'new_model_calls':0}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('publish','verify'))
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--trusted-key-sha256');a=p.parse_args()
    result=publish(a.root.resolve(),a.output.resolve()) if a.command=='publish' else verify(a.output,a.trusted_key_sha256)
    import json
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','outcomes','signature')},indent=2))


if __name__=='__main__':main()
