"""MS92 trial: declare once, authorize exact hash, run once. There is no resume/amend API."""
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import time

from .contracts import canonical, read_json, require, seal, verify
from .journey_order import file_hash, save, make_plan
from .journey_runtime import JourneySigner, inventory, read_local
from .journey_repair import client_identity, check_client, analyst_prompt, analyst_schema, select_feedback, cost_report
from .declared_rules import validate_register
from .measured_judge import VERSION
from .measured_native import REGISTER, INVENTORY, HARNESS, execute_native
from .measured_diagnostics import diagnostics
from .measured_transport import invoke
from lightyear_control_tower.decisions import verify_envelope
from lightyear_factory.agents import BUILDER_SCHEMA
from lightyear_factory.contracts import WorkOrder
from lightyear_factory.patches import PatchBroker
from lightyear_factory.workspace import IsolatedWorkspace

AREA = Path('factory/idempiere/repeatability')
PLACEHOLDER = '// LIGHTYEAR_BUILDER_JOURNEY\n'


def frozen(root, campaign):
    plan = read_json(campaign/'plan.json'); verify(plan)
    declaration = read_json(campaign/'declaration.json')
    key = (root/'work/ms87/operator/authority.public.pem').read_bytes()
    require(verify_envelope(declaration,key) and declaration['plan_sha256'] == plan['content_sha256'],
            'Frozen declaration changed; a new campaign is required')
    for name, expected in plan['implementation_sha256'].items():
        require(file_hash(root/name) == expected, 'Frozen implementation/input changed: '+name)
    require(plan['judge_version'] == VERSION, 'Unsupported frozen judge version')
    validate_register(read_json(root/REGISTER),read_json(root/INVENTORY),date.today())
    return plan


def prepare(root, campaign, executable, maximum=5, variant="baseline"):
    require(variant in ('baseline','without-decimal','without-boolean','procure-to-pay'), 'Unknown experiment variant')
    require(not campaign.exists() and campaign.resolve().is_relative_to(root.resolve()), 'Use a new workspace campaign')
    require(type(maximum) is int and 1 <= maximum <= 5, 'Invalid proposed call budget')
    base = make_plan(root,read_local(root),inventory(root))
    register = read_json(root/REGISTER)
    validate_register(register,read_json(root/INVENTORY),date.today())
    require(verify_envelope(register['timestamp_decision'],JourneySigner(root).public), 'Untrusted timestamp contract')
    implementation = dict(base['implementation_sha256'])
    for directory in ('src/lightyear_calibration','src/lightyear_factory','src/lightyear_execution','src/lightyear_workflow','src/lightyear_control_tower'):
        implementation.update({p.relative_to(root).as_posix():file_hash(p) for p in (root/directory).rglob('*.py')})
    inputs = [*sorted((root/AREA).rglob('*.json')),root/INVENTORY,
              root/'factory/idempiere/analyst-repair/api-provenance.json',
              root/'tools/publish_declared_evidence.py',root/'tools/publish_frozen_campaign.py',
              root/'tools/publish_measured_campaign.py',root/'tools/qualify_transaction_observer.py',
              root/'tools/publish_observer_qualification.py',
              root/'tools/publish_native_journeys.py',root/'tools/evaluate_journey_judge_v2.py']
    implementation.update({p.relative_to(root).as_posix():file_hash(p) for p in inputs})
    plan = seal({'artifact_type':'lightyear-frozen-factory-plan','judge_version':VERSION,
        'base_plan':base,'implementation_sha256':implementation,'variant':variant,
        'scenario':'procure-to-pay' if variant=='procure-to-pay' else 'operations',
        'variant_input_dir':(AREA/variant).as_posix(),
        'judge_sha256':{k:v for k,v in implementation.items() if k.startswith('src/lightyear_calibration/')},
        'comparison_register_sha256':register['content_sha256'],'builder_client':client_identity(executable),
        'requested_model':'gpt-6-astra','reasoning_effort':'high','provider_resolved_model':None,
        'max_client_invocations':maximum,'client_timeout_seconds':900,'max_elapsed_seconds':3600,
        'assessed_on':date.today().isoformat(),'human_authored_repair_bytes_target':0,
        'controller_changes_allowed':0,'budget_changes_allowed':0,'organization_api_migration':'deferred-by-user',
        'billing_usd':None,'cloud_resources':False,
        'scope':['purchase-order','material-receipt','vendor-invoice','outbound-payment'] if variant=='procure-to-pay' else ['partial-shipments','aggregate-invoice','credit-note','credit-reversal','controlled-concurrency','precommit-rollback-and-retry'],
        'transient_evidence_limit':'Operations require separate native session/lock/transaction captures. Procurement is a sequential purchase journey and makes no concurrency claim. No per-row undo history, crash recovery or load claim.',
        'source_transfer':{'destination':'Codex/OpenAI through the signed-in account',
                           'initial_prompt':(AREA/variant/'builder-input.json').as_posix(),
                           'allowed_repairs':['compile-error','api-type-mismatch','outside-footprint'],
                           'expected_business_outputs':False,'credentials':False,'database_rows':False}})
    campaign.mkdir(parents=True); save(campaign/'plan.json',plan)
    save(campaign/'declaration.json',JourneySigner(root).sign({'artifact_type':'lightyear-frozen-declaration',
        'plan_sha256':plan['content_sha256'],'execution_authorized':False}))
    return plan


