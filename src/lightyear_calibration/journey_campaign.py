"""MS89: bounded agent repairs, unchanged MS88 native judge, complete accounting."""
import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

from .contracts import canonical, read_json, require, seal, verify
from .journey_order import RUNS, archived, file_hash, save, make_plan, UNCLAIMED
from .journey_runtime import JourneySigner, LocalRunner, JourneyAbort, inventory, read_local, run_folder
from .journey_repair import (client_identity, check_client, invoke, diagnostics, analyst_schema,
                            select_feedback, cost_report, analyst_prompt)
from lightyear_control_tower.decisions import verify_envelope
from lightyear_factory.agents import BUILDER_SCHEMA
from lightyear_factory.contracts import WorkOrder
from lightyear_factory.patches import PatchBroker
from lightyear_factory.workspace import IsolatedWorkspace
from lightyear_workflow.campaign_journals import signed_append, check
from lightyear_workflow.run_store import RunStore, utcnow
from lightyear_workflow.run_index import RunIndex
from lightyear_workflow.convergence import INDEX_RELATIVE

SPEC = Path('factory/idempiere/analyst-repair/campaign.json')
PLACEHOLDER = '// LIGHTYEAR_BUILDER_JOURNEY\n'
HARNESS = 'LightyearPartialInvoiceTest.java'


def check_hashes(root, hashes):
    for name, expected in hashes.items():
        require(file_hash(root/name) == expected, 'Pinned implementation/input changed: '+name)


def prepare(root, campaign, executable):
    require(not campaign.exists(), 'Use a new campaign directory')
    spec = read_json(root/SPEC)
    check_client(executable, spec['builder_client'])
    check_hashes(root,spec['judge_sha256'])
    check_hashes(root,spec['public_input_sha256'])
    base = make_plan(root,read_local(root),inventory(root))
    key = JourneySigner(root).public
    # Reuse admitted *data and native environment*, not an obsolete controller.
    replays=[]
    for path in (root/RUNS).glob('journey-*/receipt.json'):
        receipt=read_json(path)
        if not (verify_envelope(receipt,key) and receipt.get('unattended_run') and receipt.get('known_findings_reproduced')): continue
        old=read_json(path.parent/'plan.json');verify(old)
        if all(old.get(k)==base[k] for k in ('declaration_sha256','references','inputs_sha256','local')):
            replays.append({'run_id':receipt['run_id'],'receipt_sha256':receipt['content_sha256'],'plan_sha256':old['content_sha256']})
    require(len(replays)>=2,'Two admitted replays of this data/environment are required')
    implementation={**base['implementation_sha256'],**spec['judge_sha256']}
    implementation.update({p.relative_to(root).as_posix():file_hash(p) for p in (root/'src/lightyear_calibration').glob('journey_*.py')})
    plan=seal({'artifact_type':'lightyear-analyst-repair-plan','spec_sha256':file_hash(root/SPEC),
        'base_plan':base,'judge_sha256':spec['judge_sha256'],'public_input_sha256':spec['public_input_sha256'],
        'implementation_sha256':implementation,'builder_client':spec['builder_client'],
        'max_client_invocations':spec['max_client_invocations'],'client_timeout_seconds':spec['client_timeout_seconds'],
        'max_elapsed_seconds':spec['max_elapsed_seconds'],'prerequisite_replays':replays,
        'human_authored_repair_bytes_target':0,'expected_business_values_exposed':False})
    campaign.mkdir(parents=True)
    save(campaign/'plan.json',plan)
    save(campaign/'authorization.json',JourneySigner(root).sign({'artifact_type':'lightyear-analyst-repair-authorization',
        'plan_sha256':plan['content_sha256'],'actor':'Howard Weale','at':utcnow(),
        'authority':'User requested a fresh partial-invoicing journey, analyst-led permitted repairs, unchanged MS88 judge and zero human-authored repair bytes. Five total agent client calls; increases require a separate approval.'}))
    return plan


def public_prompt(root):
    """This file is written from public inputs, never projected from judge results."""
    return read_json(root/'factory/idempiere/analyst-repair/builder-input.json')


