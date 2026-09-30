"""Separately versioned MS94 controller v2. Exact approval, no amendment/resume.

Equipment must already have passed Stage A including signed human reviews and
full replayable publication. Builder sees only public contracts/API and closed
diagnostics. Deterministic support assembly is declared, not a human repair.
"""
import hashlib,json,re,shutil,time,uuid,sys,importlib.metadata
from datetime import date
from pathlib import Path
from lightyear_calibration.contracts import require,read_json,seal,verify,canonical
from lightyear_calibration.journey_order import save,file_hash
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_calibration.journey_repair import client_identity,check_client,analyst_prompt,analyst_schema,select_feedback,cost_report
from lightyear_control_tower.decisions import verify_envelope
from lightyear_factory.agents import BUILDER_SCHEMA
from tools.ms94_equipment import frozen as equipment_frozen
from tools.ms94_v4_gate import VERSION
from tools.ms94_tool_policy_v4 import verify_events

CONTROLLER_VERSION='ms94-qualified-controller-v2-equipment04'
HARNESS='LightyearOperationsTest.java'
PLACEHOLDER='// LIGHTYEAR_BUILDER_JOURNEY\n'
SUPPORT=Path('factory/idempiere/qualification-ms94-v3/public/JourneySupport.java')


def tool_runtime():
    return {'python_version':sys.version,'python_executable_sha256':file_hash(Path(sys.executable)),
            'packages':{n:importlib.metadata.version(n) for n in ('mcp','pydantic','anyio')}}


from tools.ms94_stage_b_evidence import stage_a


def public_prompt(root):
    value=read_json(root/'factory/idempiere/repeatability/baseline/builder-input.json')
    value['instruction']=value['instruction'].replace('Do not use tools.',
        'Use only public_contract, public_api, deterministic_support, check_structure and compile. '
        'Read the operations contract and deterministic support. Compile the candidate before proposing it. '
        'The compiler has a frozen budget; compilation success is not business success. '
        'Use JourneySupport directly without defining or copying that class. The controller appends its pinned source deterministically.')
    value['public_shapes']=read_json(root/'factory/idempiere/qualification-ms94-v3/public/operations-shapes.json')
    value['public_trace_contract']=read_json(root/'factory/idempiere/qualification-ms94-v3/public/operations.json')
    value['support_assembly']='Remove the support package and public class modifier; trim only boundary whitespace and append with two newline separators. No candidate logic transformation.'
    return value


def prepare(root,campaign,executable,equipment,maximum=5,compilations=3):
    require(not campaign.exists() and campaign.resolve().is_relative_to(root.resolve()),'Use a new campaign path')
    require(type(maximum) is int and 1<=maximum<=5 and type(compilations) is int and 1<=compilations<=10,'Budget outside declared bound')
    ep,acceptance=stage_a(root,equipment);pins=dict(ep['implementation_sha256'])
    for p in (root/'tools').glob('ms94_*.py'):pins[p.relative_to(root).as_posix()]=file_hash(p)
    for name in ('tools/journey_development_tools.py','tools/journey_builder_mcp.py','tools/qualification_transport_policy.py',
                 'factory/idempiere/repeatability/baseline/builder-input.json','factory/idempiere/analyst-repair/api-provenance.json'):
        pins[name]=file_hash(root/name)
    for p in equipment.rglob('*.json'):pins[p.relative_to(root).as_posix()]=file_hash(p)
    snapshot=read_json(root/'execution-snapshot.json');verify(snapshot)
    pins.update(snapshot['files'])
    pins['execution-snapshot.json']=file_hash(root/'execution-snapshot.json')
    plan=seal({'artifact_type':'ms94-frozen-trial','controller_version':CONTROLLER_VERSION,'judge_version':VERSION,
        'equipment_directory':equipment.relative_to(root).as_posix(),'equipment_plan_sha256':ep['content_sha256'],
        'equipment_acceptance_sha256':acceptance['content_sha256'],'implementation_sha256':pins,
        'builder_client':client_identity(executable),'requested_model':'gpt-6-astra','reasoning_effort':'high',
        'tool_runtime':tool_runtime(),
        'requested_model_is_provider_resolution':False,'max_client_invocations':maximum,'max_compilations':compilations,
        'client_timeout_seconds':1800,'max_elapsed_seconds':7200,'tool_session_id':'ms94-'+uuid.uuid4().hex,
        'assessed_on':date.today().isoformat(),'support_sha256':file_hash(root/SUPPORT),
        'initial_prompt':public_prompt(root),'human_authored_repair_bytes_target':0,'controller_changes_allowed':0,
        'organization_api_migration':'deferred-by-user','billing_usd':None,'cloud_resources':False,
        'source_transfer':{'destination':'Codex/OpenAI through the signed-in account','public_api_and_support':True,
          'candidate_source':True,'closed_tool_outputs_and_structural_diagnostics':True,'private_reference':False,
          'private_business_outputs':False,'database_rows':False,'credentials':False}})
    campaign.mkdir(parents=True);save(campaign/'plan.json',plan)
    save(campaign/'declaration.json',JourneySigner(root).sign({'plan_sha256':plan['content_sha256'],'execution_authorized':False}))
    return plan