def authorize(root, campaign, expected, approval):
    plan = frozen(root,campaign)
    require(plan['content_sha256'] == expected and approval.strip(), 'Exact plan approval required')
    require(not (campaign/'authorization.json').exists() and not (campaign/'started.json').exists(), 'Already authorized/started')
    result = JourneySigner(root).sign({'artifact_type':'lightyear-frozen-factory-authorization',
        'plan_sha256':expected,'operator_approval':approval,'max_client_invocations':plan['max_client_invocations']})
    save(campaign/'authorization.json',result); return result


def prompt(root,campaign):
    plan=read_json(campaign/'plan.json')
    return read_json(root/plan['variant_input_dir']/'builder-input.json')


def candidate(root,campaign,folder,proposal):
    plan = frozen(root,campaign)
    require(proposal['blocked_reason'] is None and len(proposal['edits']) == 1, 'Builder blocked or exceeded edit scope')
    edit = proposal['edits'][0]
    require(edit['path'] == HARNESS and edit['find'] == PLACEHOLDER, 'Unexpected candidate edit')
    build = folder/'build'; workspace = build/'workspace'; workspace.mkdir(parents=True)
    (workspace/HARNESS).write_bytes(PLACEHOLDER.encode())
    order = WorkOrder.from_dict(read_json(root/plan['variant_input_dir']/'work-order.json'))
    patch = PatchBroker().apply(order,IsolatedWorkspace(workspace,workspace,order.allowed_paths),proposal['edits'])
    code = (workspace/HARNESS).read_text(encoding='utf-8')
    require('class LightyearOperationsTest extends AbstractTestCase' in code, 'Unexpected generated class')
    require(all(term not in code for term in ('ProcessBuilder','Runtime.getRuntime','java.net.','System.getenv','/output/','/verifier/','ALTER USER','DROP TABLE')),
            'Generated harness requests out-of-scope capabilities')
    require((workspace/HARNESS).read_bytes() == edit['replace'].encode('utf-8'), 'Candidate bytes differ from model response')
    for name in ('prompt.json','proposal.json','events.jsonl','invocation.json'):
        shutil.copyfile(folder/name,build/name)
    receipt = JourneySigner(root).sign({'artifact_type':'lightyear-journey-builder',
        'campaign_plan_sha256':plan['content_sha256'],'builder_client':plan['builder_client'],
        'provider_invocations':len(list((campaign/'calls').glob('*/invocation.json'))),
        'judge_sha256':plan['judge_sha256'],'patch':patch,'human_authored_repair_bytes':0,
        'prompt_sha256':file_hash(build/'prompt.json'),'proposal_sha256':file_hash(build/'proposal.json'),
        'events_sha256':file_hash(build/'events.jsonl'),'harness_sha256':file_hash(workspace/HARNESS)})
    save(build/'receipt.json',receipt); return build,receipt


