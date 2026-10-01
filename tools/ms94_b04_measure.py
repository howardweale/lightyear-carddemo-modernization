"""Frozen three-trial pilot, then twenty contract-clarified trials. No replacement slots."""
import json,math,time
from pathlib import Path
from lightyear_calibration.contracts import require,read_json,seal,verify
from lightyear_calibration.journey_order import save
from tools.ms94_signer_v5 import JourneySigner
from lightyear_control_tower.decisions import verify_envelope
from tools import ms94_b04_controller as controller


def decision(repaired,eligible,completed,void=False):
    if void:return 'void-equipment-failure-no-rate'
    if completed!=20:return 'incomplete-no-rate'
    if not eligible:return 'no-eligible-execution-failure-repair-conversion-undefined'
    rate=repaired/eligible
    if rate>=0.5:return 'repair-loop-works-on-this-journey-no-automatic-ms95'
    if rate>=0.2:return 'partial-classify-unrepaired-before-change'
    return 'diagnostic-not-enough-classify-before-next-intervention'


def interval(k,n):
    if not n:return None
    z=1.959963984540054;p=k/n;den=1+z*z/n
    centre=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return {'method':'Wilson score','confidence':0.95,'lower':max(0,centre-half),'upper':min(1,centre+half)}


def prepare(root,output,executable,equipment):
    controller.stage_a(root,equipment)
    require(not output.exists(),'Use a fresh Stage B cohort path')
    slots=[]
    for phase,count in [('pilot',3),('cohort',20)]:
        for i in range(1,count+1):
            trial=output/'trials'/f'{phase}-{i:02d}'
            plan=controller.prepare(root,trial,executable,equipment)
            slots.append({'phase':phase,'index':i,'path':trial.relative_to(root).as_posix(),'plan_sha256':plan['content_sha256']})
    from tools.ms94_b04_inputs import compare
    comparison=compare(root,read_json(root/slots[0]['path']/'plan.json'))
    plan=seal({'artifact_type':'ms94-b04-closed-runtime-measurement','slots':slots,'max_client_invocations':115,
        'max_compilations':69,'max_elapsed_seconds':26*3600,'variant':'closed-runtime-diagnostic-only','first_attempt_comparison':comparison,
        'repair_conversion_denominator':'Cohort first attempts classified execution-failure with nonempty closed feedback actually sent in a subsequent builder invocation.',
        'diagnostic_coverage_denominator':'All cohort execution-failure attempts; numerator requires actual subsequent builder delivery.',
        'diagnostic_export_coverage_reported_separately':True,
        'prerequisites':controller.prerequisites(root),
        'pilot_excluded_from_rate':True,'no_replaced_slots':True,'stop_on_equipment_failure':True,
        'stop_on_controller_or_provenance_failure':True,'decision_rules':{
          'at-least-50-percent':'repair loop works on this journey; no automatic MS95',
          '20-to-under-50-percent':'partial; classify unrepaired before change',
          'under-20-percent':'diagnostic not enough; classify before another intervention',
          'zero-eligible':'undefined; no repair effectiveness claim'},
        'result_classes':['passed','business-failure','execution-failure','contract-violation','judge-error','insufficient-evidence'],
        'support_suspicion':'Empty feedback, halted-equipment-suspect, review required; does not automatically void campaign.',
        'scope_limits':['Original wait-only omission remains unqualified; missing-stimulus-and-wait is the qualified stronger scope.',
            'Historical A1 source evidence and new dated-source evidence are separate.',
            'Application clock and period windows remain real-time; no universal clock invariance.',
            'No smoke tool, allocation teaching, public prompt, tools, model or support changes.'],
        'source_transfer':read_json(root/slots[0]['path']/'plan.json')['source_transfer'],'billing_usd':None,'cloud_resources':False})
    save(output/'plan.json',plan);save(output/'declaration.json',JourneySigner(root).sign({'plan_sha256':plan['content_sha256']}))
    return plan


def authorize(root,output,expected,approval):
    plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    require(plan['content_sha256']==expected and approval.strip(),'Exact prepared budget/source-transfer approval required')
    require(not (output/'authorization.json').exists() and not (output/'started.json').exists(),'Already authorized/started')
    from tools.ms94_b04_admission import public_freeze
    published=public_freeze(root,output,plan,signer.public)
    first=read_json(root/plan['slots'][0]['path']/'plan.json')
    equipment=root/first['equipment_directory']
    controller.stage_a(root,equipment,live=True)
    publication=read_json(equipment/'published-assets.json')
    for s in plan['slots']:require(controller.frozen(root,root/s['path'])['content_sha256']==s['plan_sha256'],'Trial changed')
    value=signer.sign({'plan_sha256':expected,'operator_approval':approval,
        'stage_a_publication_sha256':publication['content_sha256'],
        'b04_publication_sha256':published['content_sha256'],'cohort_directory':output.relative_to(root).as_posix(),
        'max_client_invocations':plan['max_client_invocations'],'max_compilations':plan['max_compilations']})
    save(output/'authorization.json',value)
    for s in plan['slots']:
        save(root/s['path']/'authorization.json',signer.sign({'plan_sha256':s['plan_sha256'],
            'stage_a_publication_sha256':publication['content_sha256'],
        'b04_publication_sha256':published['content_sha256'],'cohort_directory':output.relative_to(root).as_posix(),
            'cohort_authorization_sha256':value['content_sha256'],'operator_approval':approval}))
    return value


