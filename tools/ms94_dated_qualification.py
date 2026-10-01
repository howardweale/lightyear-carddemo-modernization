"""Fresh qualification of exact dated sources; historical campaigns stay separate."""
import hashlib,json,time
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,verify,seal
from lightyear_calibration.journey_order import save,file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_execution_snapshot import guard
from tools.ms94_signer_v5 import JourneySigner
from tools.ms94_dated_controls import CONTROLS,control

FAILURE='8104c17aa6cdc0b5a977a4998ee0953004d5d2bb569114c351b502c3509f5cea'
DIAGNOSIS='47b28fc0f9b6fce66785bace287a024205c44254959cbc8587192c552389236f'


def schedule():
    return [{'fault':fault,'checkpoint_profile':'admitted','repeat':repeat}
            for fault in CONTROLS for repeat in range(1,11 if fault=='retained-reference' else 4)]


def prepare(root,output):
    root,output=Path(root).resolve(),Path(output).resolve();snapshot=guard(root);signer=JourneySigner(root)
    require(output.is_relative_to(root) and not output.exists(),'Use one new dated-source qualification')
    prior=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a3-r1'
    failure,audit,diagnosis=[read_json(prior/n) for n in ('report.json','terminal-verification.json','clock-diagnosis.json')]
    require(all(verify_envelope(v,signer.public) for v in (failure,audit,diagnosis))
            and failure['content_sha256']==FAILURE and not failure['passed']
            and audit['report_sha256']==FAILURE and audit['cleanup_verified']
            and diagnosis['content_sha256']==DIAGNOSIS and diagnosis['report_sha256']==FAILURE,
            'Original failure and clock diagnosis must remain preserved')
    prepdir=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a3-checkpoint-r1'
    prep,checked=[read_json(prepdir/n) for n in ('report.json','terminal-verification.json')]
    require(all(verify_envelope(v,signer.public) for v in (prep,checked)) and prep['passed']
            and checked['passed'] and checked['report_sha256']==prep['content_sha256']
            and checked['admission_replayed'] and checked['cleanup_verified'], 'Checkpoint preparation invalid')
    a2dir=root/'docs/calibration/idempiere-ms94/equipment-06/stage-a2-r1'
    a2,a2v=[read_json(a2dir/n) for n in ('report.json','terminal-verification.json')]
    require(all(verify_envelope(v,signer.public) for v in (a2,a2v)) and a2['passed']
            and a2v['report_sha256']==a2['content_sha256'] and a2v['cleanup_verified'], 'Historical A2 invalid')
    controls={name:control(root,name)[1] for name in CONTROLS}
    private={n:'work/ms94/a3-private-checkpoint/'+n for n in
             ('checkpoint.json','oracle-entry-multisets.json','postgresql-entry-multisets.json')}
    cp=read_json(root/private['checkpoint.json']);verify(cp)
    require(cp['admitted'] and cp['content_sha256']==prep['checkpoint_sha256'],'Wrong private checkpoint')
    value=seal({'artifact_type':'ms94-explicit-date-source-qualification-plan',
        'base_plan':read_json(a2dir/'plan.json')['base_plan'],
        'prior_failed_report_sha256':FAILURE,'prior_failure_verification_sha256':audit['content_sha256'],
        'clock_diagnosis_sha256':DIAGNOSIS,
        'historical_a2_report_sha256':a2['content_sha256'],
        'preparation_report_sha256':prep['content_sha256'],'preparation_verification_sha256':checked['content_sha256'],
        'private_checkpoint_inputs':private,'private_checkpoint_input_sha256':{n:file_hash(root/p) for n,p in private.items()},
        'implementation_sha256':snapshot['files'],'execution_snapshot_sha256':snapshot['content_sha256'],
        'control_manifests':controls,'schedule':schedule(),'maximum_pairs':28,'max_elapsed_seconds':8*3600,
        'model_calls':0,'restarts_allowed':False,'replace_slots':False,'stop_on_first_unexpected':True,
        'source_change':'Exactly one explicit order.setDateAcct(businessDate) added in each new source.',
        'entry_signing':'Unchanged verified unsealed-body boundary, persisted and verified before execution.',
        'judge_observer_exporter_support_application_clock_changed':False,
        'prior_qualification_credit_for_new_sources':False,'a3_value_invariance_qualified':False,'b04_admitted':False,
        'limitations':['Admitted checkpoint only: ten dated-reference runs and six dated faults three times each; a new paired A3 is still required.',
            'Historical A1 equivalent, alternate-ARI and mutant results remain separate evidence for the unchanged judge, not new dated-source results.',
            'Original wait-only omission remains unqualified; stronger missing-stimulus-and-wait control is used.',
            'The application clock and period-window policy remain unchanged; qualification is bounded to its actual execution dates.',
            'Controls earn no autonomous cohort success and make no model performance claim.']})
    save(output/'plan.json',value)
    save(output/'declaration.json',signer.sign({'plan_sha256':value['content_sha256'],'model_calls':0,
        'maximum_pairs':28,'restarts_allowed':False,'b04_admitted':False}))
    return value


