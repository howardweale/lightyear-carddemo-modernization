"""Reproducible no-call amendments. Historical plans remain unchanged."""
import copy
import hashlib
import json
from pathlib import Path
from lightyear_control_tower.decisions import digest
from lightyear_mainframe.zos_bindings import ROOT

DIRECTORY=ROOT/'docs/factory/posttran-second-opinion'
BASE='97b105a5f9e1c26b378be927b7fc74e947a051a6ef0c49f03b5ac4ddcfa1d95e'

def amended_plan():
    old=json.loads((DIRECTORY/'revised-plan.json').read_bytes())
    if old['content_sha256']!=BASE or digest({k:v for k,v in old.items() if k!='content_sha256'})!=BASE:
        raise ValueError('unexpected-base-plan')
    plan=copy.deepcopy(old);plan.pop('content_sha256')
    plan.update(schema='posttran-independent-preregistration/3',status='approved-subject-to-amendments-awaiting-exact-go',
        supersedes_plan_sha256=BASE,result_label='independent model-built candidate',
        go_requirement='go POSTTRAN <this content_sha256>',execution_authorized=False,
        amendment_authority='Howard 2026-10-11 14:00 PDT A4; exact go still required')
    plan['dispatch']['broker_sha256']=hashlib.sha256((ROOT/plan['dispatch']['broker']).read_bytes()).hexdigest()
    plan['dispatch']['approval_verifier_sha256']=hashlib.sha256((ROOT/'src/lightyear_factory/posttran_preflight.py').read_text().encode()).hexdigest()
    plan['dispatch']['preflight_evidence']={'required_before_every_generation':True,'endpoint':'/v1/responses/input_tokens','generation':False,
        'exact_fields':['model','input','reasoning'],'ledger':'same fixed plan-bound reservation ledger',
        'recorded':['request digest','each public packet file hash','count and response digest','failure type','timestamps'],
        'failure_consumes_reserved_attempt':True}
    plan['live_dispatch_status']='Blocked until Howard supplies go POSTTRAN <this exact hash>. Phase2 remains unapproved. No live request made.'
    plan['content_sha256']=digest(plan)
    return plan

def differences(before,after,path=''):
    rows=[]
    for key in sorted(set(before)|set(after)):
        p=path+'/'+key
        if key not in before or key not in after:rows.append({'path':p,'before':before.get(key),'after':after.get(key)})
        elif isinstance(before[key],dict) and isinstance(after[key],dict):rows.extend(differences(before[key],after[key],p))
        elif before[key]!=after[key]:rows.append({'path':p,'before':before[key],'after':after[key]})
    return rows

if __name__=='__main__':
    old=json.loads((DIRECTORY/'revised-plan.json').read_bytes());new=amended_plan()
    # Only A4 labels, preflight ledger, exact-go guards and their provenance change.
    assert new['phases']==old['phases'] and new['inputs']==old['inputs'] and new['prompts']==old['prompts']
    (DIRECTORY/'amended-plan-2026-10-11.json').write_text(json.dumps(new,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    diff={'schema':'posttran-plan-amendment/1','before':BASE,'after':new['content_sha256'],'changes':differences(old,new),'unchanged':['budgets','model','reasoning','service tier','inputs','prompts','Phase2 gate'],'api_requests':0}
    diff['content_sha256']=digest(diff)
    (DIRECTORY/'amendment-2026-10-11.json').write_text(json.dumps(diff,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    print(new['content_sha256'])
