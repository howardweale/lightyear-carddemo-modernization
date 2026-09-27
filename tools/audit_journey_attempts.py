"""Publish immutable attempt plans and separately verify unchanged judge hashes."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.journey_order import RUNS, file_hash, save
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_control_tower.decisions import verify_envelope

CORE_JUDGE=('partial_invoicing.py','journey_verify.py','application_effects.py')
MS88=(('build-01',None),('build-02','journey-0b42f23e1bdd43159c248572669e4d07'),
      ('build-03','journey-71ac2046378c4ac6a181005752bba409'),
      ('build-04','journey-c471ac0ea973422d8da460a19fa15a6a'),
      ('build-05','journey-be7ca0651d3c45a7bde77136a69006f1'))


def publish_ms88(root,output):
    require(not output.exists(),'Attempt publication already exists')
    output.mkdir(parents=True);signer=JourneySigner(root);records=[]
    for name,run_id in MS88:
        build=root/'work/ms88'/name;folder=output/name;folder.mkdir()
        invocation=read_json(build/'invocation.json')
        shutil.copyfile(build/'invocation.json',folder/'invocation.json')
        record={'attempt':name,'invocation_sha256':file_hash(folder/'invocation.json'),'run_id':run_id,
                'judge_sha256':None,'usage':None,'builder_elapsed_seconds':None,'native_elapsed_seconds':None}
        if run_id:
            run=root/RUNS/run_id;plan=read_json(run/'plan.json');verify(plan)
            receipt=read_json(run/'receipt.json');builder=read_json(build/'receipt.json')
            auth=read_json(run/'authorization.json')
            require(verify_envelope(receipt,signer.public) and verify_envelope(builder,signer.public) and verify_envelope(auth,signer.public),'Original signature differs')
            require(receipt['plan_sha256']==auth['plan']['plan_sha256']==plan['content_sha256'],'Original plan binding differs')
            for file in ('plan.json','authorization.json','receipt.json'):shutil.copyfile(run/file,folder/file)
            shutil.copyfile(build/'receipt.json',folder/'builder-receipt.json')
            journal=read_json(run/'journal.json')
            start,end=journal[0]['at'],journal[-1]['at']
            elapsed=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
            record.update(judge_sha256={name:plan['implementation_sha256']['src/lightyear_calibration/'+name] for name in CORE_JUDGE},
                plan_sha256=plan['content_sha256'],receipt_sha256=receipt['content_sha256'],builder_receipt_sha256=builder['content_sha256'],
                status=receipt['status'],usage=builder.get('usage'),builder_elapsed_seconds=builder.get('elapsed_seconds'),
                native_elapsed_seconds=elapsed,started_at=start,ended_at=end,
                native_readback_gate='attempted' if (run/'gate-logs/verify-partial-invoicing.log').exists() else 'not-reached')
        else:record.update(status='transport-failed-before-generation',judge_not_executed=True)
        records.append(record)
    observed=[r['judge_sha256'] for r in records if r['judge_sha256']]
    require(all(v==observed[0] for v in observed),'MS88 judge changed between native attempts')
    known=[r['usage'] for r in records if r['usage'] is not None]
    summary=signer.sign({'artifact_type':'lightyear-ms88-attempt-audit','records':records,
        'core_judge_unchanged_across_native_attempts':True,
        'hash_scope':'Three semantic gate modules pinned in each plan; a compile or harness failure may stop before readback. Every full original plan also publishes its complete implementation and input hash map.',
        'cost':{'client_invocations':len(records),'failed_transports':1,'native_attempts':4,'failed_native_attempts':3,
            'known_input_tokens':sum(u['input_tokens'] for u in known),'known_output_tokens':sum(u['output_tokens'] for u in known),
            'calls_with_unknown_usage':1,'usage_complete':False,
            'known_builder_elapsed_seconds':round(sum(r['builder_elapsed_seconds'] or 0 for r in records),3),
            'native_elapsed_seconds':round(sum(r['native_elapsed_seconds'] or 0 for r in records),3),
            'total_elapsed_seconds':None,'billed_usd':None,
            'limitations':'The first failed transport did not record usage or elapsed time. Gaps between attempts include human work; no complete campaign wall time or per-call bill was recorded.'},
        'retrospective_report':True,'original_receipts_modified':False,'independently_attested':False})
    save(output/'receipt.json',summary);(output/'authority.public.pem').write_bytes(signer.public)
    return summary


def verify_audit(output):
    value=read_json(output/'receipt.json');key=(output/'authority.public.pem').read_bytes()
    require(verify_envelope(value,key),'Audit signature differs')
    judges=[];expected=None;acceptance=None
    for record in value['records']:
        folder=output/record['attempt']
        require(file_hash(folder/'invocation.json')==record['invocation_sha256'],'Invocation changed')
        if not record['run_id']:
            require(record['judge_sha256'] is None and record['judge_not_executed'],'Unexecuted attempt assigned a judge claim')
            continue
        plan=read_json(folder/'plan.json');verify(plan)
        receipt=read_json(folder/'receipt.json');builder=read_json(folder/'builder-receipt.json');auth=read_json(folder/'authorization.json')
        require(all(verify_envelope(v,key) for v in (receipt,builder,auth)),'Original signature differs')
        require(plan['content_sha256']==record['plan_sha256']==receipt['plan_sha256']==auth['plan']['plan_sha256'],'Plan binding differs')
        require(receipt['content_sha256']==record['receipt_sha256'] and builder['content_sha256']==record['builder_receipt_sha256'],'Receipt binding differs')
        mapping={name:plan['implementation_sha256']['src/lightyear_calibration/'+name] for name in CORE_JUDGE}
        require(mapping==record['judge_sha256'],'Judge hash differs from original plan');judges.append(mapping)
        declaration=plan['extension_declaration']
        if expected is None:expected=declaration['expected'];acceptance=declaration['acceptance']
        require(expected==declaration['expected'] and acceptance==declaration['acceptance'],'Business expectations or acceptance changed')
    require(judges and all(j==judges[0] for j in judges),'Judge changed between attempts')
    return {'status':'verified-attempt-hashes','native_attempts':len(judges),'unchanged_expectations':True,'unchanged_acceptance':True,'independently_attested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['publish-ms88','verify'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=publish_ms88(a.root.resolve(),a.output.resolve()) if a.command=='publish-ms88' else verify_audit(a.output.resolve())
    print(json.dumps(result if a.command=='verify' else {'status':'published','cost':result['cost']},indent=2))


if __name__=='__main__':main()