def run(root,output):
    from tools.ms94_dated_native import qualify
    from tools.ms94_a3_publication import publish,replay
    root,output=Path(root).resolve(),Path(output).resolve();guard(root);signer=JourneySigner(root)
    plan=read_json(output/'plan.json');verify(plan)
    require(plan['schedule']==schedule() and plan['maximum_pairs']==28 and plan['model_calls']==0,
            'Frozen dated-source schedule differs')
    for name in ('authorization.json','declaration.json'):
        value=read_json(output/name)
        require(verify_envelope(value,signer.public) and value['plan_sha256']==plan['content_sha256'],
                'Exact dated-source authorization missing')
    require(read_json(output/'authorization.json')['explicit_user_authorization'],'Missing user authority')
    with (output/'started.json').open('x') as stream:
        json.dump({'at':time.time(),'plan_sha256':plan['content_sha256']},stream)
    started=time.monotonic();results=[];error=None
    try:
        for index,slot in enumerate(schedule(),1):
            guard(root);remaining=plan['max_elapsed_seconds']-(time.monotonic()-started)
            require(remaining>0,'Qualification time cap reached')
            save(output/'active.json',signer.sign({'index':index,'slot':slot,'started_at':time.time()}))
            trial=output/'attempts'/f'{index:02d}';trial.parent.mkdir(exist_ok=True)
            receipt=qualify(root,trial,fault=slot['fault'],checkpoint_profile=slot['checkpoint_profile'],
                            equipment_plan=plan,remaining_seconds=remaining)
            native=root/read_json(trial/'run.json')['run_directory']
            item={'index':index,**slot,'run_directory':native.relative_to(root).as_posix(),
                'status':receipt['status'],'qualification_check_passed':receipt['qualification_check_passed'],
                'receipt_sha256':receipt['content_sha256'],'cleanup_complete':receipt['cleanup_complete'],
                'publication_verified':False}
            results.append(item);expected=item['qualification_check_passed'] and item['cleanup_complete']
            save(output/'progress.json',signer.sign({'results':results}))
            if not expected:
                save(output/'stopping.json',signer.sign({'slot':slot,'status':receipt['status'],
                    'reason':'Unexpected native control outcome or cleanup failure','notify_immediately':True}))
                print(json.dumps({'event':'stopping',**slot,'status':receipt['status']}),flush=True)
            pub=output/'publications'/f'{index:02d}'
            published=publish(root,native,pub)
            verified=replay(root,pub,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
            require(verified['full_entry_replayed'] and verified['complete_gate_replayed']
                    and verified['diagnostic_replayed'],'Incomplete publication replay')
            save(pub/'verification.json',signer.sign(verified))
            item.update(publication_verified=True,publication_receipt_sha256=published['content_sha256'])
            save(output/'progress.json',signer.sign({'results':results}))
            if not expected:break
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        save(output/'stopping.json',signer.sign({'error':error,'notify_immediately':True}))
        print(json.dumps({'event':'stopping','error_type':type(exc).__name__}),flush=True)
    passed=len(results)==28 and error is None and all(
        x['qualification_check_passed'] and x['cleanup_complete'] and x['publication_verified'] for x in results)
    report=signer.sign({'artifact_type':'ms94-explicit-date-source-qualification-result',
        'plan_sha256':plan['content_sha256'],'passed':passed,'results':results,
        'unstarted_slots':28-len(results),'error':error,'model_calls':0,
        'elapsed_seconds':round(time.monotonic()-started,3),'b04_admitted':False,
        'a3_value_invariance_qualified':False,
        'scope':'Ten dated reference runs and six dated faults three times each on the admitted checkpoint; prior campaigns remain separate.'})
    save(output/'report.json',report);return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();print(json.dumps(run(args.root,args.output),indent=2))