def apply_candidate(root, campaign, folder, proposal):
    require(proposal['blocked_reason'] is None, 'Builder declined')
    require(len(proposal['edits'])==1 and proposal['edits'][0]['path']==HARNESS
        and proposal['edits'][0]['find']==PLACEHOLDER,'Builder must replace exactly the declared placeholder')
    plan=read_json(campaign/'plan.json')
    workspace=folder/'candidate';workspace.mkdir()
    (workspace/HARNESS).write_text(PLACEHOLDER,encoding='utf-8',newline='\n')
    order=WorkOrder.from_dict(read_json(root/'factory/idempiere/partial-invoicing/work-order.json'))
    patch=PatchBroker().apply(order,IsolatedWorkspace(workspace,workspace,order.allowed_paths),proposal['edits'])
    code=(workspace/HARNESS).read_text(encoding='utf-8')
    require('class LightyearPartialInvoiceTest extends AbstractTestCase' in code,'Unexpected test class')
    require(all(term not in code for term in ('ProcessBuilder','Runtime.getRuntime','java.net.','System.getenv','/output/','/verifier/','ALTER USER','DROP TABLE')),'Generated harness requests out-of-scope capabilities')
    # Retain compatibility with the original offline native publication format.
    build=root/'work/ms88'/('build-ms89-'+uuid.uuid4().hex)
    (build/'workspace').mkdir(parents=True)
    for name in ('prompt.json','proposal.json','events.jsonl','invocation.json'):shutil.copyfile(folder/name,build/name)
    shutil.copyfile(workspace/HARNESS,build/'workspace'/HARNESS)
    receipt=JourneySigner(root).sign({'artifact_type':'lightyear-journey-builder','provider':'authenticated-codex-cli',
        'declaration_sha256':file_hash(root/'factory/idempiere/partial-invoicing/work-order.json'),
        'provider_invocations':len(list((campaign/'calls').glob('*/invocation.json'))),
        'builder_client':plan['builder_client'],'campaign_plan_sha256':plan['content_sha256'],
        'judge_sha256':plan['judge_sha256'],'human_authored_repair_bytes':0,'patch':patch,
        'agent_generated':True,'native_execution_verified':False,'gate_output_exposed':False,
        'prompt_sha256':file_hash(build/'prompt.json'),'proposal_sha256':file_hash(build/'proposal.json'),
        'events_sha256':file_hash(build/'events.jsonl'),'harness_sha256':file_hash(build/'workspace'/HARNESS)})
    save(build/'receipt.json',receipt)
    return build,receipt


def native_plan(root, campaign, build, builder):
    campaign_plan=read_json(campaign/'plan.json');verify(campaign_plan)
    check_hashes(root,campaign_plan['implementation_sha256'])
    require(file_hash(root/SPEC)==campaign_plan['spec_sha256'],'Campaign budget or scope changed')
    require(verify_envelope(builder,JourneySigner(root).public),'Builder receipt signature differs')
    for name,field in [('prompt.json','prompt_sha256'),('proposal.json','proposal_sha256'),('events.jsonl','events_sha256'),('workspace/'+HARNESS,'harness_sha256')]:
        require(file_hash(build/name)==builder[field],'Builder artifact changed after generation')
    base=campaign_plan['base_plan']
    require(read_local(root)==base['local'],'Native environment configuration changed')
    inv=inventory(root)
    require(inv['free_bytes']>=60*1024**3 and inv['memory_bytes']>=12*1024**3,'Insufficient native resources')
    declaration=read_json(root/'factory/idempiere/partial-invoicing/work-order.json')
    value={k:v for k,v in base.items() if k!='content_sha256'}
    value.update(mode='extend',cases=['partial-invoicing'],extension_declaration=declaration,
        extension_declaration_sha256=file_hash(root/'factory/idempiere/partial-invoicing/work-order.json'),
        builder_receipt_sha256=builder['content_sha256'],builder_directory=build.relative_to(root).as_posix(),
        harness_sha256=builder['harness_sha256'],model_calls=builder['provider_invocations'],
        prerequisite_replays=campaign_plan['prerequisite_replays'],implementation_sha256=campaign_plan['implementation_sha256'],
        judge_sha256=campaign_plan['judge_sha256'],builder_client=campaign_plan['builder_client'],
        campaign_directory=campaign.relative_to(root).as_posix(),campaign_plan_sha256=campaign_plan['content_sha256'],
        human_authored_repair_bytes=0)
    return seal(value)