def run(root,output,executable):
    from tools.ms94_b04_publication import publish,replay
    import hashlib
    plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    auth=read_json(output/'authorization.json');declaration=read_json(output/'declaration.json')
    require(all(verify_envelope(v,signer.public) and v['plan_sha256']==plan['content_sha256'] for v in (auth,declaration)),
            'Untrusted cohort authorization/declaration')
    from tools.ms94_b04_admission import public_freeze
    published=public_freeze(root,output,plan,signer.public)
    require(auth['b04_publication_sha256']==published['content_sha256'],'Public B04 authorization differs')
    require(len(plan['slots'])==23 and [s['phase'] for s in plan['slots']]==['pilot']*3+['cohort']*20,'Slot schedule changed')
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
                'cost':result['cost'],'metrics':result['metrics'],'published':False}
            results.append(entry);save(output/'progress.json',signer.sign({'results':results}))
            print(json.dumps({'event':'trial-terminal','phase':slot['phase'],'index':slot['index'],'status':result['status']}),flush=True)
            if result['status'] in ('void-equipment-failure','invalid-provenance','halted-controller-failure'):
                save(output/'stopping.json',signer.sign({'slot':slot,'status':result['status'],'notify_immediately':True}))
            for i,a in enumerate(result['attempts'],1):
                publication=output/'publications'/f'{slot["phase"]}-{slot["index"]:02d}-{i}'
                publish(root,root/a['run_directory'],publication)
                verified=replay(root,publication,hashlib.sha256(signer.public).hexdigest(),root/'work/ms94')
                require(all(verified[k] for k in ('verified','full_entry_replayed','complete_gate_replayed','diagnostic_replayed')), 'Incomplete full B04 replay')
                save(publication/'verification.json',signer.sign(verified))
            require(sum(r['cost']['client_invocations'] for r in results)<=plan['max_client_invocations']
                    and sum(r['cost']['compilations'] for r in results)<=plan['max_compilations'], 'Aggregate budget exceeded')
            entry['published']=True
            save(output/'progress.json',signer.sign({'results':results}))
            if result['status'] in ('void-equipment-failure','invalid-provenance','halted-controller-failure'):
                void=True;break
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)};void=True
        save(output/'stopping.json',signer.sign({'error':error,'notify_immediately':True}))
    cohort=[r for r in results if r['phase']=='cohort'];passed=sum(r['status']=='passed' for r in cohort)
    measured=summary(results,void)
    value=signer.sign({'artifact_type':'ms94-b04-results','plan_sha256':plan['content_sha256'],
        'results':results,'unstarted_slots':23-len(results),'cohort_completed':len(cohort),'cohort_passed':passed,
        'cohort_void':void,'decision':decision(measured['repair_passes'],measured['repair_eligible'],len(cohort),void),'error':error,
        'measurement':measured,'first_attempt_comparison':plan['first_attempt_comparison'],
        'pooled_first_try':None,
        'rate':passed/20 if len(cohort)==20 and not void else None,
        'interval':interval(passed,20) if len(cohort)==20 and not void else None,
        'elapsed_seconds':round(time.monotonic()-start,3),'pilot_excluded_from_rate':True,
        'scope':'One baseline operations journey on this frozen equipment; no unfamiliar journey or production qualification claim.'})
    save(output/'report.json',value);return value


def summary(results,void=False):
    cohort=[r for r in results if r['phase']=='cohort']
    valid=len(cohort)==20 and not void
    first=sum(r['first_try_pass'] for r in cohort)
    eligible=sum(r['metrics']['repair_conversion_eligible'] for r in cohort)
    repaired=sum(r['metrics']['repair_conversion_eligible'] and r['repaired_pass'] for r in cohort)
    failures=sum(r['metrics']['execution_failures'] for r in cohort)
    sent=sum(r['metrics']['execution_failures_with_diagnostic_sent'] for r in cohort)
    exported=sum(r['metrics']['execution_failures_with_diagnostic_exported'] for r in cohort)
    totals={k:sum(r['cost'].get(k,0) for r in results) for k in (
        'client_invocations','builder_invocations','analyst_invocations','compilations',
        'input_tokens','cached_input_tokens','output_tokens','calls_with_unknown_usage',
        'agent_elapsed_seconds','native_elapsed_seconds','total_elapsed_seconds')}
    totals['uncached_input_tokens']=totals['input_tokens']-totals['cached_input_tokens']
    totals['usage_complete']=all(r['cost']['usage_complete'] for r in results)
    return {'first_try_passes':first,'first_try_rate':first/20 if valid else None,
            'first_try_interval':interval(first,20) if valid else None,
            'repair_eligible':eligible,'repair_passes':repaired,
            'repair_conversion':repaired/eligible if valid and eligible else None,
            'execution_failures':failures,'execution_failures_with_diagnostic_sent':sent,
            'diagnostic_coverage':sent/failures if valid and failures else None,
            'execution_failures_with_diagnostic_exported':exported,
            'diagnostic_export_coverage':exported/failures if valid and failures else None,
            'post_repair_business_failures':sum(r['metrics']['post_repair_business_failures'] for r in cohort),
            'equipment_suspect_review_required':[{'phase':r['phase'],'index':r['index']} for r in results
                                                if r['status']=='halted-equipment-suspect'],
            'cost_including_excluded_pilots':totals,'pilots_excluded_from_all_effectiveness_metrics':True}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','authorize','run']);p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--equipment',type=Path);p.add_argument('--executable',type=Path)
    p.add_argument('--plan-sha256');p.add_argument('--approval');a=p.parse_args();root=a.root.resolve();output=a.output.resolve()
    value=prepare(root,output,a.executable.resolve(),a.equipment.resolve()) if a.command=='prepare' else authorize(root,output,a.plan_sha256,a.approval or '') if a.command=='authorize' else run(root,output,a.executable.resolve())
    print(json.dumps(value,indent=2))