def audit(root,campaign,attempts):
    plan = frozen(root,campaign); key = (root/'work/ms87/operator/authority.public.pem').read_bytes(); previous = None
    builders = sorted((campaign/'calls').glob('*-builder/build/receipt.json'))
    require(len(builders)==len(attempts), 'Generated candidate lacks a complete native attempt record')
    for record in sorted((campaign/'calls').glob('*/receipt.json')):
        call = read_json(record)
        require(verify_envelope(call,key) and call['plan_sha256']==plan['content_sha256'], 'Call signature/plan changed')
        for name,field in [('prompt.json','prompt_sha256'),('events.jsonl','events_sha256'),('proposal.json','proposal_sha256')]:
            if call[field] is not None: require(file_hash(record.parent/name)==call[field], 'Call artifact changed')
    for index, attempt in enumerate(attempts,1):
        build = root/attempt['builder_directory']; receipt = read_json(build/'receipt.json')
        require(verify_envelope(attempt,key) and verify_envelope(receipt,key), 'Attempt/builder signature changed')
        require(attempt['judge_sha256'] == plan['judge_sha256'], 'Attempt judge changed')
        native = read_json(root/attempt['run_directory']/'receipt.json')
        require(verify_envelope(native,key) and native['content_sha256']==attempt['receipt_sha256'], 'Native attempt receipt changed')
        require(native['human_interventions_outside_designed_stops']==0, 'Native controller recorded an intervention')
        for name, field in [('prompt.json','prompt_sha256'),('proposal.json','proposal_sha256'),('events.jsonl','events_sha256'),('workspace/'+HARNESS,'harness_sha256')]:
            require(file_hash(build/name) == receipt[field], 'Builder artifact changed')
        proposed = read_json(build/'proposal.json')['edits'][0]['replace']
        require((build/'workspace'/HARNESS).read_bytes() == proposed.encode('utf-8'), 'Human candidate bytes detected')
        expected = prompt(root,campaign)
        if previous is not None:
            selected = read_json(campaign/f'feedback-{index-1}.json')
            require(verify_envelope(selected,key), 'Feedback signature changed')
            observations = read_json(campaign/f'analyst-input-{index-1}.json')['diagnostics']
            analyst_calls = [read_json(p.parent/'prompt.json') for p in sorted((campaign/'calls').glob('*-analyst/receipt.json'))]
            analyst_results = [read_json(p.parent/'proposal.json') for p in sorted((campaign/'calls').glob('*-analyst/receipt.json'))]
            require(any(p['diagnostics']==observations and p['candidate']==previous and r==selected['analyst_proposal']
                        for p,r in zip(analyst_calls,analyst_results)), 'Feedback is not the signed analyst response')
            require(selected['diagnostics'] == select_feedback(observations,selected['analyst_proposal'],True), 'Repair message changed')
            expected.update(previous_candidate=previous,analyst_feedback=selected['diagnostics'])
        require(read_json(build/'prompt.json') == expected, 'Undeclared builder prompt bytes')
        previous = proposed
    return {'verified':True,'human_authored_repair_bytes':0,'controller_changes':0}


