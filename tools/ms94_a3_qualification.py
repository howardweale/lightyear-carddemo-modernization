"""One frozen paired native checkpoint value-invariance qualification; no models."""
import hashlib,time,json
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,verify,seal
from lightyear_calibration.journey_order import save,file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard
from tools.ms94_signer_v5 import JourneySigner
from tools.ms94_a3_controls import CONTROLS,equal_projections


def schedule():
    return [{'fault':fault,'checkpoint_profile':profile} for fault in CONTROLS for profile in ('admitted','perturbed')]


def prepare(root,output):
    root,output=Path(root).resolve(),Path(output).resolve();manifest=guard(root);signer=JourneySigner(root)
    require(output.is_relative_to(root) and not output.exists(),'Use one new A3 campaign')
    p=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a3-checkpoint-r1'
    prep=read_json(p/'report.json');checked=read_json(p/'terminal-verification.json')
    require(all(verify_envelope(x,signer.public) for x in (prep,checked)),'Untrusted checkpoint preparation')
    require(prep['passed'] and checked['passed'] and checked['report_sha256']==prep['content_sha256']
            and checked['admission_replayed'] and checked['cleanup_verified']
            and checked['checkpoint_sha256']==prep['checkpoint_sha256'],'Checkpoint prerequisite incomplete')
    prior=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a2-r1'
    a2=read_json(prior/'report.json');a2v=read_json(prior/'terminal-verification.json')
    require(all(verify_envelope(x,signer.public) for x in (a2,a2v)) and a2['passed']
            and len(a2['results'])==18 and a2v['cleanup_verified'] and a2v['report_sha256']==a2['content_sha256'],
            'A2 prerequisite invalid')
    private={n:'work/ms94/a3-private-checkpoint/'+n for n in
             ('checkpoint.json','oracle-entry-multisets.json','postgresql-entry-multisets.json')}
    cp=read_json(root/private['checkpoint.json']);verify(cp)
    require(cp['admitted'] and cp['content_sha256']==prep['checkpoint_sha256'],'Wrong private checkpoint')
    value=seal({'artifact_type':'ms94-a3-paired-native-qualification-plan',
        'base_plan':read_json(prior/'plan.json')['base_plan'],
        'preparation_report_sha256':prep['content_sha256'],'preparation_verification_sha256':checked['content_sha256'],
        'a2_report_sha256':a2['content_sha256'],'a2_verification_sha256':a2v['content_sha256'],
        'private_checkpoint_inputs':private,
        'private_checkpoint_input_sha256':{n:file_hash(root/r) for n,r in private.items()},
        'implementation_sha256':manifest['files'],'execution_snapshot_sha256':manifest['content_sha256'],
        'schedule':schedule(),'maximum_pairs':14,'max_elapsed_seconds':8*3600,
        'model_calls':0,'restarts_allowed':False,'replace_slots':False,'stop_on_first_unexpected':True,
        'controls_byte_identical_to_a2_r1':True,'retained_reference_byte_identical_to_a1':True,
        'comparison':'Exact canonical exported diagnostic bytes plus equipment-suspect and disposition equality.',
        'retained_reference_purpose':'Check both checkpoint paths with the unchanged complete business judge before faults.',
        'b04_admitted':False,
        'limitations':['Perturbs stored prices, stock quantities, price-row IDs and active table identifier sequences; not every possible private value.',
                      'Original wait-only omission remains unqualified; stronger missing-stimulus-and-wait control is used.',
                      'No model performance or autonomous cohort success follows from these controls.']})
    save(output/'plan.json',value);save(output/'declaration.json',signer.sign({'plan_sha256':value['content_sha256'],
         'model_calls':0,'maximum_pairs':14,'restarts_allowed':False,'b04_admitted':False}))
    return value