def execute_native(root, campaign, build, builder, remaining_seconds):
    from .partial_invoicing import bounded_gate
    plan=native_plan(root,campaign,build,builder)
    for path in (root/RUNS).glob('journey-*'):
        require((path/'receipt.json').exists() and read_json(path/'cleanup.json')['complete'],'An existing native run needs recovery')
    run=run_folder(root,'journey-'+uuid.uuid4().hex);run.mkdir(parents=True)
    signer=JourneySigner(root);save(run/'plan.json',plan);(run/'authority.public.pem').write_bytes(signer.public)
    inputs=archived(root);inputs['partial-invoicing.java']=(build/'workspace'/HARNESS).read_bytes()
    for h in plan['declaration']['application']['harnesses']:inputs[h['id']+'.java']=(root/h['file']).read_bytes()
    (run/'inputs').mkdir()
    for name,data in inputs.items():(run/'inputs'/name).write_bytes(data)
    auth=signer.sign({'record_type':'native-journey-authorization','run_id':run.name,'plan':{'plan_sha256':plan['content_sha256']},
        'campaign_authorization_sha256':read_json(campaign/'authorization.json')['content_sha256'],
        'operator_authorization':'Fresh generation and permitted analyst repairs under the unchanged MS88 judge; no semantic claim promotion.'})
    save(run/'authorization.json',auth)
    kwargs={'cwd':root,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,
        'env':{**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}}
    if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
    else:kwargs['start_new_session']=True
    subprocess.Popen([sys.executable,'-m','lightyear_calibration.journey_runtime','watch',str(root),str(run),str(os.getpid())],**kwargs)
    store=RunStore(run/'journal');gate=None;error=None;started=time.monotonic()
    def emit(kind,payload):return signed_append(store,signer,auth,kind,{k:v for k,v in payload.items() if k not in ('signature','content_sha256')},'journey')
    runner=LocalRunner(root,run,plan,emit);runner.deadline=min(runner.deadline,time.monotonic()+remaining_seconds)
    def interrupted(*_):raise JourneyAbort('cancelled')
    handlers={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM)}
    emit('started',{'mode':'extend','campaign_plan_sha256':plan['campaign_plan_sha256'],
        'judge_sha256':plan['judge_sha256'],'builder_client':plan['builder_client'],'human_authored_repair_bytes':0})
    print(json.dumps({'run_id':run.name,'stage':'native-started'}),flush=True)
    try:
        folder=runner.prepare('partial-invoicing',1)
        save(run/'selected-attempts.json',{'partial-invoicing':1})
        for lane in ('oracle','postgresql'):
            runner.checkpoint('execute-lane:partial-invoicing:'+lane)
            value=runner.worker('execute',{'lane':lane,'output':runner.inside(folder/'execution'/lane),
                'harness':'/output/inputs/partial-invoicing.java','harness_sha256':plan['harness_sha256'],
                'test':'LightyearPartialInvoiceTest','source_commit':plan['declaration']['application']['source_commit'],'timeout_seconds':1200},timeout=1250)
            emit('native-execution',{'case':'partial-invoicing','lane':lane,'exit_code':value['exit_code'],'execution_sha256':value['content_sha256']})
            if value['exit_code']:raise JourneyAbort('timeout' if value['exit_code']==124 else 'harness-exception')
            runner.worker('capture',{'lane':lane,'output':runner.inside(folder/'after'/lane)},timeout=1800)
        cleaned=runner.cleanup();emit('pair-cleanup',cleaned);require(cleaned['complete'],'Cleanup failure')
        runner.checkpoint('verify')
        gate=bounded_gate(runner);emit('gate',{'command':'verify-partial-invoicing','passed':gate['passed'],'receipt_sha256':gate['content_sha256']})
        require(gate['passed'],'Business or equivalence gate failed')
        emit('result',{'case':'partial-invoicing','boundary':{'model_calls':plan['model_calls']}})
    except Exception as exc:
        error={'classification':exc.code if isinstance(exc,JourneyAbort) else 'gate-failed','exception_type':type(exc).__name__}
        emit('exception',error)
    finally:
        cleaned=runner.cleanup(retain=error is not None)
        cleanup=signer.sign({'artifact_type':'lightyear-journey-cleanup','run_id':run.name,'plan_sha256':plan['content_sha256'],**cleaned})
        save(run/'cleanup.json',cleanup);emit('cleanup',cleanup)
        if not cleaned['complete']:error={'classification':'cleanup-failure'}
        passed=bool(gate and gate['passed'] and error is None)
        receipt=signer.sign({'artifact_type':'lightyear-native-journey-run','run_id':run.name,'mode':'extend',
            'plan_sha256':plan['content_sha256'],'declaration_sha256':plan['extension_declaration_sha256'],
            'status':'passed-bounded-partial-invoicing-equivalence' if passed else 'failed','reason':'native-judge-completed',
            'builder_receipt_sha256':builder['content_sha256'],'agent_generated':True,'model_calls':plan['model_calls'],
            'known_findings_reproduced':False,'bounded_operations_equivalence':False,'bounded_partial_invoicing_equivalence':passed,
            'executed_cases':['partial-invoicing'],'inherited_cases':[],'human_interventions_outside_designed_stops':sum(e['type']=='intervention' for e in store.events()),
            'unattended_run':False,'unattended_extension':passed,'human_authored_repair_bytes':0,
            'judge_sha256':plan['judge_sha256'],'builder_client':plan['builder_client'],
            'campaign_directory':plan['campaign_directory'],'cleanup_sha256':cleanup['content_sha256'],
            'elapsed_seconds':round(time.monotonic()-started,3),'requests':[],'error':error,'cloud_resources_started':False,**UNCLAIMED})
        emit('halted',receipt);save(run/'receipt.json',receipt)
        try:events=check(store.events(),auth,signer.public,'journey')
        finally:store.close()
        archive=run/(run.name+'.json.gz');archive.write_bytes(gzip.compress(canonical({'events':events}),mtime=0))
        RunIndex(root/INDEX_RELATIVE).record(run.name,'idempiere','ms89-analyst-repair',events,archive);save(run/'journal.json',events)
        for sig,handler in handlers.items():signal.signal(sig,handler)
    return run,receipt


