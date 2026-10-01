"""Stage A'1: fresh operations recheck, no generation or replacement slots."""
import hashlib
import json
import time
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_calibration.journey_order import save, file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard
from tools.ms94_stage_b_admission_v5 import stage_a
from tools.ms94_signer_v5 import JourneySigner
from tools.ms94_v6_gate import VERSION, EQUIPMENT_REVISION

EVIDENCE = Path('docs/calibration/idempiere-ms94/equipment-04')
REVIEW = Path('docs/calibration/idempiere-ms94/stage-b-03/operator-adjudication.json')


def schedule(root):
    base=read_json(Path(root)/EVIDENCE/'plan.json');verify(base)
    mutations=sorted({s['fault'] for s in base['schedule'] if s['scenario']=='operations' and s['fault']!='none'})
    slots=[{'profile':profile,'fault':'none','repeat':i} for profile,count in
           [('retained',10),('equivalent',5),('alternate',3)] for i in range(1,count+1)]
    slots += [{'profile':'retained','fault':fault,'repeat':1} for fault in mutations]
    return slots


def prepare(root, output):
    root,output=Path(root),Path(output); manifest=guard(root)
    base,_=stage_a(root,root/EVIDENCE,live=True)
    review=read_json(root/REVIEW)
    require(review['accepted_decisions']==[1,2,3,4] and review['b04_classification_prerequisite_satisfied'],
            'Completed classification acceptance missing')
    require(file_hash(root/'docs/calibration/idempiere-ms94/stage-b-03/classification.json')==review['classification_sha256'],
            'Accepted classification differs')
    require(not output.exists() and output.resolve().is_relative_to(root.resolve()),'Use one new qualification directory')
    plan=seal({'artifact_type':'ms94-b04-stage-a1-judge-recheck','judge_version':VERSION,
        'equipment_revision':EQUIPMENT_REVISION,'base_plan':base['base_plan'],
        'base_equipment_plan_sha256':base['content_sha256'],'implementation_sha256':manifest['files'],
        'classification_review_sha256':file_hash(root/REVIEW),'schedule':schedule(root),
        'maximum_pairs':len(schedule(root)),'max_elapsed_seconds':8*3600,'model_calls':0,
        'stop_on_first_nonpass':True,'restarts_allowed':False,'replace_slots':False,
        'execution_snapshot_sha256':manifest['content_sha256'],
        'ten_of_ten_false_rejection_upper95':1-0.05**(1/10),
        'limitations':['A1 alone cannot admit B04. A2 diagnostic controls and A3 native value-invariance must also pass.',
                      'Operator review is not independent human source attestation of reference variants.',
                      'Purchasing mutants are excluded because this recheck covers only operations.'],
        'source_transfer':False,'cloud_resources':False})
    save(output/'plan.json',plan)
    save(output/'declaration.json',JourneySigner(root).sign({'plan_sha256':plan['content_sha256'],'model_calls':0}))
    return plan


def run(root, output):
    from tools.ms94_native_v6 import qualify
    from tools.ms94_publication_v6 import publish,replay
    root,output=Path(root),Path(output);guard(root)
    plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    auth=read_json(output/'authorization.json');declaration=read_json(output/'declaration.json')
    require(all(verify_envelope(v,signer.public) and v['plan_sha256']==plan['content_sha256']
                for v in (auth,declaration)) and auth['explicit_user_authorization'],'Exact qualification approval missing')
    require(plan['schedule']==schedule(root) and plan['model_calls']==0,'Qualification schedule differs')
    with (output/'started.json').open('x') as f:json.dump({'at':time.time(),'plan_sha256':plan['content_sha256']},f)
    started=time.monotonic();results=[];error=None
    try:
        for index,slot in enumerate(plan['schedule'],1):
            guard(root); remaining=plan['max_elapsed_seconds']-(time.monotonic()-started)
            require(remaining>0,'Qualification time budget exhausted')
            save(output/'active.json',signer.sign({'index':index,'slot':slot,'started_at':time.time()}))
            trial=output/'attempts'/f'{index:02d}';trial.parent.mkdir(exist_ok=True)
            receipt=qualify(root,trial,fault=slot['fault'],reference_profile=slot['profile'],equipment_plan=plan,remaining_seconds=remaining)
            native=root/read_json(trial/'run.json')['run_directory']
            item={'index':index,**slot,'run_directory':native.relative_to(root).as_posix(),
                  'status':receipt['status'],'qualification_check_passed':receipt['qualification_check_passed'],
                  'receipt_sha256':receipt['content_sha256'],'cleanup_complete':receipt['cleanup_complete'],
                  'publication_verified':False}
            results.append(item);save(output/'progress.json',signer.sign({'results':results}))
            if not item['qualification_check_passed']:
                save(output/'stopping.json',signer.sign({'slot':slot,'status':receipt['status'],'notify_immediately':True}))
                print(json.dumps({'event':'stopping',**slot,'status':receipt['status']}),flush=True)
            publication=output/'publications'/f'{index:02d}'
            published=publish(root,native,publication)
            checked=replay(root,publication,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
            save(publication/'verification.json',signer.sign(checked))
            item.update(publication_verified=True,publication_receipt_sha256=published['content_sha256'])
            save(output/'progress.json',signer.sign({'results':results}))
            if not item['qualification_check_passed']:break
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        save(output/'stopping.json',signer.sign({'error':error,'notify_immediately':True}))
        print(json.dumps({'event':'stopping','error_type':type(exc).__name__}),flush=True)
    passed=len(results)==len(plan['schedule']) and all(x['qualification_check_passed'] and x['cleanup_complete'] and x['publication_verified'] for x in results) and error is None
    value=signer.sign({'artifact_type':'ms94-b04-stage-a1-result','plan_sha256':plan['content_sha256'],
        'passed':passed,'results':results,'unstarted_slots':len(plan['schedule'])-len(results),'error':error,
        'model_calls':0,'elapsed_seconds':round(time.monotonic()-started,3),'b04_admitted':False,
        'scope':'Judge recheck only; A2 and A3 remain required before any model execution.'})
    save(output/'report.json',value);return value


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.root.resolve(),a.output.resolve()),indent=2))