def run(root,output):
    from tools.ms94_a3_native import qualify
    from tools.ms94_a3_publication import publish,replay
    root,output=Path(root).resolve(),Path(output).resolve();guard(root);signer=JourneySigner(root)
    plan=read_json(output/'plan.json');verify(plan)
    require(plan['schedule']==schedule(),'Frozen A3 schedule differs')
    for name in ('authorization.json','declaration.json'):
        record=read_json(output/name)
        require(verify_envelope(record,signer.public) and record['plan_sha256']==plan['content_sha256'],
                'Exact A3 authorization missing')
    require(read_json(output/'authorization.json')['explicit_user_authorization'],'No A3 authority')
    with (output/'started.json').open('x') as f:json.dump({'at':time.time(),'plan_sha256':plan['content_sha256']},f)
    started=time.monotonic();results=[];comparisons=[];error=None
    try:
        for index,slot in enumerate(schedule(),1):
            guard(root);remaining=plan['max_elapsed_seconds']-(time.monotonic()-started)
            require(remaining>0,'A3 time cap reached')
            save(output/'active.json',signer.sign({'index':index,'slot':slot,'started_at':time.time()}))
            trial=output/'attempts'/f'{index:02d}';trial.parent.mkdir(exist_ok=True)
            receipt=qualify(root,trial,equipment_plan=plan,remaining_seconds=remaining,**slot)
            native=root/read_json(trial/'run.json')['run_directory']
            item={'index':index,**slot,'run_directory':native.relative_to(root).as_posix(),
                'status':receipt['status'],'qualification_check_passed':receipt['qualification_check_passed'],
                'receipt_sha256':receipt['content_sha256'],'cleanup_complete':receipt['cleanup_complete'],
                'publication_verified':False}
            results.append(item)
            expected=item['qualification_check_passed'] and item['cleanup_complete']
            if slot['checkpoint_profile']=='perturbed':
                left=root/results[-2]['run_directory'];right=native
                l=read_json(left/'diagnostic-projection.json');r=read_json(right/'diagnostic-projection.json')
                require(all(verify_envelope(x,signer.public) for x in (l,r)),'Untrusted paired diagnostic projection')
                equal=equal_projections(l,r);expected=expected and equal
                comparison={'fault':slot['fault'],'diagnostic_bytes_equal':equal,
                    'admitted_projection_sha256':l['content_sha256'],'perturbed_projection_sha256':r['content_sha256'],
                    'admitted_diagnostic_sha256':l['diagnostic_bytes_sha256'],'perturbed_diagnostic_sha256':r['diagnostic_bytes_sha256']}
                comparisons.append(comparison)
            save(output/'progress.json',signer.sign({'results':results,'comparisons':comparisons}))
            if not expected:
                save(output/'stopping.json',signer.sign({'slot':slot,'status':receipt['status'],
                    'reason':'Unexpected native control or diagnostic inequality','notify_immediately':True}))
                print(json.dumps({'event':'stopping',**slot,'status':receipt['status']}),flush=True)
            pub=output/'publications'/f'{index:02d}';published=publish(root,native,pub)
            verified=replay(root,pub,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
            save(pub/'verification.json',signer.sign(verified))
            item.update(publication_verified=True,publication_receipt_sha256=published['content_sha256'])
            save(output/'progress.json',signer.sign({'results':results,'comparisons':comparisons}))
            if not expected:break
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        save(output/'stopping.json',signer.sign({'error':error,'notify_immediately':True}))
        print(json.dumps({'event':'stopping','error_type':type(exc).__name__}),flush=True)
    passed=(len(results)==14 and len(comparisons)==7 and error is None
        and all(x['qualification_check_passed'] and x['cleanup_complete'] and x['publication_verified'] for x in results)
        and all(x['diagnostic_bytes_equal'] for x in comparisons))
    report=signer.sign({'artifact_type':'ms94-a3-paired-native-qualification-result','plan_sha256':plan['content_sha256'],
        'passed':passed,'results':results,'comparisons':comparisons,'unstarted_slots':14-len(results),'error':error,
        'model_calls':0,'elapsed_seconds':round(time.monotonic()-started,3),'b04_admitted':False,
        'scope':'Six revised planted faults and a retained-reference path check on both checkpoints; no factory success credit.'})
    save(output/'report.json',report);return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.root,a.output),indent=2))
