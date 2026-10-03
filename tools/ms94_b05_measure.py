"""Frozen three-trial pilot, then twenty contract-clarified trials. No replacement slots."""
import json,math,time
from pathlib import Path
from lightyear_calibration.contracts import require,read_json,seal,verify
from lightyear_calibration.journey_order import save
from tools.ms94_signer_v5 import JourneySigner
from lightyear_control_tower.decisions import verify_envelope
from tools import ms94_b05_controller as controller


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


def run(root,output,executable):
    from tools.ms94_b05_supervisor import run_unit
    from tools.ms94_b05_stops import IMMEDIATE,notify
    from tools.ms94_b05_review import wait_for_review
    import hashlib
    plan=read_json(output/'plan.json');verify(plan);signer=JourneySigner(root)
    from tools.ms94_b05_admission import model_authorization
    from tools.ms94_b05_admission import CONFIG,CAMPAIGN,actual_cleanup
    require(output==root/CAMPAIGN and plan==read_json(root/CONFIG/'campaign.json'),'Executable cohort plan changed')
    model_authorization(root,launching=True)
    require(len(plan['slots'])==23 and [s['phase'] for s in plan['slots']]==['pilot']*3+['cohort']*20,'Slot schedule changed')
    with (output/'started.json').open('x') as f:json.dump({'plan_sha256':plan['content_sha256']},f)
    start=time.monotonic();results=[];void=False;error=None;started_slots=0;interrupted=None
    try:
        for slot in plan['slots']:
            require(not (output/'stopping.json').exists(),'Campaign stop forbids next slot')
            model_authorization(root)
            require(time.monotonic()-start<plan['max_elapsed_seconds'],'Cohort time budget exhausted')
            save(output/'active.json',signer.sign({'phase':slot['phase'],'index':slot['index'],'started_at':time.time()}))
            trial=root/slot['path'];require(controller.frozen(root,trial)['content_sha256']==slot['plan_sha256'],'Frozen slot changed')
            started_slots+=1
            result=run_unit(root,trial,'measurement',executable,plan['max_elapsed_seconds']-(time.monotonic()-start))['result']
            entry={**slot,'receipt_sha256':result['content_sha256'],'status':result['status'],
                'first_try_pass':result['first_try_pass'],'repaired_pass':result['repaired_pass'],
                'attempts':[{'result_class':a['result_class'],'run_directory':a['run_directory']} for a in result['attempts']],
                'cost':result['cost'],'metrics':result['metrics'],'published':True,
                'supervision_sha256':read_json(trial/'supervision-receipt.json')['content_sha256'],
                'total_with_finalization_seconds':read_json(trial/'supervision-receipt.json')['total_elapsed_seconds']}
            results.append(entry);save(output/'progress.json',signer.sign({'results':results}))
            print(json.dumps({'event':'trial-terminal','phase':slot['phase'],'index':slot['index'],'status':result['status']}),flush=True)
            if result['status'] in IMMEDIATE:notify(root,trial,result['status'])
            require(sum(r['cost']['client_invocations'] for r in results)<=plan['max_client_invocations']
                    and sum(r['cost']['compilations'] for r in results)<=plan['max_compilations'], 'Aggregate budget exceeded')
            entry['published']=True
            save(output/'progress.json',signer.sign({'results':results}))
            if result['status'] in IMMEDIATE:
                void=True
                break
            resolution=wait_for_review(root,trial,start,plan['max_elapsed_seconds'])
            if resolution:
                entry['operator_review']=resolution
                save(output/'progress.json',signer.sign({'results':results}))
                if resolution['action'] in ('stop','void'):
                    void=resolution['action']=='void'
                    break
    except Exception as exc:
        error={'type':type(exc).__name__,'message':str(exc)};void=True
        save(output/'stopping.json',signer.sign({'error':error,'notify_immediately':True}))
        if started_slots>len(results):
            interrupted={'slot':slot,'trial_directory':slot['path'],
                'invocations_started':len(list(trial.glob('calls/*/invocation.json'))),
                'completed_call_receipts':len(list(trial.glob('calls/*/receipt.json'))),
                'receipt_exists':(trial/'receipt.json').exists(),
                'supervision_receipt_exists':(trial/'supervision-receipt.json').exists(),
                'cost_accounting_complete':False,
                'note':'All interrupted call, compiler, native and recovery evidence retained locally; completed totals below exclude this interrupted slot and are not a full campaign cost.'}
    cohort=[r for r in results if r['phase']=='cohort'];passed=sum(r['status']=='passed' for r in cohort)
    measured=summary(results,void)
    value=signer.sign({'artifact_type':'ms94-b05-results','plan_sha256':plan['content_sha256'],
        'results':results,'unstarted_slots':23-started_slots,'started_slots':started_slots,'interrupted_trial':interrupted,
        'cost_accounting_complete':interrupted is None,'cohort_completed':len(cohort),'cohort_passed':passed,
        'cohort_void':void,'decision':decision(measured['repair_passes'],measured['repair_eligible'],len(cohort),void),'error':error,
        'primary_metric':'final cohort pass rate with Wilson 95% interval','failure_classification':'B03 categories; operator review, not independent',
        'measurement':measured,'first_attempt_comparison':plan['first_attempt_comparison'],
        'operator_decisions':[r['operator_review'] for r in results if 'operator_review' in r],
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
            'cost_including_excluded_pilots':totals,
            'completed_trials_total_including_finalization_seconds':sum(r.get('total_with_finalization_seconds',0) for r in results),
            'operator_waiting_seconds':sum(r.get('operator_review',{}).get('waiting_seconds',0) for r in results),
            'pilots_excluded_from_all_effectiveness_metrics':True}


if __name__=='__main__':
    import argparse
    from tools.ms94_b05_admission import CAMPAIGN
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--executable',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.root.resolve(),a.root.resolve()/CAMPAIGN,a.executable.resolve()),indent=2))
