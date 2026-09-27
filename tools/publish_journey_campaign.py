"""Export every agent call and native attempt without retained databases or keys.

This checks provenance/accounting. Full native gate replay is a separate archive.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from lightyear_calibration.contracts import canonical,read_json,require,verify
from lightyear_calibration.journey_order import RUNS,file_hash,save
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_calibration.journey_repair import cost_report,select_feedback
from lightyear_control_tower.decisions import verify_envelope
if __package__:
    from tools.publish_native_journeys import safe_relative,verify_run_identity
else:
    from publish_native_journeys import safe_relative,verify_run_identity


def publish(root,campaign,output):
    require(not output.exists(),'Campaign publication already exists')
    signer=JourneySigner(root);receipt=read_json(campaign/'receipt.json')
    require(verify_envelope(receipt,signer.public),'Campaign signature differs')
    paths=[campaign/name for name in ('plan.json','authorization.json','receipt.json','attempts.json')]
    paths.extend(campaign.glob('feedback-*.json'));paths.extend(campaign.glob('analyst-input-*.json'))
    if (campaign/'resume-proposal.json').exists():paths.append(campaign/'resume-proposal.json')
    paths.extend((campaign/'history').glob('*.json'))
    for call in sorted((campaign/'calls').glob('*')):
        paths.extend(call/name for name in ('invocation.json','receipt.json','prompt.json','schema.json','events.jsonl','proposal.json') if (call/name).exists())
    # Original controller snapshots make the acknowledged framework fix reviewable.
    paths.extend((root/'work/ms89').glob('journey_*.py'))
    for attempt in receipt['attempts']:
        run=root/RUNS/attempt['run_id'];verify_run_identity(run,signer.public)
        paths.extend(run/name for name in ('plan.json','authorization.json','receipt.json','cleanup.json','journal.json','authority.public.pem'))
        for where in sorted((run/'cases/partial-invoicing').glob('*/execution/*')):
            paths.extend(where/name for name in ('execution.json','harness.java','maven.log','journey.xml') if (where/name).exists())
        # Preserve paired findings even when the unchanged comparison gate fails.
        paths.extend((run/'cases/partial-invoicing').glob('*/verified/*.json'))
        paths.extend((run/'gate-logs').glob('*.log'))
        for name in ('gate.json','selected-attempts.json'):
            if (run/name).exists():paths.append(run/name)
        build=root/attempt['builder_directory']
        paths.extend(build/name for name in ('receipt.json','prompt.json','proposal.json','events.jsonl','invocation.json','workspace/LightyearPartialInvoiceTest.java'))
    paths.extend(root/name for name in read_json(campaign/'plan.json')['public_input_sha256'])
    paths.append(root/'factory/idempiere/analyst-repair/campaign.json')
    files={}
    for path in paths:
        require(not path.is_symlink(),'Symbolic publication source')
        relative=path.relative_to(root).as_posix();safe_relative(relative)
        files[relative]={'sha256':file_hash(path),'bytes':path.stat().st_size}
    output.mkdir(parents=True)
    manifest=signer.sign({'artifact_type':'lightyear-journey-campaign-audit','campaign':campaign.relative_to(root).as_posix(),
        'campaign_receipt_sha256':receipt['content_sha256'],'files':files,
        'verification_scope':'Agent provenance, attempt signatures, pinned judges and accounting. Does not itself replay the native database gate.',
        'independently_attested':False})
    with zipfile.ZipFile(output/'campaign-audit.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',canonical(manifest))
        for name in sorted(files):z.write(root/name,name)
    summary=signer.sign({'artifact_type':'lightyear-journey-campaign-audit-receipt','manifest_sha256':manifest['content_sha256'],
        'archive_sha256':file_hash(output/'campaign-audit.zip'),'campaign_receipt_sha256':receipt['content_sha256'],
        'status':receipt['status'],'human_authored_repair_bytes':receipt['human_authored_repair_bytes'],'cost':receipt['cost'],
        'attempts':receipt['attempts'],'independently_attested':False})
    save(output/'receipt.json',summary);(output/'authority.public.pem').write_bytes(signer.public)
    return summary


def verify_archive(output):
    summary=read_json(output/'receipt.json');key=(output/'authority.public.pem').read_bytes()
    require(verify_envelope(summary,key) and file_hash(output/'campaign-audit.zip')==summary['archive_sha256'],'Campaign audit changed')
    with zipfile.ZipFile(output/'campaign-audit.zip') as z,tempfile.TemporaryDirectory() as temp:
        root=Path(temp);manifest=json.loads(z.read('manifest.json'))
        require(verify_envelope(manifest,key) and manifest['content_sha256']==summary['manifest_sha256'],'Audit manifest changed')
        require(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(manifest['files'])|{'manifest.json'},'Archive members differ')
        for name,entry in manifest['files'].items():
            safe_relative(name);data=z.read(name)
            require(hashlib.sha256(data).hexdigest()==entry['sha256'] and len(data)==entry['bytes'],'Archive source changed')
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        safe_relative(manifest['campaign']);campaign=root/manifest['campaign']
        result=read_json(campaign/'receipt.json');plan=read_json(campaign/'plan.json');verify(plan)
        require(verify_envelope(result,key) and result['content_sha256']==summary['campaign_receipt_sha256']==manifest['campaign_receipt_sha256'],'Campaign result differs')
        require(result['plan_sha256']==plan['content_sha256'],'Campaign plan differs')
        auth=read_json(campaign/'authorization.json')
        require(verify_envelope(auth,key) and auth['plan_sha256']==plan['content_sha256'],'Campaign authorization differs')
        require(all(summary[k]==result[k] for k in ('status','human_authored_repair_bytes','cost','attempts')),'Published summary differs')
        calls=[]
        for path in sorted((campaign/'calls').glob('*/invocation.json')):
            folder=path.parent;call=read_json(folder/'receipt.json')
            require(verify_envelope(call,key),'Agent call signature differs')
            require(call['builder_client']==plan['builder_client'],'Agent executable identity differs')
            for name,field in [('prompt.json','prompt_sha256'),('events.jsonl','events_sha256'),('proposal.json','proposal_sha256')]:
                if call[field] is not None:require(file_hash(folder/name)==call[field],'Agent call artifact differs')
            if call['role']=='analyst' and call['error'] is None:
                analyst_input=read_json(folder/'prompt.json')
                select_feedback(analyst_input['diagnostics'],read_json(folder/'proposal.json'),
                                require_decisions=analyst_input.get('diagnostic_contract_version')==2)
            calls.append(call)
        require(len(calls)<=plan['max_client_invocations'],'Campaign exceeds authorized client calls')
        previous=None
        public=read_json(root/'factory/idempiere/analyst-repair/builder-input.json')
        for n,attempt in enumerate(result['attempts'],1):
            require(verify_envelope(attempt,key),'Attempt signature differs')
            run=root/RUNS/attempt['run_id'];terminal=verify_run_identity(run,key);native_plan=read_json(run/'plan.json')
            require(terminal['content_sha256']==attempt['receipt_sha256'] and native_plan['content_sha256']==attempt['plan_sha256'],'Attempt/native identity differs')
            require(native_plan['judge_sha256']==attempt['judge_sha256']==plan['judge_sha256'],'Judge changed across attempts')
            build=root/attempt['builder_directory'];builder=read_json(build/'receipt.json')
            require(verify_envelope(builder,key) and builder['content_sha256']==native_plan['builder_receipt_sha256'],'Builder receipt differs')
            require(any(c['role']=='builder' and c['prompt_sha256']==builder['prompt_sha256'] and c['events_sha256']==builder['events_sha256'] and c['proposal_sha256']==builder['proposal_sha256'] for c in calls),'Builder not bound to an agent call')
            proposal=read_json(build/'proposal.json');code=(build/'workspace/LightyearPartialInvoiceTest.java').read_bytes()
            require(hashlib.sha256(code).hexdigest()==attempt['harness_sha256']==builder['harness_sha256']==native_plan['harness_sha256'],'Executed candidate changed')
            require(len(proposal['edits'])==1 and code==proposal['edits'][0]['replace'].encode('utf-8'),'Non-model candidate bytes')
            prompt=dict(public)
            if previous is not None:
                feedback=read_json(campaign/f'feedback-{n-1}.json')
                require(verify_envelope(feedback,key),'Feedback signature differs')
                observations=read_json(campaign/f'analyst-input-{n-1}.json')['diagnostics']
                ids=[d['id'] for d in feedback['diagnostics']]
                require(select_feedback(observations,{'diagnostic_ids':ids})==feedback['diagnostics'],'Untracked diagnostic bytes')
                require(any(c['role']=='analyst'
                    and read_json(p.parent/'prompt.json')['diagnostics']==observations
                    and read_json(p.parent/'prompt.json')['candidate']==previous
                    and select_feedback(observations,read_json(p.parent/'proposal.json'))==feedback['diagnostics']
                    for p in (campaign/'calls').glob('*/receipt.json') for c in [read_json(p)]),'Feedback not selected by an analyst')
                prompt.update(previous_candidate=previous,analyst_feedback=feedback['diagnostics'])
            require(read_json(build/'prompt.json')==prompt,'Untracked repair prompt bytes')
            previous=code.decode('utf-8')
        cost=cost_report(calls,result['attempts'],result['cost']['total_elapsed_seconds'])
        require(all(result['cost'][k]==v for k,v in cost.items()),'Campaign costs omit or alter a call/attempt')
        return {'status':'verified-campaign-provenance-and-accounting','client_invocations':len(calls),
            'native_attempts':len(result['attempts']),'human_authored_repair_bytes':0,
            'native_gate_replayed':False,'independently_attested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['publish','verify'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--campaign',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=publish(a.root.resolve(),a.campaign.resolve(),a.output.resolve()) if a.command=='publish' else verify_archive(a.output.resolve())
    print(json.dumps(result if a.command=='verify' else {'status':result['status'],'cost':result['cost']},indent=2))


if __name__=='__main__':main()