def run(root,campaign,executable,remaining_seconds=None):
    plan = frozen(root,campaign); signer = JourneySigner(root); auth = read_json(campaign/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['plan_sha256'] == plan['content_sha256'], 'Missing exact-plan authorization')
    require(not (campaign/'receipt.json').exists(), 'Campaign is terminal; declare a new campaign')
    check_client(executable,plan['builder_client'])
    # Exclusive creation prevents a second controller consuming the same budget.
    with (campaign/'started.json').open('xb') as stream: stream.write(canonical({'plan_sha256':plan['content_sha256']}))
    started = time.monotonic(); attempts = []; previous = None; feedback = []; status = 'failed'; error = None
    ceiling=plan['max_elapsed_seconds'] if remaining_seconds is None else min(plan['max_elapsed_seconds'],remaining_seconds)
    def remaining(): return ceiling-(time.monotonic()-started)
    try:
        while True:
            frozen(root,campaign); require(remaining()>0,'Campaign elapsed budget exhausted')
            public = prompt(root,campaign)
            if previous is not None: public.update(previous_candidate=previous,analyst_feedback=feedback)
            folder,proposal = invoke(root,campaign,executable,'builder',public,BUILDER_SCHEMA,remaining())
            build,builder = candidate(root,campaign,folder,proposal)
            previous = (build/'workspace'/HARNESS).read_text(encoding='utf-8')
            native,receipt = execute_native(root,campaign,build,builder,remaining())
            frozen(root,campaign)
            attempt = signer.sign({'attempt':len(attempts)+1,'run_directory':native.relative_to(root).as_posix(),
                'receipt_sha256':receipt['content_sha256'],'judge_sha256':plan['judge_sha256'],
                'judge_version':VERSION,'comparison_register_sha256':plan['comparison_register_sha256'],
                'builder_directory':build.relative_to(root).as_posix(),'elapsed_seconds':receipt['elapsed_seconds'],
                'passed':receipt['bounded_observed_journey_equivalence'],'human_authored_repair_bytes':0})
            attempts.append(attempt); save(campaign/'attempts.json',attempts)
            if attempt['passed']: status = 'verified'; break
            require(read_json(native/'cleanup.json')['complete'], 'Native cleanup incomplete')
            observed = diagnostics(native,previous,read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
            save(campaign/f'analyst-input-{len(attempts)}.json',{'diagnostics':observed})
            if not observed: status = 'halted-no-supported-repair'; break
            if len(list((campaign/'calls').glob('*/invocation.json')))+2>plan['max_client_invocations']:
                status = 'halted-frozen-budget-exhausted'; break
            _,selection = invoke(root,campaign,executable,'analyst',analyst_prompt(observed,previous,public['api_reference'],receipt['error']),analyst_schema(observed),remaining())
            feedback = select_feedback(observed,selection,True)
            save(campaign/f'feedback-{len(attempts)}.json',signer.sign({'diagnostics':feedback,'analyst_proposal':selection}))
            if not feedback: status = 'halted-analyst-declined-supported-diagnostics'; break
    except Exception as exc:
        error = {'type':type(exc).__name__,'message':str(exc)}
        status = 'halted-frozen-budget-exhausted' if 'budget exhausted' in str(exc) else 'halted-campaign-error'
    finally:
        try: provenance = audit(root,campaign,attempts)
        except Exception as exc:
            provenance = {'verified':False,'human_authored_repair_bytes':None,'controller_changes':None,'reason':str(exc)}
            status = 'invalid-frozen-provenance'
        calls = [read_json(p) for p in sorted((campaign/'calls').glob('*/receipt.json'))]
        consumed = len(list((campaign/'calls').glob('*/invocation.json')))
        cost = cost_report(calls,attempts,time.monotonic()-started)
        cost['attempted_client_invocations'] = consumed
        cost['accounting_complete'] = consumed == len(calls)
        passed = status == 'verified' and provenance['verified'] and cost['accounting_complete']
        result = signer.sign({'artifact_type':'lightyear-frozen-factory-campaign','status':status,'error':error,
            'plan_sha256':plan['content_sha256'],'judge_version':VERSION,'judge_sha256':plan['judge_sha256'],
            'comparison_register_sha256':plan['comparison_register_sha256'],'attempts':attempts,'cost':cost,
            'provenance':provenance,'combined_gate_passed':passed,
            'dark_factory_run':passed,'claim_scope':'Bounded '+plan['scenario']+' journey with the declared native observer scope.',
            'requested_model':plan['requested_model'],'provider_resolved_model':None,
            'organization_api_migration':'deferred-by-user','platform_qualification':False,'independently_attested':False})
        save(campaign/'receipt.json',result)
    return result


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','authorize','run','audit'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--executable',type=Path);p.add_argument('--max-calls',type=int,default=5)
    p.add_argument('--variant',default='baseline');p.add_argument('--plan-sha256');p.add_argument('--approval');a=p.parse_args();root=a.root.resolve();campaign=a.campaign.resolve()
    if a.command=='prepare': result=prepare(root,campaign,a.executable.resolve(),a.max_calls,a.variant)
    elif a.command=='authorize': result=authorize(root,campaign,a.plan_sha256,a.approval or '')
    elif a.command=='audit': result=audit(root,campaign,read_json(campaign/'attempts.json'))
    else: result=run(root,campaign,a.executable.resolve())
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
