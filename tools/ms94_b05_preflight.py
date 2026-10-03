"""One-shot zero-model executable integration check, never autonomous measurement."""
import hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,require,verify
from lightyear_calibration.journey_order import save,file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_signer_v5 import JourneySigner
from tools.ms94_b05_admission import PREFLIGHT,CONFIG,PLAN,DECLARATION,bindings,preflight_authorization,actual_cleanup
from tools.ms94_calendar_sources import source
from tools.ms94_b05_controller import builder_prompt,prepare_feedback

def receive_without_model(root,campaign,payload):
    """Actual byte receiver for preflight only; it returns a pinned fixture, not an AI repair."""
    value=json.loads(payload)
    require(value['analyst_feedback'] and all(d['category']=='candidate-runtime-exception' and d['thrown_by']=='candidate'
        for d in value['analyst_feedback']), 'Direct candidate diagnostic was not received')
    path,manifest=source(root,'retained')
    (campaign/'receiver-prompt.json').write_bytes(payload)
    save(campaign/'receiver.json',JourneySigner(root).sign({'role':'zero-model-builder-interface-receiver',
        'received_prompt_sha256':hashlib.sha256(payload).hexdigest(),'received_diagnostics':value['analyst_feedback'],
        'returned_fixture_sha256':manifest['harness_sha256'],'model_calls':0,'analyst_calls':0,
        'limitation':'A deterministic receiver proves delivery bytes only; it does not demonstrate model repair.'}))
    return path

def audit(root,campaign):
    plan,snapshot=bindings(root)
    key=(root/'work/ms87/operator/authority.public.pem').read_bytes()
    receipt=read_json(campaign/'receipt.json')
    require(verify_envelope(receipt,key) and receipt['snapshot_sha256']==snapshot['content_sha256'], 'Preflight receipt differs')
    require(receipt['model_calls']==0 and not list(campaign.rglob('invocation.json')), 'Preflight cannot contain model invocations')
    require(len(receipt['attempts'])==2, 'Preflight must contain both fixed native attempts')
    from tools.ms94_b05_evidence import verify_attempt
    from tools.ms94_v6_gate import evaluate
    for i,attempt in enumerate(receipt['attempts']):
        run=root/attempt['run_directory'];native=read_json(run/'receipt.json')
        require(native['content_sha256']==attempt['receipt_sha256'] and native['model_calls']==0 and not native['agent_generated'], 'Preflight native binding differs')
        expected,manifest=source(root,'retained','invoice-null-dereference' if i==0 else None)
        require((run/'inputs/operations.java').read_bytes()==expected.read_bytes(), 'Preflight candidate was rewritten')
        require(native['status']==('execution-failure' if i==0 else 'passed') and native['error'] is None, 'Unexpected preflight native outcome')
        recorded=read_json(run/'gate.json');require(evaluate(run)==recorded,'Preflight full judge replay differs')
        verify_attempt(root,run,key)
    first=root/receipt['attempts'][0]['run_directory']
    observed=read_json(first/'diagnostic-projection.json')['diagnostics']
    routed=read_json(campaign/'feedback.json');require(verify_envelope(routed,key),'Feedback signature differs')
    expected=prepare_feedback(observed,False)
    require(all(routed.get(k)==v for k,v in expected.items()), 'Direct routing differs')
    previous=(first/'inputs/operations.java').read_text(encoding='utf-8')
    prompt=builder_prompt(read_json(root/CONFIG/'preflight.json')['initial_prompt'],previous,expected['diagnostics'])
    require((campaign/'receiver-prompt.json').read_bytes()==canonical(prompt), 'Received builder prompt bytes differ')
    received=read_json(campaign/'receiver.json')
    require(verify_envelope(received,key) and received['received_prompt_sha256']==file_hash(campaign/'receiver-prompt.json')
            and received['received_diagnostics']==observed and received['model_calls']==0 and received['analyst_calls']==0,
            'Direct delivery receiver differs')
    retained,_=source(root,'retained')
    require(received['returned_fixture_sha256']==file_hash(retained), 'Receiver fixture differs')
    second=root/receipt['attempts'][1]['run_directory']
    require(read_json(second/'diagnostic-projection.json')['diagnostics']==[] and not read_json(second/'receipt.json')['equipment_suspect'], 'Retained reference diagnostics/suspicion differ')
    return {'verified':True,'full_entry_replayed':True,'complete_gate_replayed':True,'diagnostic_replayed':True,
            'calendar_replayed':True,'provenance_replayed':True,'delivery_replayed':True,'model_calls':0}

