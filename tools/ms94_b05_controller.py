"""B05 r2 controller: pre-outcome review amendment, no restarted slots.

Equipment must already have passed Stage A including signed operator reviews (not independent) and
full replayable publication. Builder sees only public contracts/API and closed
diagnostics. Deterministic support assembly is declared, not a human repair.
"""
import hashlib,json,re,shutil,time,uuid,sys,importlib.metadata
from datetime import date
from pathlib import Path
from lightyear_calibration.contracts import require,read_json,seal,verify,canonical
from lightyear_calibration.journey_order import save,file_hash
from tools.ms94_signer_v5 import JourneySigner
from lightyear_calibration.journey_repair import client_identity,check_client,analyst_prompt,analyst_schema,select_feedback,cost_report
from lightyear_control_tower.decisions import verify_envelope
from lightyear_factory.agents import BUILDER_SCHEMA
from tools.ms94_equipment import frozen as equipment_frozen
from tools.ms94_v6_gate import VERSION
from tools.ms94_tool_policy_v5 import verify_events
from tools.ms94_b04_feedback_route import partition, route, verify_route

CONTROLLER_VERSION='ms94-b05-calendar-direct-delivery-r2-review'
HARNESS='LightyearOperationsTest.java'
PLACEHOLDER='// LIGHTYEAR_BUILDER_JOURNEY\n'
SUPPORT=Path('factory/idempiere/qualification-ms94-v3/public/JourneySupport.java')


def tool_runtime():
    return {'python_version':sys.version,'python_executable_sha256':file_hash(Path(sys.executable)),
            'packages':{n:importlib.metadata.version(n) for n in ('mcp','pydantic','anyio')}}


def public_prompt(root):
    from tools.ms94_b05_admission import APPROVED
    return read_json(root/APPROVED/'builder-prompt.json')

def frozen(root,campaign,live=False):
    from tools.ms94_b05_admission import trial
    return trial(root,campaign,live)

def builder_prompt(initial,previous=None,feedback=None):
    value=json.loads(json.dumps(initial))
    if previous is not None:value.update(previous_candidate=previous,analyst_feedback=feedback)
    return value

def prepare_feedback(observed,suspect,selection=None):
    require(not suspect or not observed, 'Equipment-suspect feedback must be empty')
    if suspect:return {'disposition':'halted-equipment-suspect','diagnostics':[]}
    return route(observed,selection)


def assemble(root,source):
    require(isinstance(source,str) and len(source.encode())<=60000,'Candidate exceeds source budget')
    require(len(source.splitlines())<=650,'Candidate exceeds declared line budget')
    require(not re.search(r'\bclass\s+JourneySupport\b',source),'Candidate cannot replace support')
    from tools.ms94_v3_development import structural
    require(structural(source)['passed'],'Out-of-scope candidate structure')
    support=(root/SUPPORT).read_text(encoding='utf-8')
    support=support.replace('package org.idempiere.test;','',1).replace('public final class JourneySupport','final class JourneySupport',1)
    return source.rstrip()+'\n\n'+support.strip()+'\n'


def candidate(root,campaign,folder,proposal):
    plan=frozen(root,campaign)
    require(proposal['blocked_reason'] is None and len(proposal['edits'])==1,'Builder blocked or exceeded scope')
    edit=proposal['edits'][0]
    require(edit['path']==HARNESS and edit['find']==PLACEHOLDER,'Unexpected replacement edit')
    source=edit['replace'];code=assemble(root,source)
    records=[record for p in sorted((campaign/'calls').glob('*/tool-transcript.json')) for record in read_json(p)]
    require(any(r['invocation']['tool']=='compile' and r['invocation']['arguments'].get('source')==source
                and r['result']['output'].get('status')=='compiled'
                and r['result']['output'].get('candidate_sha256')==hashlib.sha256(source.encode()).hexdigest()
                for r in records),'Final candidate has no successful recorded compiler check')
    build=folder/'build';(build/'workspace').mkdir(parents=True)
    (build/'model-source.java').write_bytes(source.encode('utf-8'))
    (build/'workspace'/HARNESS).write_bytes(code.encode('utf-8'))
    r=JourneySigner(root).sign({'artifact_type':'ms94-builder-candidate','plan_sha256':plan['content_sha256'],
        'prompt_sha256':file_hash(folder/'prompt.json'),'proposal_sha256':file_hash(folder/'proposal.json'),
        'tool_transcript_sha256':file_hash(folder/'tool-transcript.json'),'events_sha256':file_hash(folder/'events.jsonl'),
        'model_source_sha256':file_hash(build/'model-source.java'),'harness_sha256':file_hash(build/'workspace'/HARNESS),
        'support_sha256':plan['support_sha256'],'human_authored_repair_bytes':0,
        'provider_invocations':len(list((campaign/'calls').glob('*/invocation.json')))})
    save(build/'receipt.json',r);return build,r


