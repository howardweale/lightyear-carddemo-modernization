"""Issue a new signed assessment without rewriting the old native run."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil
import time
import uuid

from lightyear_calibration.contracts import canonical, read_json, require, seal, verify
from lightyear_calibration.journey_order import RUNS, file_hash, save
from lightyear_calibration.journey_runtime import JourneySigner, CONTROL
from lightyear_calibration.journey_campaign import check_hashes
from lightyear_calibration.journey_contracts import CONTRACT, current_contract
from lightyear_calibration.journey_judge_v2 import compare, POLICY_ID
from lightyear_calibration.native_reconciliation import state, rows
from lightyear_calibration.native_catalog import read_capture
from lightyear_calibration.partial_invoicing import verify_run
from lightyear_control_tower.decisions import verify_envelope

if __package__:
    from tools.publish_native_journeys import verify_run_identity
else:
    from publish_native_journeys import verify_run_identity

POLICY=Path('factory/idempiere/contracts/partial-invoicing-comparison-v2.json')
EXTRA_IMPLEMENTATION=('src/lightyear_calibration/journey_judge_v2.py',
                      'tools/evaluate_journey_judge_v2.py',
                      'src/lightyear_calibration/journey_contracts.py')


def source_files(run):
    files=[run/name for name in ('plan.json','authorization.json','receipt.json','gate.json',
                                 'cleanup.json','journal.json','selected-attempts.json','authority.public.pem')]
    files.extend(p for name in ('inputs','cases') for p in (run/name).rglob('*') if p.is_file())
    require(not any(p.is_symlink() for p in files),'Symbolic source evidence is not permitted')
    return {p.relative_to(run).as_posix():file_hash(p) for p in files}


def native_context(folder):
    snapshots={lane:state(folder/'after'/lane,lane) for lane in ('oracle','postgresql')}
    catalogs={lane:read_capture(folder/'baseline'/lane/'catalog.json') for lane in snapshots}
    types={}
    for lane,snapshot in snapshots.items():
        columns=[c for c in snapshot['structure']['columns']
                 if c['table_name'].lower()=='m_inout' and c['column_name'].lower()=='shipdate']
        require(len(columns)==1,'Ambiguous shipment datatype')
        types[lane]=columns[0]['data_type']
    oracle=catalogs['oracle']['results']['identity']['rows']
    postgres=[r for r in catalogs['postgresql']['results']['settings']['rows'] if r['name']=='TimeZone']
    require(len(oracle)==len(postgres)==1,'Ambiguous capture session timezone')
    return {'oracle_datatype':types['oracle'],'postgresql_datatype':types['postgresql'],
        'capture_session_timezones':{'oracle':oracle[0]['time_zone'],'postgresql':postgres[0]['setting']},
        'timezone_scope':'Captured database sessions and naive native row values; no claim about arbitrary client or production timezones.',
        'catalog_sha256':{l:c['content_sha256'] for l,c in catalogs.items()},
        'state_sha256':{l:s['content_sha256'] for l,s in snapshots.items()}},snapshots


def shipment_bindings(folder,lanes,snapshots):
    records={l:rows(folder/'after'/l,snapshots[l]['tables']['m_inout']) for l in lanes}
    bindings={}
    for stage in ('firstShipment','shipment'):
        binding={'table':'m_inout','column':'shipdate'}
        for lane in lanes:
            identity=lanes[lane]['trace'][stage+'.id']
            require(identity.isdigit(),'Invalid shipment identifier')
            matches=[r for r in records[lane] if r['m_inout_id']==int(identity)]
            require(len(matches)==1,'Missing or ambiguous native shipment')
            binding[lane]=matches[0]['shipdate'];binding[lane+'_id']=identity
        require(binding['oracle_id']==binding['postgresql_id'],'Shipment row keys differ')
        binding['key']=canonical([int(binding['oracle_id'])]).decode()
        bindings[stage]=binding
    return bindings


def evaluate(root,run,output):
    root=root.resolve();run=run.resolve();output=output.resolve();started=time.monotonic()
    require(run.parent==root/RUNS and output.is_relative_to(root) and not output.exists(),'Unsafe or existing assessment path')
    signer=JourneySigner(root);terminal=verify_run_identity(run,signer.public)
    original_plan=read_json(run/'plan.json');old_gate=read_json(run/'gate.json');verify(old_gate)
    events=read_json(run/'journal.json')
    require(any(e['type']=='gate' and e['payload'].get('receipt_sha256')==old_gate['content_sha256']
                and e['payload']['passed']==old_gate['passed'] for e in events),'Original gate is not anchored in its signed journal')
    require(old_gate['plan_sha256']==original_plan['content_sha256'],'Original gate plan differs')
    cleanup=read_json(run/'cleanup.json')
    require(verify_envelope(cleanup,signer.public) and cleanup['complete']
            and cleanup['content_sha256']==terminal['cleanup_sha256'],'Original cleanup is not verified')
    check_hashes(root,original_plan['judge_sha256'])
    policy=read_json(root/POLICY);decision=read_json(root/CONTRACT)
    require(current_contract(root)['effective'],'Timestamp contract needs review')
    source=source_files(run)
    implementation={**original_plan['judge_sha256'],**{p:file_hash(root/p) for p in EXTRA_IMPLEMENTATION}}
    plan=seal({'artifact_type':'lightyear-versioned-judge-assessment-plan','judge_version':POLICY_ID,
        'run_id':run.name,'source_directory':run.relative_to(root).as_posix(),
        'original_receipt_sha256':terminal['content_sha256'],'original_gate_sha256':old_gate['content_sha256'],
        'policy_sha256':file_hash(root/POLICY),'timestamp_decision_sha256':decision['content_sha256'],
        'source_files':source,'implementation_sha256':implementation,'assessed_on':date.today().isoformat(),
        'new_model_calls':0,'new_native_executions':0})
    authorization=signer.sign({'artifact_type':'lightyear-versioned-judge-authorization',
        'plan_sha256':plan['content_sha256'],'actor':'Howard Weale',
        'authorization':'User requested applying the accepted timestamp scope and numeric comparison rules through a versioned judge update while preserving the original result.'})
    # The old verifier writes derived summaries. Give it a separate workspace.
    staging=root/'work/ms90'/('assessment-'+uuid.uuid4().hex)
    require(staging.resolve().is_relative_to((root/'work/ms90').resolve()),'Unsafe assessment workspace')
    copied=staging/RUNS/run.name;copied.mkdir(parents=True)
    for name in source:
        target=copied/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(run/name,target)
    trust=staging/CONTROL/'authority.public.pem';trust.parent.mkdir(parents=True);trust.write_bytes(signer.public)
    recomputed=verify_run(copied)
    require(recomputed==old_gate,'Retained native evidence does not reproduce the original judge result')
    attempt=read_json(copied/'selected-attempts.json')['partial-invoicing']
    folder=copied/'cases/partial-invoicing'/str(attempt)
    lanes={l:read_json(folder/'verified'/(l+'.json')) for l in ('oracle','postgresql')}
    effects=read_json(folder/'verified/effects.json')
    context,snapshots=native_context(folder)
    bindings=shipment_bindings(folder,lanes,snapshots)
    result=compare(lanes,effects,recomputed['comparison'],bindings,context,policy,decision,date.fromisoformat(plan['assessed_on']))
    require(source_files(run)==source,'Original native evidence changed during assessment')
    check_hashes(root,implementation)
    require(file_hash(root/POLICY)==plan['policy_sha256'] and read_json(root/CONTRACT)==decision,'Decision changed during assessment')
    output.mkdir(parents=True)
    artifacts={'plan.json':plan,'authorization.json':authorization,'comparison-v2.json':result,
               'policy.json':policy,'timestamp-decision.json':decision,'original-gate.json':old_gate,
               'original-receipt.json':terminal,'original-plan.json':original_plan,
               'original-authorization.json':read_json(run/'authorization.json'),'original-journal.json':events,
               'original-effects.json':effects,'native-oracle.json':lanes['oracle'],'native-postgresql.json':lanes['postgresql']}
    for name,value in artifacts.items():save(output/name,value)
    shutil.copyfile(root/POLICY,output/'policy.json')
    receipt=signer.sign({'artifact_type':'lightyear-versioned-judge-assessment','judge_version':POLICY_ID,
        'run_id':run.name,'plan_sha256':plan['content_sha256'],'comparison_sha256':result['content_sha256'],
        'status':result['status'],'passed':result['passed'],'original_receipt_sha256':terminal['content_sha256'],
        'original_status':terminal['status'],'original_gate_passed':old_gate['passed'],
        'original_gate_reproduced':True,'original_source_preserved':True,
        'assessment_kind':'retained-native-evidence-reassessment','timestamp_review_date':decision['review_date'],
        'artifacts':{name:file_hash(output/name) for name in artifacts},
        'implementation_sha256':implementation,'elapsed_seconds':round(time.monotonic()-started,3),
        'new_model_calls':0,'new_native_executions':0,'cloud_resources_started':False,
        'application_equivalence':False,'schema_equivalence':False,'platform_qualification':False,'independently_attested':False})
    save(output/'receipt.json',receipt);(output/'authority.public.pem').write_bytes(signer.public)
    return receipt


def verify_assessment(output):
    """Recompute v2 from published native summaries; full native replay is separate."""
    key=(output/'authority.public.pem').read_bytes();receipt=read_json(output/'receipt.json')
    require(verify_envelope(receipt,key),'Assessment signature differs')
    for name,expected in receipt['artifacts'].items():
        require(Path(name).name==name and file_hash(output/name)==expected,'Assessment artifact changed')
    plan=read_json(output/'plan.json');verify(plan)
    auth=read_json(output/'authorization.json');decision=read_json(output/'timestamp-decision.json')
    original=read_json(output/'original-receipt.json');gate=read_json(output/'original-gate.json')
    verify(gate)
    require(verify_envelope(auth,key) and auth['plan_sha256']==plan['content_sha256']==receipt['plan_sha256'],'Assessment authorization differs')
    require(verify_envelope(decision,key) and decision['content_sha256']==plan['timestamp_decision_sha256'],'Timestamp decision differs')
    require(verify_envelope(original,key) and original['content_sha256']==receipt['original_receipt_sha256']==plan['original_receipt_sha256'],'Original receipt differs')
    require(gate['content_sha256']==plan['original_gate_sha256'] and gate['passed']==receipt['original_gate_passed'],'Original gate differs')
    prior_plan=read_json(output/'original-plan.json');verify(prior_plan)
    require(original['plan_sha256']==gate['plan_sha256']==prior_plan['content_sha256'],'Original plan binding differs')
    from lightyear_data.contracts import content_hash
    from lightyear_workflow.campaign_journals import check
    prior_auth=read_json(output/'original-authorization.json');events=read_json(output/'original-journal.json')
    require(verify_envelope(prior_auth,key) and prior_auth['plan']['plan_sha256']==prior_plan['content_sha256'],'Original authorization differs')
    require(prior_auth['run_id']==original['run_id']==plan['run_id']==receipt['run_id'], 'Run identity differs')
    require(file_hash(output/'policy.json')==plan['policy_sha256'], 'Policy identity differs')
    previous=None
    for n,event in enumerate(events,1):
        require(event['sequence']==n and event['previous_sha256']==previous and event['content_sha256']==content_hash(event),'Original journal differs')
        previous=event['content_sha256']
    check(events,prior_auth,key,'journey')
    require(events and events[-1]['type']=='halted' and any(e['type']=='gate' and e['payload'].get('receipt_sha256')==gate['content_sha256'] for e in events),'Original gate journal binding differs')
    require(all(events[-1]['payload'].get(k)==v for k,v in original.items() if k not in ('signature','content_sha256')), 'Original terminal journal receipt differs')
    lanes={l:read_json(output/('native-'+l+'.json')) for l in ('oracle','postgresql')}
    result=read_json(output/'comparison-v2.json');verify(result)
    replay=compare(lanes,read_json(output/'original-effects.json'),gate['comparison'],result['shipment_bindings'],
                   result['native_context'],read_json(output/'policy.json'),decision,date.fromisoformat(plan['assessed_on']))
    require(replay==result and result['content_sha256']==receipt['comparison_sha256']
            and result['passed']==receipt['passed'] and result['status']==receipt['status'],'Versioned comparison differs')
    return {'status':'verified-versioned-assessment','passed':result['passed'],
            'original_gate_passed':gate['passed'],'full_native_gate_replayed':False,
            'verification_scope':'Signed source and original journal bindings, then deterministic v2 comparison of retained native summaries',
            'independently_attested':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['evaluate','verify'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--run',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=evaluate(a.root,a.run,a.output) if a.command=='evaluate' else verify_assessment(a.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('artifacts','implementation_sha256','signature')},indent=2))


if __name__=='__main__':main()