def frozen(root,campaign,live=False):
    plan=read_json(campaign/'plan.json');verify(plan);key=(root/'work/ms87/operator/authority.public.pem').read_bytes()
    d=read_json(campaign/'declaration.json')
    require(verify_envelope(d,key) and d['plan_sha256']==plan['content_sha256'],'Trial declaration changed')
    require(plan['controller_version']==CONTROLLER_VERSION,'Unsupported controller')
    if live:
        from tools.ms94_execution_snapshot import guard
        guard(root)
        require(plan['tool_runtime']==tool_runtime(),'Public tool runtime changed')
    _,acceptance=stage_a(root,root/plan['equipment_directory'],live=live)
    require(acceptance['content_sha256']==plan['equipment_acceptance_sha256'],'Equipment acceptance changed')
    for name,sha in plan['implementation_sha256'].items():require(file_hash(root/name)==sha,'Frozen controller/input changed: '+name)
    require(plan['initial_prompt']==public_prompt(root),'Public prompt changed')
    if (campaign/'authorization.json').exists():
        auth=read_json(campaign/'authorization.json')
        require(verify_envelope(auth,key) and auth['plan_sha256']==plan['content_sha256'], 'Trial authorization changed')
        publication=read_json(root/plan['equipment_directory']/'published-assets.json')
        require(verify_envelope(publication,key) and publication['content_sha256']==auth['stage_a_publication_sha256'],
                'Authorized Stage A publication changed')
    return plan


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
        expected=json.loads(json.dumps(plan['initial_prompt']))
        if previous is not None:
            feedback=read_json(campaign/f'feedback-{i-1}.json');observed=read_json(campaign/f'analyst-input-{i-1}.json')['diagnostics']
            require(verify_envelope(feedback,key) and feedback['diagnostics']==select_feedback(observed,feedback['analyst_proposal'],True),'Feedback changed')
            analyst=[p.parent for p in calls if read_json(p)['role']=='analyst']
            require(any(read_json(p/'proposal.json')==feedback['analyst_proposal'] and
                        read_json(p/'prompt.json')['diagnostics']==observed and
                        read_json(p/'prompt.json')['candidate']==previous for p in analyst),'Feedback lacks analyst provenance')
            expected.update(previous_candidate=previous,analyst_feedback=feedback['diagnostics'])
        require(read_json(folder/'prompt.json')==expected,'Undeclared builder prompt')
        previous=proposal
    return {'verified':True,'tool_calls':tool_calls,'human_authored_repair_bytes':0,'controller_changes':0}


def run(root,campaign,executable,remaining_seconds=None):
    from tools.ms94_transport_v4 import invoke
    from tools.ms94_native_b_v4 import execute_native
    from tools.qualification_feedback import export
    plan=frozen(root,campaign,live=True);signer=JourneySigner(root);auth=read_json(campaign/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['plan_sha256']==plan['content_sha256'],'Exact trial approval missing')
    check_client(executable,plan['builder_client'])
    with (campaign/'started.json').open('xb') as f:f.write(canonical({'plan_sha256':plan['content_sha256']}))
    started=time.monotonic();attempts=[];previous=None;feedback=[];status='halted';error=None
    limit=min(plan['max_elapsed_seconds'],remaining_seconds) if remaining_seconds is not None else plan['max_elapsed_seconds']
    def remaining():return limit-(time.monotonic()-started)
    try:
        while True:
            frozen(root,campaign);require(remaining()>0,'Trial budget exhausted')
            prompt=json.loads(json.dumps(plan['initial_prompt']))
            if previous is not None:prompt.update(previous_candidate=previous,analyst_feedback=feedback)
            folder,proposal=invoke(root,campaign,executable,'builder',prompt,BUILDER_SCHEMA,remaining())
            build,builder=candidate(root,campaign,folder,proposal);previous=proposal['edits'][0]['replace']
            native,nr=execute_native(root,campaign,build,builder,remaining());gate=read_json(native/'gate.json')
            attempt=signer.sign({'attempt':len(attempts)+1,'builder_directory':build.relative_to(root).as_posix(),
                'run_directory':native.relative_to(root).as_posix(),'receipt_sha256':nr['content_sha256'],
                'gate_sha256':gate['content_sha256'],'result_class':gate['status'],'passed':gate['status']=='passed',
                'elapsed_seconds':nr['elapsed_seconds']})
            attempts.append(attempt);save(campaign/'attempts.json',attempts)
            require(nr['cleanup_complete'],'Native cleanup incomplete')
            if gate['status']=='passed':status='passed';break
            if gate['status'] in ('judge-error','insufficient-evidence'):status='void-equipment-failure';break
            observed=export(native,prompt['public_trace_contract'],root=root,
                            api=read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
            save(campaign/f'analyst-input-{len(attempts)}.json',{'diagnostics':observed})
            if not observed:status='halted-no-supported-repair';break
            if len(list((campaign/'calls').glob('*/invocation.json')))+2>plan['max_client_invocations']:
                status='halted-frozen-budget-exhausted';break
            ap=analyst_prompt(observed,previous,prompt['api_reference'],{'classification':gate['status']})
            _,selection=invoke(root,campaign,executable,'analyst',ap,analyst_schema(observed),remaining())
            feedback=select_feedback(observed,selection,True)
            save(campaign/f'feedback-{len(attempts)}.json',signer.sign({'diagnostics':feedback,'analyst_proposal':selection}))
            if not feedback:status='halted-analyst-declined';break
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)};status='halted-controller-failure'
    try:provenance=audit(root,campaign,attempts)
    except Exception as exc:provenance={'verified':False,'error_type':type(exc).__name__};status='invalid-provenance'
    calls=[read_json(p) for p in sorted((campaign/'calls').glob('*/receipt.json'))]
    value=signer.sign({'artifact_type':'ms94-controller-v2-trial','plan_sha256':plan['content_sha256'],
        'status':status,'error':error,'attempts':attempts,'provenance':provenance,
        'cost':cost_report(calls,attempts,time.monotonic()-started),'first_try_pass':status=='passed' and len(attempts)==1,
        'repaired_pass':status=='passed' and len(attempts)>1,'dark_factory_run':status=='passed' and provenance['verified'],
        'platform_qualification':False,'billing_usd':None})
    save(campaign/'receipt.json',value);return value