def run(root):
    from tools.ms94_b05_supervisor import remaining_work
    remaining_work(root,root/PREFLIGHT)
    from tools.ms94_b05_native import execute_native
    from tools.ms94_b05_publication import publish,replay
    auth=preflight_authorization(root);_,snapshot=bindings(root,True)
    campaign=root/PREFLIGHT;signer=JourneySigner(root)
    with (campaign/'started.json').open('xb') as f:f.write(canonical({'authorization_sha256':auth['content_sha256'],'real_utc':datetime.now(timezone.utc).isoformat()}))
    started=time.monotonic();attempts=[];replays=[];cleanup=[];error=None;replay_seconds=0
    try:
        candidate,_=source(root,'retained','invoice-null-dereference')
        for index in (1,2):
            preflight_authorization(root)
            build=campaign/f'attempt-{index}'/'build';(build/'workspace').mkdir(parents=True,exist_ok=False)
            target=build/'workspace/LightyearOperationsTest.java';target.write_bytes(candidate.read_bytes())
            fixture=signer.sign({'artifact_type':'b05-preflight-fixture-candidate','harness_sha256':file_hash(target),
                'provider_invocations':0,'agent_generated':False,'fixture_only':True,'autonomous_success':False})
            save(build/'receipt.json',fixture)
            native,nr=execute_native(root,campaign,build,fixture,7200-(time.monotonic()-started))
            attempts.append({'run_directory':native.relative_to(root).as_posix(),'receipt_sha256':nr['content_sha256']})
            save(campaign/'progress.json',signer.sign({'attempts':attempts,'model_calls':0}))
            require(nr['error'] is None and nr['cleanup_complete'] and nr['calendar_checks'], 'Native preflight evidence or cleanup failed')
            cleanup+=actual_cleanup(native)
            require(nr['status']==('execution-failure' if index==1 else 'passed'), 'Unexpected preflight outcome')
            projected=read_json(native/'diagnostic-projection.json')
            require(not projected['equipment_suspect'], 'Preflight equipment-suspect')
            if index==1:
                feedback=prepare_feedback(projected['diagnostics'],False)
                require(feedback['diagnostics'] and feedback['runtime_forwarded_ids'] and feedback['analyst_proposal'] is None, 'Candidate exception did not bypass analyst')
                save(campaign/'feedback.json',signer.sign(feedback))
                prompt=builder_prompt(read_json(campaign/'plan.json')['initial_prompt'],candidate.read_text(encoding='utf-8'),feedback['diagnostics'])
                candidate=receive_without_model(root,campaign,canonical(prompt))
            print(json.dumps({'event':'preflight-native-complete','index':index,'status':nr['status']}),flush=True)
        save(campaign/'receipt.json',signer.sign({'artifact_type':'b05-zero-model-preflight-native-receipt',
            'snapshot_sha256':snapshot['content_sha256'],'attempts':attempts,'model_calls':0,'agent_generated':False}))
        checks=audit(root,campaign)
        for index,attempt in enumerate(attempts,1):
            publication=root/'work/ms94/stage-b-05-r2-preflight-publications'/str(index)
            one=time.monotonic();publish(root,root/attempt['run_directory'],publication)
            verified=replay(root,publication,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
            require(all(verified.get(k) for k in ('full_entry_replayed','complete_gate_replayed','diagnostic_replayed','calendar_replayed','provenance_replayed','delivery_replayed')), 'Incomplete preflight replay')
            replays.append(verified);replay_seconds+=time.monotonic()-one
            save(publication/'verification.json',signer.sign(verified))
            print(json.dumps({'event':'preflight-archive-replayed','index':index}),flush=True)
        cleanup_after=[r for a in attempts for r in actual_cleanup(root/a['run_directory'])]
        require(cleanup_after==cleanup,'Cleanup changed after replay');bindings(root,True)
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        save(campaign/'stopping.json',signer.sign({'error':error,'notify_immediately':True,'model_calls':0}))
        print(json.dumps({'event':'preflight-stopping','error':error}),flush=True)
    report=signer.sign({'artifact_type':'ms94-b05-zero-model-preflight-report','passed':error is None,
        'approved_plan_sha256':PLAN,'approved_declaration_sha256':DECLARATION,'snapshot_sha256':snapshot['content_sha256'],
        'authorization_sha256':auth['content_sha256'],'attempts':attempts,'replays':replays,'actual_cleanup':cleanup,
        'model_calls':0,'analyst_calls':0,'autonomous_successes':0,'measurement_started':False,
        'native_pair_count':len(attempts),'native_elapsed_seconds':sum(read_json(root/a['run_directory']/'receipt.json')['elapsed_seconds'] for a in attempts),
        'independent_replay_and_archive_seconds':round(replay_seconds,3),'total_preflight_seconds':round(time.monotonic()-started,3),
        'preparation_total_monotonic_seconds':None,'error':error,'b04_status':'VOID',
        'review':'Operator review; not independent',
        'limitation':'Zero-model fixture receiver proves delivery, not AI repair; preflight is excluded from measurement rates and budgets.'})
    save(campaign/'report.json',report)
    print(json.dumps({'event':'preflight-terminal','passed':report['passed'],'report_sha256':report['content_sha256']}),flush=True)
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();run(a.root.resolve())
