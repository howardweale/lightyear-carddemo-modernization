"""Frozen three-trial pilot, then ten baseline trials. No replacement slots."""
import json,math,time
from pathlib import Path
from lightyear_calibration.contracts import require,read_json,seal,verify
from lightyear_calibration.journey_order import save
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_control_tower.decisions import verify_envelope
from tools import ms94_controller_v4 as controller


def decision(passed,completed,void=False):
    if void:return 'void-equipment-failure-no-rate'
    if completed!=10:return 'incomplete-no-rate'
    if passed>=7:return 'recommend-separately-authorized-procure-to-pay-cohort'
    if passed<=3:return 'no-further-generation-until-failures-classified-and-reviewed'
    return 'review-intermediate-result-no-automatic-further-generation'


def interval(k,n):
    if not n:return None
    z=1.959963984540054;p=k/n;den=1+z*z/n
    centre=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return {'method':'Wilson score','confidence':0.95,'lower':max(0,centre-half),'upper':min(1,centre+half)}


def prepare(root,output,executable,equipment):
    controller.stage_a(root,equipment)
    require(not output.exists(),'Use a fresh Stage B cohort path')
    slots=[]
    for phase,count in [('pilot',3),('cohort',10)]:
        for i in range(1,count+1):
            trial=output/'trials'/f'{phase}-{i:02d}'
            plan=controller.prepare(root,trial,executable,equipment)
            slots.append({'phase':phase,'index':i,'path':trial.relative_to(root).as_posix(),'plan_sha256':plan['content_sha256']})
    plan=seal({'artifact_type':'ms94-single-condition-measurement','slots':slots,'max_client_invocations':65,
        'max_compilations':39,'max_elapsed_seconds':26*3600,'variant':'baseline-operations',
        'pilot_excluded_from_rate':True,'no_replaced_slots':True,'stop_on_equipment_failure':True,
        'stop_on_controller_or_provenance_failure':True,'decision_rules':{
          '7-10':'recommend separately authorized procure-to-pay','0-3':'no more generation before classification and review',
          '4-6':'review before further generation'},'result_classes':['passed','business-failure','execution-failure','judge-error','insufficient-evidence'],
        'source_transfer':read_json(root/slots[0]['path']/'plan.json')['source_transfer'],'billing_usd':None,'cloud_resources':False})
    save(output/'plan.json',plan);save(output/'declaration.json',JourneySigner(root).sign({'plan_sha256':plan['content_sha256']}))
    return plan


def authorize(root,output,expected,approval):
    plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    require(plan['content_sha256']==expected and approval.strip(),'Exact prepared budget/source-transfer approval required')
    require(not (output/'authorization.json').exists() and not (output/'started.json').exists(),'Already authorized/started')
    first=read_json(root/plan['slots'][0]['path']/'plan.json')
    equipment=root/first['equipment_directory']
    controller.stage_a(root,equipment,live=True)
    publication=read_json(equipment/'published-assets.json')
    for s in plan['slots']:require(controller.frozen(root,root/s['path'])['content_sha256']==s['plan_sha256'],'Trial changed')
    value=signer.sign({'plan_sha256':expected,'operator_approval':approval,
        'stage_a_publication_sha256':publication['content_sha256'],
        'max_client_invocations':plan['max_client_invocations'],'max_compilations':plan['max_compilations']})
    save(output/'authorization.json',value)
    for s in plan['slots']:
        save(root/s['path']/'authorization.json',signer.sign({'plan_sha256':s['plan_sha256'],
            'stage_a_publication_sha256':publication['content_sha256'],
            'cohort_authorization_sha256':value['content_sha256'],'operator_approval':approval}))
    return value


def run(root,output,executable):
    from tools.ms94_publication_b_v4 import publish,replay
    import hashlib
    plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    auth=read_json(output/'authorization.json');declaration=read_json(output/'declaration.json')
    require(all(verify_envelope(v,signer.public) and v['plan_sha256']==plan['content_sha256'] for v in (auth,declaration)),
            'Untrusted cohort authorization/declaration')
    require(len(plan['slots'])==13 and [s['phase'] for s in plan['slots']]==['pilot']*3+['cohort']*10,'Slot schedule changed')
    with (output/'started.json').open('x') as f:json.dump({'plan_sha256':plan['content_sha256']},f)
    start=time.monotonic();results=[];void=False;error=None
    try:
        for slot in plan['slots']:
            require(time.monotonic()-start<plan['max_elapsed_seconds'],'Cohort time budget exhausted')
            save(output/'active.json',signer.sign({'phase':slot['phase'],'index':slot['index'],'started_at':time.time()}))
            trial=root/slot['path'];require(controller.frozen(root,trial)['content_sha256']==slot['plan_sha256'],'Frozen slot changed')
            result=controller.run(root,trial,executable,plan['max_elapsed_seconds']-(time.monotonic()-start))
            entry={**slot,'receipt_sha256':result['content_sha256'],'status':result['status'],
                'first_try_pass':result['first_try_pass'],'repaired_pass':result['repaired_pass'],
                'attempts':[{'result_class':a['result_class'],'run_directory':a['run_directory']} for a in result['attempts']],
                'cost':result['cost'],'published':False}
            results.append(entry);save(output/'progress.json',signer.sign({'results':results}))
            print(json.dumps({'event':'trial-terminal','phase':slot['phase'],'index':slot['index'],'status':result['status']}),flush=True)
            if result['status'] in ('void-equipment-failure','invalid-provenance','halted-controller-failure'):
                save(output/'stopping.json',signer.sign({'slot':slot,'status':result['status'],'notify_immediately':True}))
            for i,a in enumerate(result['attempts'],1):
                publication=output/'publications'/f'{slot["phase"]}-{slot["index"]:02d}-{i}'
                publish(root,root/a['run_directory'],publication)
                verified=replay(root,publication,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
                save(publication/'verification.json',signer.sign(verified))
            entry['published']=True
            save(output/'progress.json',signer.sign({'results':results}))
            if result['status'] in ('void-equipment-failure','invalid-provenance','halted-controller-failure'):
                void=True;break
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)};void=True
    cohort=[r for r in results if r['phase']=='cohort'];passed=sum(r['status']=='passed' for r in cohort)
    value=signer.sign({'artifact_type':'ms94-stage-b-results','plan_sha256':plan['content_sha256'],
        'results':results,'unstarted_slots':13-len(results),'cohort_completed':len(cohort),'cohort_passed':passed,
        'cohort_void':void,'decision':decision(passed,len(cohort),void),'error':error,
        'rate':passed/10 if len(cohort)==10 and not void else None,
        'interval':interval(passed,10) if len(cohort)==10 and not void else None,
        'elapsed_seconds':round(time.monotonic()-start,3),'pilot_excluded_from_rate':True,
        'scope':'One baseline operations journey on this frozen equipment; no unfamiliar journey or production qualification claim.'})
    save(output/'report.json',value);return value


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','authorize','run']);p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--equipment',type=Path);p.add_argument('--executable',type=Path)
    p.add_argument('--plan-sha256');p.add_argument('--approval');a=p.parse_args();root=a.root.resolve();output=a.output.resolve()
    value=prepare(root,output,a.executable.resolve(),a.equipment.resolve()) if a.command=='prepare' else authorize(root,output,a.plan_sha256,a.approval or '') if a.command=='authorize' else run(root,output,a.executable.resolve())
    print(json.dumps(value,indent=2))
