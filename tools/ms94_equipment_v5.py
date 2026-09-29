"""Three fresh controls for the one approved public-contract delta; no generation."""
import hashlib
import json
import time
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_calibration.journey_order import save
from tools.ms94_signer_v5 import JourneySigner
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard
from tools.ms94_stage_b_evidence import stage_a
from tools.ms94_snapshot_v5 import EVIDENCE
from tools.ms94_v5_gate import VERSION

SCHEDULE = ['retained', 'equivalent', 'alternate']


def prepare(root, output):
    root, output = Path(root), Path(output)
    manifest = guard(root); base, _ = stage_a(root, root/EVIDENCE, live=True)
    require(not output.exists(), 'Never replace a qualification declaration')
    plan = seal({'artifact_type':'ms94-invoice-type-extension-qualification','judge_version':VERSION,
        'base_equipment_plan_sha256':base['content_sha256'],'base_plan':base['base_plan'],
        'implementation_sha256':manifest['files'],'schedule':SCHEDULE,'maximum_pairs':3,
        'max_elapsed_seconds':3*3600,'model_calls':0,'stop_on_first_nonpass':True,
        'execution_snapshot_sha256':manifest['content_sha256'],
        'rule':'Retain original invoice type derived from the completed order document type',
        'single_change':True,'smoke_tool_added':False,'diagnostics_widened':False})
    signer = JourneySigner(root)
    save(output/'plan.json',plan)
    save(output/'declaration.json',signer.sign({'plan_sha256':plan['content_sha256'],'model_calls':0}))
    return plan


def run(root, output):
    from tools.ms94_native_v5 import qualify
    from tools.ms94_publication_v5 import publish, replay
    root, output = Path(root), Path(output)
    guard(root); plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    auth=read_json(output/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['plan_sha256']==plan['content_sha256']
            and auth['explicit_user_authorization'], 'Qualification approval differs')
    require(plan['schedule']==SCHEDULE and plan['model_calls']==0, 'Qualification schedule changed')
    with (output/'started.json').open('x') as f:json.dump({'at':time.time(),'plan_sha256':plan['content_sha256']},f)
    started=time.monotonic();results=[];error=None
    try:
        for i, profile in enumerate(SCHEDULE,1):
            guard(root);require(time.monotonic()-started<plan['max_elapsed_seconds'],'Qualification elapsed budget exhausted')
            trial=output/'attempts'/f'{i:02d}-{profile}';trial.parent.mkdir(exist_ok=True)
            receipt=qualify(root,trial,reference_profile=profile,equipment_plan=plan,
                            remaining_seconds=plan['max_elapsed_seconds']-(time.monotonic()-started))
            native=root/read_json(trial/'run.json')['run_directory']
            item={'profile':profile,'run_directory':native.relative_to(root).as_posix(),
                  'status':receipt['status'],'qualification_check_passed':receipt['qualification_check_passed'],
                  'receipt_sha256':receipt['content_sha256'],'cleanup_complete':receipt['cleanup_complete'],
                  'publication_verified':False}
            results.append(item);save(output/'progress.json',signer.sign({'results':results}))
            if not item['qualification_check_passed']:
                save(output/'stopping.json',signer.sign({'profile':profile,'status':receipt['status'],'notify_immediately':True}))
                print(json.dumps({'event':'stopping','profile':profile,'status':receipt['status']}),flush=True)
            pub=output/'publications'/f'{i:02d}'
            publication=publish(root,native,pub)
            checked=replay(root,pub,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
            save(pub/'verification.json',signer.sign(checked));item.update(publication_verified=True,publication_receipt_sha256=publication['content_sha256'])
            save(output/'progress.json',signer.sign({'results':results}))
            if not item['qualification_check_passed']:break
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
    passed=len(results)==3 and all(x['qualification_check_passed'] and x['cleanup_complete'] and x['publication_verified'] for x in results) and not error
    value=signer.sign({'artifact_type':'ms94-invoice-type-extension-result','plan_sha256':plan['content_sha256'],
        'passed':passed,'results':results,'unstarted_slots':3-len(results),'error':error,
        'model_calls':0,'elapsed_seconds':round(time.monotonic()-started,3),
        'scope':'Only the declared invoice-type acceptance delta, inheriting unchanged accepted equipment-04; not a new 62-pair qualification.'})
    save(output/'report.json',value);return value


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.root.resolve(),a.output.resolve()),indent=2))
