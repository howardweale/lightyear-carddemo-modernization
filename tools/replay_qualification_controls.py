"""Reassess preserved native controls in a disposable workspace; never rewrite a run."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
from lightyear_calibration.contracts import require,read_json,verify
from lightyear_calibration.journey_order import RUNS,file_hash,save
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_control_tower.decisions import verify_envelope
from tools.qualify_journey_judge import EXPECTED_REJECTION


def replay(root, output):
    root=Path(root).resolve();output=Path(output).resolve()
    require(not output.exists() and output.is_relative_to(root),'Use a new reassessment output')
    signer=JourneySigner(root);results=[]
    names=['reference-support-isolated-02',*('negative-'+f+'-01' for f in EXPECTED_REJECTION)]
    pins={p.relative_to(root).as_posix():file_hash(p) for p in (root/'src').rglob('*.py')}
    for name in names:
        original=root/read_json(root/'work/ms93'/name/'run.json')['run_directory']
        receipt=read_json(original/'receipt.json');plan=read_json(original/'plan.json')
        gate=read_json(original/'gate.json');cleanup=read_json(original/'cleanup.json')
        require(verify_envelope(receipt,signer.public),'Invalid original receipt')
        verify(plan);verify(gate)
        require(receipt['plan_sha256']==plan['content_sha256'] and receipt['gate_sha256']==gate['content_sha256'],
                'Original gate binding changed')
        require(verify_envelope(cleanup,signer.public) and cleanup['complete'],'Original cleanup not verified')
        for rel,sha in plan['implementation_sha256'].items():
            require(file_hash(original/'qualification-source'/rel)==sha,'Archived implementation changed')
        before={p.relative_to(original).as_posix():file_hash(p) for p in original.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory(prefix='qualification-replay-') as temporary:
            target=Path(temporary);run=target/RUNS/original.name
            shutil.copytree(root/'src',target/'src',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(root/'factory/idempiere/qualification/public',target/'factory/idempiere/qualification/public')
            trust=target/'work/ms87/operator';trust.mkdir(parents=True)
            (trust/'authority.public.pem').write_bytes(signer.public)
            shutil.copytree(original,run,ignore=shutil.ignore_patterns('qualification-source','application-output'))
            env={**os.environ,'PYTHONPATH':str(target/'src'),'PYTHONUTF8':'1'}
            command='from pathlib import Path; from lightyear_calibration.qualified_judge_v3 import evaluate; evaluate(Path('+repr(str(run))+'))'
            proc=subprocess.run([sys.executable,'-c',command],cwd=target,env=env,capture_output=True,timeout=180)
            require(proc.returncode==0,'Reassessment process failed')
            actual=read_json(run/'gate.json');verify(actual)
        require(before=={p.relative_to(original).as_posix():file_hash(p) for p in original.rglob('*') if p.is_file()},
                'Original run changed during reassessment')
        expected='passed' if receipt['fault']=='none' else 'business-failure'
        intended=receipt['fault']=='none' or (actual.get('error') or {}).get('message')==EXPECTED_REJECTION[receipt['fault']]
        require(actual['status']==expected and intended,'New judge failed a preserved native control')
        if receipt['fault']=='none':
            for lane in ('oracle','postgresql'):
                execution=read_json(original/'cases/operations/1/execution'/lane/'execution.json')
                require(execution['private_judge_mount'] is False,'Application had judge access')
                require({x['destination'] for x in execution['application_mounts']}==
                        {'/candidate/LightyearOperationsTest.java','/runtime/worker.py','/results'},'Unexpected mount')
        results.append({'run_id':original.name,'fault':receipt['fault'],'original_receipt_sha256':receipt['content_sha256'],
            'original_judge_version':receipt['judge_version'],'reassessment_judge_version':actual['judge_version'],
            'original_gate_sha256':gate['content_sha256'],'reassessment_gate_sha256':actual['content_sha256'],
            'status':actual['status'],'intended_rejection':intended,'original_unchanged':True,
            'cleanup_verified':True,'native_execution_repeated':False})
    require(all(file_hash(root/p)==sha for p,sha in pins.items()),'Reassessment implementation changed')
    result=signer.sign({'artifact_type':'versioned-native-control-reassessment','status':'passed-bounded-controls',
        'judge_version':'idempiere-qualified-judge-v3','controls':results,'implementation_sha256':pins,
        'autonomous_success':False,'model_calls':0,'reference_scope_review':'Original operations scope accepted; support source not separately human-reviewed.',
        'limits':['One fresh isolated support reference and four previously executed native fault captures.',
                  'Negative captures were replayed under the new judge, not rerun on fresh databases.',
                  'This qualifies bounded test equipment, not an autonomous success rate or every possible defect.']})
    save(output,result);return result


if __name__=='__main__':
    result=replay(Path('.'),Path('work/ms93/isolated-control-reassessment.json'))
    print(json.dumps({'status':result['status'],'controls':len(result['controls'])}))
