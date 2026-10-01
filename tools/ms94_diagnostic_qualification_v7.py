"""A fresh A2 revision; the stopped A2 and all its unstarted slots stay closed."""
import hashlib
import json
import time
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_calibration.journey_order import save, file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard
from tools.ms94_signer_v5 import JourneySigner
from tools.ms94_v6_gate import VERSION, EQUIPMENT_REVISION

REVIEW = Path('docs/calibration/idempiere-ms94/stage-b-03/operator-adjudication.json')


def schedule(root):
    from tools.ms94_diagnostic_controls_v7 import FAULTS
    return [{'fault':fault,'repeat':repeat} for fault in FAULTS for repeat in range(1,4)]


def prepare(root, output):
    root,output=Path(root),Path(output); manifest=guard(root)
    a1=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a1'
    base=read_json(a1/'plan.json');verify(base)
    report=read_json(a1/'report.json');terminal=read_json(a1/'terminal-verification.json')
    public=(root/'work/ms87/operator/authority.public.pem').read_bytes()
    require(all(verify_envelope(v,public) for v in (report,terminal)),'A1 signature invalid')
    require(report['passed'] and len(report['results'])==30 and terminal['cleanup_verified']
            and len(terminal['publications'])==30 and all(x['verified'] for x in terminal['publications'])
            and terminal['report_sha256']==report['content_sha256'],'A1 terminal verification incomplete')
    prior=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a2'
    failed=read_json(prior/'report.json');checked=read_json(prior/'terminal-verification.json')
    require(all(verify_envelope(v,public) for v in (failed,checked)),'Prior failure signature invalid')
    require(failed['content_sha256']=='fc3b818e5fd142c2e92861f3541d493921c9a817b6071eaaa98cdf236387f4ac'
            and failed['passed'] is False and checked['report_sha256']==failed['content_sha256']
            and checked['cleanup_verified'] and len(checked['publications'])==13
            and all(x['verified'] for x in checked['publications']), 'Prior A2 failure must be preserved and verified')
    review=read_json(root/REVIEW)
    require(review['accepted_decisions']==[1,2,3,4] and review['b04_classification_prerequisite_satisfied'],
            'Completed classification acceptance missing')
    require(file_hash(root/'docs/calibration/idempiere-ms94/stage-b-03/classification.json')==review['classification_sha256'],
            'Accepted classification differs')
    require(not output.exists() and output.resolve().is_relative_to(root.resolve()),'Use one new qualification directory')
    plan=seal({'artifact_type':'ms94-b04-stage-a2-r1-diagnostic-qualification','judge_version':VERSION,
        'equipment_revision':EQUIPMENT_REVISION,'base_plan':base['base_plan'],
        'a1_plan_sha256':base['content_sha256'],'a1_report_sha256':report['content_sha256'],'a1_verification_sha256':terminal['content_sha256'],'implementation_sha256':manifest['files'],
        'revision':'a2-r1','prior_failed_plan_sha256':'75f2be3accefd6912cfeaecb99da6a7767ac25cba36130c9567b15f20651c790',
        'prior_failed_report_sha256':'fc3b818e5fd142c2e92861f3541d493921c9a817b6071eaaa98cdf236387f4ac',
        'user_authorization':'yes to 1,2,3 and 4: repair control, fresh qualification, A3 then B04 behind gates',
        'control_revision':'Omit draft database write and post-rollback wait; original wait-only control remains failed.',
        'original_wait_only_control_qualified':False,
        'classification_review_sha256':file_hash(root/REVIEW),'schedule':schedule(root),
        'maximum_pairs':len(schedule(root)),'max_elapsed_seconds':8*3600,'model_calls':0,
        'stop_on_first_nonpass':True,'restarts_allowed':False,'replace_slots':False,
        'execution_snapshot_sha256':manifest['content_sha256'],
        'diagnostic_module':'tools.qualification_feedback_v4','judge_module':'tools.ms94_v6_gate',
        'diagnostic_contract':{'category':'candidate-runtime-exception','private_values_permitted':False},
        'a3_complete':False,
        'limitations':['A2 alone cannot admit B04. A3 native value-invariance remains required.',
                      'Operator review is not independent human source attestation of reference variants.',
                      'Purchasing mutants are excluded because this recheck covers only operations.'],
        'source_transfer':False,'cloud_resources':False})
    save(output/'plan.json',plan)
    save(output/'declaration.json',JourneySigner(root).sign({'plan_sha256':plan['content_sha256'],'model_calls':0}))
    return plan


def run(root, output):
    from tools.ms94_diagnostic_native_v7 import qualify
    from tools.ms94_diagnostic_publication_v7 import publish,replay
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
            receipt=qualify(root,trial,fault=slot['fault'],equipment_plan=plan,remaining_seconds=remaining)
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
    value=signer.sign({'artifact_type':'ms94-b04-stage-a2-r1-result','plan_sha256':plan['content_sha256'],
        'passed':passed,'results':results,'unstarted_slots':len(plan['schedule'])-len(results),'error':error,
        'model_calls':0,'elapsed_seconds':round(time.monotonic()-started,3),'b04_admitted':False,
        'scope':'Diagnostic qualification only; A3 remains required before any model execution.'})
    save(output/'report.json',value);return value


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.root.resolve(),a.output.resolve()),indent=2))
