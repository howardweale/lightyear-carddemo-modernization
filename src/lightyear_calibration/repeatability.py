"""Predeclared repeated trials with complete denominators and no outcome stopping."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import time

from .contracts import canonical,read_json,require,seal,verify
from .journey_runtime import JourneySigner
from .journey_order import save,file_hash
from lightyear_control_tower.decisions import verify_envelope
from . import measured_campaign as trial

VARIANTS=('baseline','procure-to-pay','without-decimal','without-boolean')
AREA=Path('factory/idempiere/repeatability')


def wilson(successes,total):
    require(type(total) is int and type(successes) is int and 0<=successes<=total,'Invalid rate counts')
    if total==0:return None
    z=1.959963984540054;p=successes/total;denom=1+z*z/total
    centre=(p+z*z/(2*total))/denom
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denom
    return [max(0,centre-half),min(1,centre+half)]


def schedule(variants,per_variant,seed):
    require(variants and len(set(variants))==len(variants) and set(variants)<=set(VARIANTS),'Unknown or duplicate variant')
    require(type(per_variant) is int and 1<=per_variant<=10,'At most ten declared trials per variant')
    rng=random.Random(seed);result=[]
    for round_number in range(1,per_variant+1):
        block=list(variants);rng.shuffle(block)
        for variant in block:result.append({'slot':len(result)+1,'variant':variant,'replicate':round_number})
    return result


def outcome(receipt):
    attempts=receipt['attempts'];cost=receipt['cost'];calls=cost.get('attempted_client_invocations')
    passed=receipt['combined_gate_passed'] is True
    repaired=len(attempts)>1
    label='first-try-pass' if passed and len(attempts)==1 and calls==1 else 'pass-after-repair' if passed else 'halt'
    return {'outcome':label,'status':receipt['status'],'passed':passed,
            'native_attempts':len(attempts),'repair_candidates':max(0,len(attempts)-1),
            'calls':calls,'cost':cost,'provenance':receipt['provenance'],
            'receipt_sha256':receipt['content_sha256']}


def rates(rows,planned):
    started=[r for r in rows if r['outcome']!='not-started'];counts=Counter(r['outcome'] for r in started)
    n=len(started);first=counts['first-try-pass'];repaired=counts['pass-after-repair']
    return {'planned':planned,'started':n,'not_started':planned-n,'first_try_passes':first,
            'passes_after_repair':repaired,'halts':counts['halt'],'invalid':counts['invalid'],
            'first_try_rate':first/n if n else None,'eventual_pass_rate':(first+repaired)/n if n else None,
            'first_try_wilson_95':wilson(first,n),'eventual_pass_wilson_95':wilson(first+repaired,n),
            'first_try_passes_over_all_planned':[first,planned],
            'complete_fixed_sample':n==planned,
            'interval_scope':'Descriptive Wilson interval under a binomial working model; small samples and provider drift limit generalization.'}


def frozen(root,cohort):
    p=read_json(cohort/'plan.json');verify(p);key=JourneySigner(root).public
    declaration=read_json(cohort/'declaration.json')
    require(verify_envelope(declaration,key) and declaration['plan_sha256']==p['content_sha256'],'Cohort declaration changed')
    for variant,identity in p['variant_plans'].items():
        actual=trial.frozen(root,cohort/'templates'/variant)
        require(actual['content_sha256']==identity,'Variant declaration changed')
    return p


def prepare(root,cohort,executable,qualification,variants=VARIANTS,per_variant=10,max_calls=5,seed=20260927):
    require(not cohort.exists() and cohort.resolve().is_relative_to(root.resolve()),'Use a new cohort folder')
    require(max_calls in (3,5),'Use an odd call budget with complete analyst/builder cycles')
    key=JourneySigner(root).public;q=read_json(qualification/'receipt.json')
    require(verify_envelope(q,key) and q['passed'] and q['cleanup_complete'],'Native observer qualification must pass before declaration')
    for name in ('transaction_observer.py','observer_runtime.py','observer_probe.py'):
        require(file_hash(root/'src/lightyear_calibration'/name)==file_hash(qualification/'qualification-source'/name),'Observer changed since qualification')
    cohort.mkdir(parents=True);templates=cohort/'templates';templates.mkdir();plans={}
    for variant in variants:
        value=trial.prepare(root,templates/variant,executable,max_calls,variant);plans[variant]=value['content_sha256']
    ordered=schedule(variants,per_variant,seed)
    p=seal({'artifact_type':'lightyear-factory-rate-declaration','version':'factory-rates-v1',
        'variant_plans':plans,'schedule':ordered,'schedule_seed':seed,'runs_per_variant':per_variant,
        'planned_trials':len(ordered),'maximum_client_calls':len(ordered)*max_calls,
        'maximum_active_seconds':len(ordered)*3600,'per_trial_maximum_calls':max_calls,
        'per_trial_maximum_seconds':3600,'qualification_directory':qualification.relative_to(root).as_posix(),
        'qualification_receipt_sha256':q['content_sha256'],
        'stopping_rule':{'normal':'Complete every prespecified trial, regardless of passes or business/repair halts.',
            'early':['frozen-identity-drift','incomplete-cleanup','invalid-observer-capture','invalid-provenance','cohort-active-budget-exhausted','explicit-operator-cancellation'],
            'no_success_or_futility_stopping':True,'unstarted_slots':'Publish every remaining slot as not-started with the stop reason.',
            'no_replacement_of_failed_trials':True,'no_mid_campaign_budget_or_controller_changes':True},
        'fresh_generation':'Every trial starts an ephemeral builder session with its same variant input and empty candidate; no previous-trial output is included.',
        'transfer':'Initial variant source/API payloads, generated candidates and allowlisted structural diagnostics only.',
        'organization_api_migration':'deferred-by-user','cloud_resources':False,'billing_usd':None,
        'first_try_means':'First candidate after the documented inherited input lessons.',
        'no_foundation_model_unfamiliarity_claim':True})
    save(cohort/'plan.json',p)
    save(cohort/'declaration.json',JourneySigner(root).sign({'plan_sha256':p['content_sha256'],'execution_authorized':False}))
    return p


def authorize(root,cohort,expected,approval):
    p=frozen(root,cohort);require(expected==p['content_sha256'] and approval.strip(),'Exact cohort approval required')
    require(not (cohort/'authorization.json').exists() and not (cohort/'started.json').exists(),'Cohort already authorized or started')
    a=JourneySigner(root).sign({'artifact_type':'factory-rate-authorization','plan_sha256':expected,
                               'operator_approval':approval,'maximum_client_calls':p['maximum_client_calls']})
    save(cohort/'authorization.json',a);return a


def cancel(root,cohort,reason):
    """Stop before the next trial; an active bounded trial finishes and cleans up."""
    p=read_json(cohort/'plan.json');verify(p);require(reason.strip(),'Cancellation reason required')
    result=JourneySigner(root).sign({'artifact_type':'factory-rate-cancellation',
        'plan_sha256':p['content_sha256'],'reason':reason,
        'effective':'Before the next trial; the active trial completes within its frozen budget.'})
    save(cohort/'cancel.json',result);return result


def report(root,cohort,stop_reason=None):
    p=read_json(cohort/'plan.json');verify(p);key=JourneySigner(root).public;all_rows=[]
    for slot in p['schedule']:
        folder=cohort/'trials'/f"{slot['slot']:03d}-{slot['variant']}";path=folder/'receipt.json'
        if path.exists():
            r=read_json(path)
            if not verify_envelope(r,key) or r.get('plan_sha256')!=p['variant_plans'][slot['variant']]:
                all_rows.append({**slot,'outcome':'invalid','status':'untrusted-or-wrong-plan-receipt','observed_file_sha256':file_hash(path)})
                continue
            value=outcome(r)
            if not r['provenance'].get('verified') or not r['cost'].get('accounting_complete'):value['outcome']='invalid'
            all_rows.append({**slot,**value,'trial_directory':folder.relative_to(root).as_posix(),
                             'publication':(cohort/'publications'/folder.name).relative_to(root).as_posix() if (cohort/'publications'/folder.name/'receipt.json').exists() else None})
        elif (folder/'started.json').exists():
            all_rows.append({**slot,'outcome':'invalid','status':'started-without-terminal-receipt','trial_directory':folder.relative_to(root).as_posix()})
        else:all_rows.append({**slot,'outcome':'not-started','reason':stop_reason or 'pending-authorization-or-execution'})
    result=JourneySigner(root).sign({'artifact_type':'lightyear-factory-rate-report','plan_sha256':p['content_sha256'],
        'stop_reason':stop_reason,'outcomes':all_rows,
        'rates':{v:rates([r for r in all_rows if r['variant']==v],p['runs_per_variant']) for v in p['variant_plans']},
        'no_cross_variant_pooling':True,'every_planned_slot_published':True,
        'billing_usd':None,'platform_qualification':False})
    save(cohort/'report.json',result);return result


def run(root,cohort,executable):
    p=frozen(root,cohort);signer=JourneySigner(root);auth=read_json(cohort/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['plan_sha256']==p['content_sha256'],'Exact cohort authorization missing')
    with (cohort/'started.json').open('xb') as stream:stream.write(canonical({'plan_sha256':p['content_sha256']}))
    began=time.monotonic();stop=None
    try:
        for slot in p['schedule']:
            frozen(root,cohort)
            require(time.monotonic()-began<p['maximum_active_seconds'],'cohort-active-budget-exhausted')
            cancel=cohort/'cancel.json'
            if cancel.exists():
                c=read_json(cancel);require(verify_envelope(c,signer.public) and c['plan_sha256']==p['content_sha256'],'Unsigned cancellation')
                stop='explicit-operator-cancellation';break
            folder=cohort/'trials'/f"{slot['slot']:03d}-{slot['variant']}";folder.mkdir(parents=True,exist_ok=False)
            for name in ('plan.json','declaration.json'):shutil.copyfile(cohort/'templates'/slot['variant']/name,folder/name)
            trial.authorize(root,folder,p['variant_plans'][slot['variant']], 'Approved by exact frozen cohort '+auth['content_sha256'])
            r=trial.run(root,folder,executable,
                        remaining_seconds=p['maximum_active_seconds']-(time.monotonic()-began))
            report(root,cohort)
            from tools.publish_measured_campaign import publish
            publish(root,folder,cohort/'publications'/folder.name)
            require(r['provenance']['verified'] and r['cost']['accounting_complete'],'invalid-provenance')
            for attempt in r['attempts']:
                native=root/attempt['run_directory'];require(read_json(native/'cleanup.json')['complete'],'incomplete-cleanup')
                require(read_json(native/'receipt.json').get('observer_capture_integrity') is True,'invalid-observer-capture')
                from .transaction_observer import verify_capture
                for observation in native.glob('cases/operations/*/observers/*'):
                    verify_capture(observation)  # Missing witnesses are a halt; a broken capture stops the cohort.
    except BaseException as exc:
        stop=type(exc).__name__+': '+str(exc)
    finally:result=report(root,cohort,stop)
    return result


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','authorize','run','report','cancel'))
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--executable',type=Path);p.add_argument('--qualification',type=Path)
    p.add_argument('--variant',action='append',choices=VARIANTS);p.add_argument('--runs-per-variant',type=int,default=10)
    p.add_argument('--max-calls',type=int,default=5);p.add_argument('--plan-sha256');p.add_argument('--approval');p.add_argument('--reason');a=p.parse_args()
    root=a.root.resolve();cohort=a.cohort.resolve()
    if a.command=='prepare':r=prepare(root,cohort,a.executable.resolve(),a.qualification.resolve(),a.variant or VARIANTS,a.runs_per_variant,a.max_calls)
    elif a.command=='authorize':r=authorize(root,cohort,a.plan_sha256,a.approval or '')
    elif a.command=='run':r=run(root,cohort,a.executable.resolve())
    elif a.command=='cancel':r=cancel(root,cohort,a.reason or '')
    else:r=report(root,cohort)
    print(json.dumps(r,indent=2))


if __name__=='__main__':main()