def propose_resume(root,campaign,executable,maximum,analyst_only=False):
    """A reviewable proposal grants no authority and launches no client process."""
    old=read_json(campaign/'plan.json');verify(old)
    result=read_json(campaign/'receipt.json');signer=JourneySigner(root)
    require(verify_envelope(result,signer.public) and result['plan_sha256']==old['content_sha256'],'Stopped campaign receipt differs')
    require(result['status'] in ('halted-nonrepairable','budget-increase-required','repair-feedback-ready'),'Campaign is not at a resumable stop')
    consumed=len(list((campaign/'calls').glob('*/invocation.json')))
    if analyst_only:
        maximum=old['max_client_invocations']
        require(consumed<maximum,'No approved call remains for an analyst recheck')
    else:
        require(type(maximum) is int and old['max_client_invocations']<maximum<=20,'Invalid requested client limit')
    check_client(executable,old['builder_client']);check_hashes(root,old['judge_sha256']);check_hashes(root,old['public_input_sha256'])
    implementation=dict(old['implementation_sha256'])
    # Only the new controller and structural diagnostic filter may differ.
    changed=[]
    allowed={'src/lightyear_calibration/journey_campaign.py','src/lightyear_calibration/journey_repair.py'}
    for name,expected in implementation.items():
        current=file_hash(root/name)
        if current!=expected:
            require(name in allowed,'Resume changed a judge or an unrelated implementation')
            changed.append({'path':name,'before_sha256':expected,'after_sha256':current});implementation[name]=current
    plan=seal({**{k:v for k,v in old.items() if k!='content_sha256'},'max_client_invocations':maximum,
        'implementation_sha256':implementation,'prior_plan_sha256':old['content_sha256'],
        'prior_receipt_sha256':result['content_sha256'],'controller_revision':changed})
    last=result['attempts'][-1];run=root/RUNS/last['run_id'];build=root/last['builder_directory']
    observed=diagnostics(run,(build/'workspace'/HARNESS).read_text(encoding='utf-8'),read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
    proposal=seal({'artifact_type':'lightyear-journey-budget-resume-proposal','plan':plan,
        'consumed_calls':consumed,'analyst_only':analyst_only,
        'resume_from_run':run.name,'permitted_diagnostics':observed,
        'initial_builder_prompt_unchanged':True,'judge_unchanged':True,
        'note':'Controller changes and source-derived structural diagnostics are disclosed. No human candidate repair or business output is supplied. An analyst-only recheck consumes at most one remaining approved call and cannot launch a builder or native execution. The original stopped receipt remains retained.'})
    save(campaign/'resume-proposal.json',proposal);return proposal


def accept_resume(root,campaign,executable,proposal_sha256,analyst_only=False):
    proposal=read_json(campaign/'resume-proposal.json');verify(proposal)
    require(proposal['content_sha256']==proposal_sha256,'Resume proposal changed')
    require(proposal.get('analyst_only',False)==analyst_only,'Resume execution mode differs')
    plan=proposal['plan'];verify(plan)
    require(read_json(campaign/'plan.json')['content_sha256']==plan['prior_plan_sha256'],'Resume base plan changed')
    require(read_json(campaign/'receipt.json')['content_sha256']==plan['prior_receipt_sha256'],'Resume base receipt changed')
    check_client(executable,plan['builder_client']);check_hashes(root,plan['implementation_sha256'])
    for name,key in [('plan.json','prior_plan_sha256'),('receipt.json','prior_receipt_sha256')]:
        archive=campaign/'history'/(plan[key]+'.json');archive.parent.mkdir(exist_ok=True);shutil.copyfile(campaign/name,archive)
    old_auth=read_json(campaign/'authorization.json')
    shutil.copyfile(campaign/'authorization.json',campaign/'history'/(old_auth['content_sha256']+'.json'))
    old_receipt=read_json(campaign/'receipt.json')
    require(len(list((campaign/'calls').glob('*/invocation.json')))==proposal['consumed_calls'],'Client count changed after proposal')
    if analyst_only:
        require(plan['max_client_invocations']==read_json(campaign/'plan.json')['max_client_invocations'],
                'Analyst recheck cannot increase the approved budget')
    # Preserve superseded diagnostics as well as the original stopped receipt.
    for prior in [*campaign.glob('analyst-input-*.json'),*campaign.glob('feedback-*.json')]:
        archive=campaign/'history'/(old_receipt['content_sha256']+'-'+prior.name)
        shutil.copyfile(prior,archive)
    # Moving a completed receipt into immutable history reopens only this campaign.
    (campaign/'receipt.json').unlink()
    save(campaign/'plan.json',plan)
    save(campaign/'authorization.json',JourneySigner(root).sign({'artifact_type':'lightyear-analyst-repair-authorization',
        'plan_sha256':plan['content_sha256'],'actor':'Howard Weale','at':utcnow(),
        'approved_resume_proposal_sha256':proposal_sha256,'previous_authorization_scope':'unchanged public inputs, judge, source-transfer destination and permitted diagnostic categories',
        'authority':('User requested diagnosis and repair of the analyst rejection. One analyst-only recheck uses the remaining call in the existing approved limit; no builder or native run is authorized by this amendment.' if analyst_only else 'User explicitly approved this additional client budget and the concrete diagnostic resume proposal.')}))
    return run_campaign(root,campaign,executable,resume_attempts=old_receipt['attempts'],analyst_only=analyst_only)


def run_campaign(root,campaign,executable,resume_attempts=None,analyst_only=False):
    plan=read_json(campaign/'plan.json');verify(plan);signer=JourneySigner(root)
    require(not (campaign/'receipt.json').exists() and (resume_attempts is not None or not (campaign/'calls').exists()),'Campaign already started')
    auth=read_json(campaign/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['plan_sha256']==plan['content_sha256'],'Campaign authorization differs')
    started=time.monotonic();attempts=list(resume_attempts or []);feedback=[];previous=None;status='failed';error=None
    previous_elapsed=0
    if resume_attempts:
        previous_elapsed=read_json(campaign/'history'/(plan['prior_receipt_sha256']+'.json'))['cost']['total_elapsed_seconds']
    try:
        if resume_attempts:
            last=attempts[-1];run=root/RUNS/last['run_id'];build=root/last['builder_directory']
            previous=(build/'workspace'/HARNESS).read_text(encoding='utf-8')
            observations=diagnostics(run,previous,read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
            require(observations,'No permitted structural diagnosis exists')
            save(campaign/f'analyst-input-{len(attempts)}.json',{'run_id':run.name,'diagnostics':observations})
            prompt=public_prompt(root)
            _,proposal=invoke(root,campaign,executable,'analyst',analyst_prompt(observations,previous,
                prompt['api_reference'],read_json(run/'receipt.json')['error']),analyst_schema(observations))
            feedback=select_feedback(observations,proposal,require_decisions=True)
            save(campaign/f'feedback-{len(attempts)}.json',signer.sign({'diagnostics':feedback,
                'source_run':run.name,'human_authored_repair_bytes':0,'judge_sha256':plan['judge_sha256']}))
            if analyst_only:status='repair-feedback-ready' if feedback else 'halted-nonrepairable'
            else:require(feedback,'Analyst declined the permitted diagnostics')
        require(not analyst_only or resume_attempts,'Analyst recheck needs a stopped native attempt')
        while not analyst_only:
            require(previous_elapsed+time.monotonic()-started<plan['max_elapsed_seconds'],'Campaign elapsed budget exhausted')
            check_hashes(root,plan['implementation_sha256']);check_hashes(root,plan['public_input_sha256'])
            require(file_hash(root/SPEC)==plan['spec_sha256'],'Campaign budget or scope changed')
            prompt=public_prompt(root)
            if previous is not None:prompt.update(previous_candidate=previous,analyst_feedback=feedback)
            folder,proposal=invoke(root,campaign,executable,'builder',prompt,BUILDER_SCHEMA)
            build,builder=apply_candidate(root,campaign,folder,proposal)
            previous=(build/'workspace'/HARNESS).read_text(encoding='utf-8')
            run,receipt=execute_native(root,campaign,build,builder,plan['max_elapsed_seconds']-previous_elapsed-(time.monotonic()-started))
            attempt=signer.sign({'attempt':len(attempts)+1,'run_id':run.name,'receipt_sha256':receipt['content_sha256'],
                'plan_sha256':receipt['plan_sha256'],'judge_sha256':plan['judge_sha256'],
                'harness_sha256':builder['harness_sha256'],'builder_directory':build.relative_to(root).as_posix(),
                'elapsed_seconds':receipt['elapsed_seconds'],'passed':receipt['bounded_partial_invoicing_equivalence'],
                'human_authored_repair_bytes':0,'builder_prompt_sha256':builder['prompt_sha256']})
            attempts.append(attempt);save(campaign/'attempts.json',attempts)
            if attempt['passed']:status='verified';break
            if not read_json(run/'cleanup.json')['complete']:raise ValueError('Native cleanup incomplete')
            observations=diagnostics(run,previous,read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
            save(campaign/f'analyst-input-{len(attempts)}.json',{'run_id':run.name,'diagnostics':observations})
            if not observations:status='halted-nonrepairable';break
            calls=len(list((campaign/'calls').glob('*/invocation.json')))
            if calls+2>plan['max_client_invocations']:status='budget-increase-required';break
            _,proposal=invoke(root,campaign,executable,'analyst',analyst_prompt(observations,previous,
                prompt['api_reference'],receipt['error']),analyst_schema(observations))
            feedback=select_feedback(observations,proposal,require_decisions=True)
            save(campaign/f'feedback-{len(attempts)}.json',signer.sign({'diagnostics':feedback,
                'source_run':run.name,'human_authored_repair_bytes':0,'judge_sha256':plan['judge_sha256']}))
            if not feedback:status='halted-nonrepairable';break
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        if 'budget exhausted' in str(exc):status='budget-increase-required'
    finally:
        calls=[read_json(p) for p in sorted((campaign/'calls').glob('*/receipt.json'))]
        cost=cost_report(calls,attempts,previous_elapsed+time.monotonic()-started)
        cost['elapsed_scope']='Sum of campaign execution segments, including failures; excludes the gap at a stopped approval boundary.'
        try:
            provenance=audit_repair_provenance(root,campaign,attempts)
        except (ValueError,KeyError,OSError) as exc:
            provenance={'verified':False,'human_authored_repair_bytes':None,'reason':str(exc)}
            status='invalid-provenance'
        result=signer.sign({'artifact_type':'lightyear-analyst-repair-campaign','status':status,'error':error,
            'plan_sha256':plan['content_sha256'],'attempts':attempts,'cost':cost,
            'judge_sha256':plan['judge_sha256'],'builder_client':plan['builder_client'],
            'human_authored_repair_bytes':provenance['human_authored_repair_bytes'],'repair_provenance':provenance,
            'human_authored_repair_bytes_scope':'Source patches and repair messages after the pinned initial prompt; setup/specification work is excluded.',
            'expected_business_values_exposed':False,'independently_attested':False})
        save(campaign/'receipt.json',result)
    return result


def audit_repair_provenance(root,campaign,attempts):
    """Zero is established by exact model-artifact and derived-message identity."""
    key=JourneySigner(root).public;previous=None;count=0
    for number,attempt in enumerate(attempts,1):
        require(verify_envelope(attempt,key),'Attempt signature differs')
        build=root/attempt['builder_directory'];receipt=read_json(build/'receipt.json')
        require(verify_envelope(receipt,key),'Builder signature differs')
        for name,field in [('prompt.json','prompt_sha256'),('proposal.json','proposal_sha256'),('events.jsonl','events_sha256'),('workspace/'+HARNESS,'harness_sha256')]:
            require(file_hash(build/name)==receipt[field],'Builder artifact changed')
        proposal=read_json(build/'proposal.json');code=(build/'workspace'/HARNESS).read_bytes()
        require(len(proposal['edits'])==1 and code==proposal['edits'][0]['replace'].encode('utf-8'),'Candidate contains bytes outside model proposal')
        prompt=public_prompt(root)
        if previous is not None:
            feedback=read_json(campaign/f'feedback-{number-1}.json')
            require(verify_envelope(feedback,key),'Feedback signature differs')
            observations=read_json(campaign/f'analyst-input-{number-1}.json')['diagnostics']
            selected=select_feedback(observations,{'diagnostic_ids':[d['id'] for d in feedback['diagnostics']]})
            require(selected==feedback['diagnostics'],'Feedback contains non-diagnostic bytes')
            prompt.update(previous_candidate=previous,analyst_feedback=selected)
            count+=len(canonical(selected))
        require(read_json(build/'prompt.json')==prompt,'Builder prompt contains untracked repair guidance')
        previous=code.decode('utf-8')
    return {'verified':True,'human_authored_repair_bytes':0,'machine_forwarded_diagnostic_bytes':count,
        'verified_candidates':len(attempts),'method':'Every candidate equals its signed model proposal; every repair prompt equals the initial prompt plus the prior candidate and selected allowlisted diagnostics.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare','run','propose-resume','resume','propose-recheck','recheck'])
    parser.add_argument('--root',type=Path,default=Path('.'));parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--max-client-invocations',type=int)
    parser.add_argument('--proposal-sha256');args=parser.parse_args()
    common=(args.root.resolve(),args.campaign.resolve(),args.executable.resolve())
    if args.command in ('propose-resume','propose-recheck'):result=propose_resume(*common,args.max_client_invocations,analyst_only=args.command=='propose-recheck')
    elif args.command in ('resume','recheck'):result=accept_resume(*common,args.proposal_sha256,analyst_only=args.command=='recheck')
    else:result=(prepare if args.command=='prepare' else run_campaign)(*common)
    print(json.dumps(result,indent=2))
    return 0 if result.get('status','verified') in ('verified','repair-feedback-ready') else 3


if __name__=='__main__':raise SystemExit(main())