def audit(root,campaign,attempts):
    plan=frozen(root,campaign);key=(root/'work/ms87/operator/authority.public.pem').read_bytes();previous=None
    from tools.ms94_b05_stops import verify_causes
    verify_causes(root,campaign,key)
    calls=sorted((campaign/'calls').glob('*/receipt.json'));tool_calls=0
    require(len(calls)==len(list((campaign/'calls').glob('*/invocation.json'))),'Incomplete call accounting')
    all_records=[]
    for p in calls:
        c=read_json(p);require(verify_envelope(c,key) and c['plan_sha256']==plan['content_sha256'],'Call signature changed')
        require(c.get('tool_transcript_error') is None,'Incomplete tool transcript')
        for name,field in [('prompt.json','prompt_sha256'),('events.jsonl','events_sha256'),('proposal.json','proposal_sha256'),('tool-transcript.json','tool_transcript_sha256')]:
            if c.get(field) is not None:require(file_hash(p.parent/name)==c[field],'Call artifact changed')
        events=[json.loads(x) for x in (p.parent/'events.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        records=read_json(p.parent/'tool-transcript.json');verify_events(events,c['role'],records)
        all_records.extend(records)
        tool_calls+=len(records)
    previous_hash=None
    for ordinal,record in enumerate(all_records,1):
        i=record['invocation'];v=record['result'];verify(i);verify(v)
        require(i['ordinal']==ordinal and i['previous_sha256']==previous_hash and
                v['invocation_sha256']==i['content_sha256'],'Tool transcript chain changed')
        previous_hash=v['content_sha256']
    compile_calls=[x for x in all_records if x['invocation']['tool']=='compile' and
                   x['result']['output'].get('status')!='tool-rejected']
    require(len(compile_calls)<=plan['max_compilations'],'Compile budget exceeded')
    require(len(calls)<=plan['max_client_invocations'],'Call budget exceeded')
    require(len(list((campaign/'calls').glob('*-builder/build/receipt.json')))==len(attempts),'Candidate has no complete native attempt')
    for i,attempt in enumerate(attempts,1):
        build=root/attempt['builder_directory'];r=read_json(build/'receipt.json');folder=build.parent
        require(verify_envelope(r,key) and verify_envelope(attempt,key),'Candidate/attempt signature changed')
        proposal=read_json(folder/'proposal.json')['edits'][0]['replace']
        require((build/'model-source.java').read_bytes()==proposal.encode('utf-8'),'Human candidate edits detected')
        require((build/'workspace'/HARNESS).read_bytes()==assemble(root,proposal).encode('utf-8'),'Deterministic support assembly changed')
        require(file_hash(build/'workspace'/HARNESS)==r['harness_sha256'],'Native candidate hash differs')
        native=root/attempt['run_directory'];nr=read_json(native/'receipt.json')
        require(verify_envelope(nr,key) and nr['content_sha256']==attempt['receipt_sha256'],'Native receipt changed')
        require(file_hash(native/'inputs/operations.java')==r['harness_sha256'],'Native execution used different candidate')
        require(read_json(native/'gate.json')['content_sha256']==attempt['gate_sha256'],'Gate changed')
        from tools.ms94_b05_evidence import verify_attempt
        verify_attempt(root,native,key)
        from tools.qualification_feedback_v4 import export
        observed_path=campaign/f'analyst-input-{i}.json'
        if observed_path.exists():
            diagnostics=export(native,plan['initial_prompt']['public_trace_contract'],root=root,
                               api=read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
            require(read_json(observed_path)=={'diagnostics':diagnostics},'Observed diagnostic differs from native export')
        expected=json.loads(json.dumps(plan['initial_prompt']))
        if previous is not None:
            feedback=read_json(campaign/f'feedback-{i-1}.json');observed=read_json(campaign/f'analyst-input-{i-1}.json')['diagnostics']
            require(verify_envelope(feedback,key),'Feedback signature changed')
            verify_route(observed,feedback)
            _,structural=partition(observed)
            analyst=[p.parent for p in calls if read_json(p)['role']=='analyst']
            if structural:
                require(any(read_json(p/'proposal.json')==feedback['analyst_proposal'] and
                            read_json(p/'prompt.json')['diagnostics']==structural and
                            read_json(p/'prompt.json')['candidate']==previous for p in analyst),'Feedback lacks analyst provenance')
            expected.update(previous_candidate=previous,analyst_feedback=feedback['diagnostics'])
        require(read_json(folder/'prompt.json')==expected,'Undeclared builder prompt')
        previous=proposal
    return {'verified':True,'tool_calls':tool_calls,'human_authored_repair_bytes':0,'controller_changes':0}


def run(root,campaign,executable,remaining_seconds=None):
    from tools.ms94_b05_transport import invoke
    from tools.ms94_b05_native import execute_native
    from tools.qualification_feedback_v4 import export,equipment_suspect
    from tools.ms94_b05_admission import model_authorization
    model_authorization(root)
    from tools.ms94_b05_supervisor import remaining_work
    from tools.ms94_b05_stops import IMMEDIATE,notify,record_failure,signal_review
    remaining_work(root,campaign)
    plan=frozen(root,campaign,live=True);signer=JourneySigner(root)
    check_client(executable,plan['builder_client'])
    with (campaign/'started.json').open('xb') as f:f.write(canonical({'plan_sha256':plan['content_sha256']}))
    started=time.monotonic();attempts=[];previous=None;feedback=[];status='halted';error=None
    limit=min(plan['max_elapsed_seconds'],remaining_seconds) if remaining_seconds is not None else plan['max_elapsed_seconds']
    def remaining():return min(limit-(time.monotonic()-started),remaining_work(root,campaign))
    try:
        while True:
            frozen(root,campaign);require(remaining()>0,'Trial budget exhausted')
            prompt=builder_prompt(plan['initial_prompt'],previous,feedback)
            folder,proposal=invoke(root,campaign,executable,'builder',prompt,BUILDER_SCHEMA,remaining())
            build,builder=candidate(root,campaign,folder,proposal);previous=proposal['edits'][0]['replace']
            native,nr=execute_native(root,campaign,build,builder,remaining());gate=read_json(native/'gate.json')
            attempt=signer.sign({'attempt':len(attempts)+1,'builder_directory':build.relative_to(root).as_posix(),
                'run_directory':native.relative_to(root).as_posix(),'receipt_sha256':nr['content_sha256'],
                'gate_sha256':gate['content_sha256'],'result_class':gate['status'],'passed':gate['status']=='passed',
                'elapsed_seconds':nr['elapsed_seconds']})
            attempts.append(attempt);save(campaign/'attempts.json',attempts)
            require(nr['cleanup_complete'] and nr['error'] is None and nr['calendar_checks'],'Native evidence/cleanup failure')
            if gate['status']=='passed':status='passed';break
            if gate['status'] in ('judge-error','insufficient-evidence'):status='void-equipment-failure';break
            observed=export(native,prompt['public_trace_contract'],root=root,
                            api=read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
            save(campaign/f'analyst-input-{len(attempts)}.json',{'diagnostics':observed})
            if equipment_suspect(native,prompt['public_trace_contract'],root=root,
                                 api=read_json(root/'factory/idempiere/analyst-repair/api-provenance.json')):
                require(not observed,'Equipment-suspect feedback must be empty')
                status='halted-equipment-suspect';break
            record_failure(root,campaign,native,gate,observed)
            if not observed:status='halted-no-supported-repair';break
            runtime,structural=partition(observed)
            additional_calls=1+bool(structural)
            from tools.ms94_b05_evidence import metrics
            used_compilations=metrics(root,campaign,attempts)['compilations']
            if (len(list((campaign/'calls').glob('*/invocation.json')))+additional_calls>plan['max_client_invocations']
                    or max(len(attempts),used_compilations)>=plan.get('max_compilations',3)):
                status='halted-frozen-budget-exhausted';break
            selection=None
            if structural:
                ap=analyst_prompt(structural,previous,prompt['api_reference'],{'classification':gate['status']})
                _,selection=invoke(root,campaign,executable,'analyst',ap,analyst_schema(structural),remaining())
            routed=prepare_feedback(observed,False,selection);feedback=routed['diagnostics']
            save(campaign/f'feedback-{len(attempts)}.json',signer.sign(routed))
            if not feedback:status='halted-analyst-declined';break
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)};status='halted-controller-failure'
    if status in IMMEDIATE:notify(root,campaign,status)
    elif status=='halted-equipment-suspect':signal_review(root,campaign,'equipment-suspect')
    try:provenance=audit(root,campaign,attempts)
    except Exception as exc:
        provenance={'verified':False,'error_type':type(exc).__name__};status='invalid-provenance'
        notify(root,campaign,status)
    calls=[read_json(p) for p in sorted((campaign/'calls').glob('*/receipt.json'))]
    from tools.ms94_b05_evidence import metrics
    measured=metrics(root,campaign,attempts)
    cost=cost_report(calls,attempts,time.monotonic()-started)
    cost['compilations']=measured['compilations']
    value=signer.sign({'artifact_type':'ms94-b05-trial','plan_sha256':plan['content_sha256'],
        'status':status,'error':error,'attempts':attempts,'provenance':provenance,
        'metrics':measured,'cost':cost,'first_try_pass':status=='passed' and len(attempts)==1,
        'repaired_pass':status=='passed' and len(attempts)>1,'dark_factory_run':status=='passed' and provenance['verified'],
        'platform_qualification':False,'billing_usd':None})
    save(campaign/'receipt.json',value);return value
