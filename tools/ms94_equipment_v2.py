"""Declare once, run Stage A once, stop at first non-pass. No model calls."""
import hashlib,json,time
from pathlib import Path
from lightyear_calibration.contracts import read_json,seal,verify,require
from lightyear_calibration.journey_order import make_plan,save,file_hash
from lightyear_calibration.journey_runtime import JourneySigner,read_local,inventory
from lightyear_control_tower.decisions import verify_envelope
from lightyear_calibration.ms94_faults_v2 import FAULTS
from tools.ms94_judge import VERSION

AREA=Path('factory/idempiere/qualification-ms94')


def schedule():
    positive=[{'scenario':s,'fault':'none','repeat':i} for s in ('operations','procure-to-pay') for i in range(1,11)]
    negative=[{'scenario':'procure-to-pay' if f=='costing-wrong-organization' else 'operations','fault':f,'repeat':i}
              for f in FAULTS for i in range(1,4)]
    return positive+negative


def freeze(root,output):
    require(not output.exists(),'Use a new equipment declaration')
    base=make_plan(root,read_local(root),inventory(root));pins=dict(base['implementation_sha256'])
    for directory,glob in [('src','**/*.py'),('factory/idempiere/qualification','**/*'),(str(AREA),'**/*')]:
        for p in (root/directory).glob(glob):
            if p.is_file():pins[p.relative_to(root).as_posix()]=file_hash(p)
    for pattern in ('ms94_equipment*.py','ms94_native.py','ms94_native_v2.py','ms94_judge.py','ms94_negative_checks*.py','ms94_publication.py','qualification_*.py','publish_native_journeys.py'):
        for p in (root/'tools').glob(pattern):pins[p.relative_to(root).as_posix()]=file_hash(p)
    for name in ('factory/idempiere/repeatability/comparison-register.json','docs/calibration/idempiere-boundaries/mappings.json'):
        pins[name]=file_hash(root/name)
    plan=seal({'artifact_type':'ms94-equipment-declaration','judge_version':VERSION,'base_plan':base,
        'implementation_sha256':pins,'schedule':schedule(),'model_calls':0,'max_parallel_pairs':1,
        'maximum_pairs':56,'max_elapsed_seconds':15*3600,'positive_passes_required':{'operations':10,'procure-to-pay':10},
        'negative_repeats':3,'mutation_score_required':1.0,'stop_on_first_nonpass':True,
        'reference_only':True,'autonomous_success':False,'human_review_packet_sha256':read_json(root/AREA/'review-packet-v2.json')['content_sha256'],
        'limits':['Lock-duration and duplicate-retry mutants are not scored. The native unique (AD_Client_ID, Value) index prevents the proposed duplicate-retry insert; this is not credited as a judge rejection. Duplicate invoice-line cardinality is tested instead.',
                  'Rollback mutation models a leaked committed draft; it does not disable a database rollback.',
                  'Timestamp mutant is a paired comparison rejection, with distinct native second offsets on both engines.'],
        'authorization':'User explicitly approved running the replacement declaration after the stopped first declaration; local deterministic Stage A only.', 'revision':2})
    output.mkdir(parents=True);save(output/'plan.json',plan)
    save(output/'declaration.json',JourneySigner(root).sign({'plan_sha256':plan['content_sha256'],'model_calls':0}))
    return plan


def frozen(root,output):
    plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    d=read_json(output/'declaration.json');require(verify_envelope(d,signer.public) and d['plan_sha256']==plan['content_sha256'],'Equipment declaration changed')
    for name,sha in plan['implementation_sha256'].items():require(file_hash(root/name)==sha,'Frozen equipment changed: '+name)
    require(plan['schedule']==schedule() and len(plan['schedule'])==56,'Qualification schedule changed')
    require(read_local(root)==plan['base_plan']['local'],'Native runtime changed')
    return plan


def run(root,output):
    from tools.ms94_native_v2 import qualify
    from tools.ms94_publication import publish,replay
    plan=frozen(root,output);signer=JourneySigner(root)
    with (output/'started.json').open('x',encoding='utf-8') as f:json.dump({'plan_sha256':plan['content_sha256'],'at':time.time()},f)
    start=time.monotonic();results=[];status='stopped';error=None
    try:
        for ordinal,slot in enumerate(plan['schedule'],1):
            frozen(root,output);require(time.monotonic()-start<plan['max_elapsed_seconds'],'Equipment time budget exhausted')
            trial=output/'attempts'/f'{ordinal:02d}-{slot["scenario"]}-{slot["fault"]}-{slot["repeat"]}'
            trial.parent.mkdir(exist_ok=True)
            r=qualify(root,trial,slot['fault'],slot['scenario'],
                'operations-support-ms94-v2' if slot['scenario']=='operations' else 'procure-to-pay',True)
            native=root/read_json(trial/'run.json')['run_directory']
            entry={'slot':ordinal,**slot,'receipt_sha256':r['content_sha256'],'run_directory':native.relative_to(root).as_posix(),
                   'qualification_check_passed':r['qualification_check_passed'],'status':r['status'],'publication_verified':False}
            results.append(entry);save(output/'progress.json',signer.sign({'results':results,'planned':56}))
            publication=output/'publications'/f'{ordinal:02d}'
            published=publish(root,native,publication)
            replayed=replay(root,publication,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
            save(publication/'verification.json',signer.sign(replayed))
            entry.update(publication_verified=True,publication_receipt_sha256=published['content_sha256'])
            frozen(root,output)
            if not r['qualification_check_passed']:break
        if len(results)==56 and all(x['qualification_check_passed'] and x['publication_verified'] for x in results):status='native-controls-passed-review-pending'
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)}
    value=signer.sign({'artifact_type':'ms94-stage-a-native-results','status':status,'error':error,
        'plan_sha256':plan['content_sha256'],'results':results,'unstarted_slots':56-len(results),
        'elapsed_seconds':round(time.monotonic()-start,3),'model_calls':0,'stage_b_authorized':False,
        'autonomous_success':False,'stage_a_accepted':False})
    save(output/'report.json',value);return value


def accept(root,output,reviews):
    plan=frozen(root,output);signer=JourneySigner(root);r=read_json(output/'report.json')
    require(verify_envelope(r,signer.public) and r['plan_sha256']==plan['content_sha256'],'Native report changed')
    require(r['status']=='native-controls-passed-review-pending' and len(r['results'])==56 and
            all(x['qualification_check_passed'] and x['publication_verified'] for x in r['results']),'Stage A native gates not passed')
    require({v['review_kind'] for v in reviews}=={'support-source','independent-purchasing-rule-and-reference'},'Both human reviews required')
    for v in reviews:
        require(verify_envelope(v,signer.public) and v['human_attestation'] and v['accepted'] and v['reviewer'].strip()
                and v['packet_sha256']==plan['human_review_packet_sha256'],'Invalid human review')
        if v['review_kind'].startswith('independent'):require(v['reviewer_is_author'] is False,'Purchasing review must be independent')
    value=signer.sign({'artifact_type':'ms94-stage-a-acceptance','passed':True,'plan_sha256':plan['content_sha256'],
        'native_report_sha256':r['content_sha256'],'reviews':reviews,'stage_a_accepted':True})
    require(not (output/'acceptance.json').exists(),'Acceptance already recorded');save(output/'acceptance.json',value);return value


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run']);p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();v=(freeze if a.command=='freeze' else run)(a.root.resolve(),a.output.resolve());print(json.dumps(v,indent=2))
