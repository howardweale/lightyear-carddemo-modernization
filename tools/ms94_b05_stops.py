"""Prospective B05 r2 hard stops and per-trial review evidence; these records never become builder feedback."""
import hashlib,json
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,require
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_signer_v5 import JourneySigner

IMMEDIATE=frozenset(('void-equipment-failure','invalid-provenance',
    'halted-controller-failure','halted-trial-deadline'))

def fingerprints(gate,diagnostics):
    """Origin is not causation. Matching unresolved failures request review between trials."""
    values=[]
    for d in diagnostics:
        if d.get('category')=='candidate-runtime-exception' and d.get('thrown_by')!='candidate':
            values.append({'kind':'non-candidate-origin-causality-unresolved',
                'diagnostic':{k:v for k,v in d.items() if k not in ('id','line','lanes')}})
    if gate['status']=='business-failure':
        if gate.get('error'):
            values.append({'kind':'business-causality-unresolved','error':gate['error']})
        else:
            # A full closed check is retained; private values are never sent to a model.
            def walk(node,path):
                if isinstance(node,dict):
                    if node.get('passed') is False:
                        values.append({'kind':'business-causality-unresolved','check':path,
                            'reason':{k:v for k,v in node.items() if k in ('error','reason','message','divergent_fields')}})
                    for k,v in node.items():
                        if isinstance(v,dict):walk(v,path+'/'+k)
            walk(gate.get('checks',{}),'checks')
            if not values:values.append({'kind':'business-causality-unresolved','check':'unresolved-business-failure'})
    return sorted(set(hashlib.sha256(canonical(v)).hexdigest() for v in values))

def repeated(current,prior,trial_directory):
    # Each fingerprint contributes once per trial; attempts never match themselves.
    return sorted(set(current)&{f for r in prior if r['trial_directory']!=trial_directory for f in r['fingerprints']})

def notify(root,campaign,status,details=None):
    signer=JourneySigner(root)
    value=signer.sign({'status':status,'notify_immediately':True,'details':details,
        'review':'Operator review; not independent','next_slot_forbidden':True})
    save(campaign/'stopping.json',value)
    from tools.ms94_b05_admission import CAMPAIGN,PREFLIGHT
    if campaign!=root/PREFLIGHT:save(root/CAMPAIGN/'stopping.json',value)
    print(json.dumps({'event':'campaign-stopping','status':status,'notify_immediately':True}),flush=True)
    return value

def signal_review(root,campaign,reason):
    path=campaign/'review-needed.json';signer=JourneySigner(root)
    if path.exists():
        require(verify_envelope(read_json(path),signer.public),'Invalid pending review signal')
        return
    save(path,signer.sign({'reason':reason,'notify_immediately':True,
        'pause_after_trial_finalization':True,'verdict_changed':False,
        'review':'Operator review; not independent'}))
    print(json.dumps({'event':'operator-review-needed','reason':reason,'next_slot_requires_decision':True}),flush=True)


def record_failure(root,campaign,run,gate,diagnostics):
    signer=JourneySigner(root)
    value=signer.sign({'trial_directory':campaign.relative_to(root).as_posix(),
        'run_directory':run.relative_to(root).as_posix(),'gate_sha256':gate['content_sha256'],
        'fingerprints':fingerprints(gate,diagnostics),
        'classification':'unresolved; matching origin/check is not proof of non-candidate causation',
        'review':'Operator review; not independent'})
    path=campaign/('cause-'+run.name+'.json');require(not path.exists(),'Cause record already exists')
    save(path,value)
    # Collection does not halt a repair or alter any attempt/trial verdict.


def verify_causes(root,campaign,key):
    for p in campaign.glob('cause-*.json'):
        value=read_json(p);require(verify_envelope(value,key),'Invalid cause signature')
        require(value['trial_directory']==campaign.relative_to(root).as_posix(),'Cause belongs to another trial')
        run=root/value['run_directory'];gate=read_json(run/'gate.json')
        projected=read_json(run/'diagnostic-projection.json')
        require(value['gate_sha256']==gate['content_sha256'] and value['fingerprints']==fingerprints(gate,projected['diagnostics']),'Cause fingerprints differ')
