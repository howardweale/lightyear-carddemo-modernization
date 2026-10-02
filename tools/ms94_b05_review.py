"""B05 r2: signed operator decisions between completed, unrepeated trial slots."""
import json,time
from datetime import datetime,timezone
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,require
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_signer_v5 import JourneySigner
from tools.ms94_b05_stops import repeated,verify_causes,signal_review

REVIEW='Operator review; not independent'

def signed(path,key):
    value=read_json(path);require(verify_envelope(value,key),'Invalid operator-review evidence: '+path.name)
    return value

def review_reasons(trial_directory,status,current,prior):
    matches=repeated(current,prior,trial_directory)
    reasons=[]
    if status=='halted-equipment-suspect':reasons.append('equipment-suspect')
    if matches:reasons.append('repeated-cause-across-trials')
    return reasons,matches

def prior_summaries(root,campaign,key):
    from tools.ms94_b05_admission import CONFIG
    slots=read_json(root/CONFIG/'campaign.json')['slots'];name=campaign.relative_to(root).as_posix()
    index=next(i for i,s in enumerate(slots) if s['path']==name)
    records=[];refs=[]
    for slot in slots[:index]:
        folder=root/slot['path'];p=folder/'trial-review.json'
        value=signed(p,key);receipt=signed(folder/'receipt.json',key)
        require(value['trial_directory']==slot['path'] and value['receipt_sha256']==receipt['content_sha256'], 'Prior trial review binding differs')
        require(receipt['plan_sha256']==slot['plan_sha256'],'Prior trial plan differs')
        require(value['snapshot_sha256']==read_json(root/'execution-snapshot.json')['content_sha256'],'Prior review snapshot differs')
        records.append(value);refs.append({'path':p.relative_to(root).as_posix(),'sha256':value['content_sha256']})
    return records,refs

def trial_fingerprints(root,campaign,key):
    verify_causes(root,campaign,key)
    # Union across attempts: never a counter of attempts or engine lanes.
    return sorted({f for p in campaign.glob('cause-*.json') for f in signed(p,key)['fingerprints']})

def summarize_trial(root,campaign,result):
    signer=JourneySigner(root);current=trial_fingerprints(root,campaign,signer.public)
    prior,refs=prior_summaries(root,campaign,signer.public);name=campaign.relative_to(root).as_posix()
    reasons,matches=review_reasons(name,result['status'],current,prior)
    value=signer.sign({'artifact_type':'b05-r2-trial-review','trial_directory':name,
        'snapshot_sha256':read_json(root/'execution-snapshot.json')['content_sha256'],
        'receipt_sha256':result['content_sha256'],'fingerprints':current,'prior_trial_records':refs,
        'matching_prior_fingerprints':matches,'reasons':reasons,'review_required':bool(reasons),
        'verdict_changed':False,'review':REVIEW})
    with (campaign/'trial-review.json').open('xb') as f:f.write(canonical(value))
    if reasons:signal_review(root,campaign,','.join(reasons))
    return value

def verify_trial_review(root,campaign,key):
    value=signed(campaign/'trial-review.json',key);receipt=signed(campaign/'receipt.json',key)
    name=campaign.relative_to(root).as_posix()
    require(value['trial_directory']==name and value['receipt_sha256']==receipt['content_sha256'],'Trial review receipt differs')
    require(value['snapshot_sha256']==read_json(root/'execution-snapshot.json')['content_sha256'],'Review snapshot differs')
    current=trial_fingerprints(root,campaign,key);prior,refs=prior_summaries(root,campaign,key)
    reasons,matches=review_reasons(name,receipt['status'],current,prior)
    require(value['fingerprints']==current and value['prior_trial_records']==refs and value['reasons']==reasons
        and value['matching_prior_fingerprints']==matches and value['review_required']==bool(reasons)
        and value['verdict_changed'] is False,'Trial review cannot be independently reproduced')
    return value

def validate_decision(value,pause,key):
    require(verify_envelope(value,key),'Operator decision signature invalid')
    require(value.get('artifact_type')=='b05-r2-operator-decision','Wrong decision type')
    for field in ('snapshot_sha256','campaign_plan_sha256','amendment_sha256','trial_directory','trial_receipt_sha256'):
        require(value.get(field)==pause[field],'Operator decision binding differs: '+field)
    require(value.get('pause_sha256')==pause['content_sha256'],'Decision belongs to another pause')
    require(value.get('action') in ('continue','stop','void'),'Unsupported operator action')
    require(isinstance(value.get('reason'),str) and value['reason'].strip(),'An operator reason is required')
    require(value.get('operator')=='Howard Weale' and value.get('operator_approval') and value.get('review')==REVIEW,'Missing explicit operator review')
    require(value.get('verdict_changed') is False,'Operator decision cannot change a verdict')
    at=datetime.fromisoformat(value['issued_at_utc']);created=datetime.fromisoformat(pause['created_at_utc'])
    require(at.tzinfo is not None and created<=at<=datetime.now(timezone.utc),'Decision timestamp outside this pause')
    return value['action']

def wait_for_review(root,campaign,campaign_started,maximum_seconds):
    from tools.ms94_b05_admission import CAMPAIGN,CONFIG,APPROVED,bindings
    from tools.ms94_b05_plan import period_guard
    signer=JourneySigner(root);review=verify_trial_review(root,campaign,signer.public)
    if not review['review_required']:return None
    output=root/CAMPAIGN;folder=output/'reviews'/campaign.name;folder.mkdir(parents=True,exist_ok=False)
    original=signed(campaign/'receipt.json',signer.public)
    pause=signer.sign({'artifact_type':'b05-r2-review-pause',
        'snapshot_sha256':read_json(root/'execution-snapshot.json')['content_sha256'],
        'campaign_plan_sha256':read_json(root/CONFIG/'campaign.json')['content_sha256'],
        'amendment_sha256':read_json(root/APPROVED/'amendment-r2/amendment.json')['content_sha256'],
        'trial_directory':campaign.relative_to(root).as_posix(),'trial_receipt_sha256':original['content_sha256'],
        'trial_review_sha256':review['content_sha256'],'reasons':review['reasons'],
        'supervision_receipt_sha256':signed(campaign/'supervision-receipt.json',signer.public)['content_sha256'],
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'review':REVIEW,
        'waiting_counts_against_campaign_seconds':True,'verdict_changed':False})
    save(folder/'pause.json',pause)
    save(output/'review-active.json',signer.sign({'pause_path':(folder/'pause.json').relative_to(root).as_posix(),
        'pause_sha256':pause['content_sha256']}))
    print(json.dumps({'event':'campaign-paused-for-operator','pause_sha256':pause['content_sha256'],
        'decision_path':str(folder/'decision.json'),'reasons':review['reasons']}),flush=True)
    started=time.monotonic()
    while True:
        period_guard(datetime.now(timezone.utc))
        require(time.monotonic()-campaign_started<maximum_seconds,'Campaign deadline reached while awaiting operator')
        require(not (output/'stopping.json').exists(),'Hard stop cannot be overridden by operator continue')
        if (folder/'decision.json').exists():
            decision=read_json(folder/'decision.json');action=validate_decision(decision,pause,signer.public)
            bindings(root,True)
            require(read_json(campaign/'receipt.json')==original,'Trial verdict changed while paused')
            resolution=signer.sign({'artifact_type':'b05-r2-review-resolution','pause_sha256':pause['content_sha256'],
                'decision_sha256':decision['content_sha256'],'action':action,'reason':decision['reason'],
                'waiting_seconds':time.monotonic()-started,'verdict_changed':False,'review':REVIEW})
            save(folder/'resolution.json',resolution)
            print(json.dumps({'event':'operator-review-decided','action':action,'pause_sha256':pause['content_sha256']}),flush=True)
            return resolution
        time.sleep(5)

def require_review_clear(root):
    from tools.ms94_b05_admission import CAMPAIGN,CONFIG,APPROVED
    path=root/CAMPAIGN/'review-active.json'
    if not path.exists():return
    key=(root/'work/ms87/operator/authority.public.pem').read_bytes();active=signed(path,key)
    pause_path=root/active['pause_path']
    require(pause_path.resolve().is_relative_to((root/CAMPAIGN/'reviews').resolve()),'Review path escaped campaign')
    pause=signed(pause_path,key);require(pause['content_sha256']==active['pause_sha256'],'Active pause changed')
    require(pause['snapshot_sha256']==read_json(root/'execution-snapshot.json')['content_sha256']
        and pause['campaign_plan_sha256']==read_json(root/CONFIG/'campaign.json')['content_sha256']
        and pause['amendment_sha256']==read_json(root/APPROVED/'amendment-r2/amendment.json')['content_sha256'],'Review campaign binding differs')
    decision=signed(pause_path.parent/'decision.json',key)
    action=validate_decision(decision,pause,key);resolution=signed(pause_path.parent/'resolution.json',key)
    require(action=='continue' and resolution['action']==action and resolution['pause_sha256']==pause['content_sha256']
        and resolution['decision_sha256']==decision['content_sha256'],'Next slot is not authorized by a signed continue decision')
    require(signed(root/pause['trial_directory']/'receipt.json',key)['content_sha256']==pause['trial_receipt_sha256'],'Reviewed verdict changed')

def write_decision(root,pause_path,action,reason,operator_approval):
    """Host-only helper. Call only after explicit user approval of this exact decision."""
    from tools.ms94_b05_admission import CAMPAIGN
    require(pause_path.resolve().is_relative_to((root/CAMPAIGN/'reviews').resolve()),'Unexpected pause path')
    signer=JourneySigner(root);pause=signed(pause_path,signer.public)
    value=signer.sign({'artifact_type':'b05-r2-operator-decision',
        **{k:pause[k] for k in ('snapshot_sha256','campaign_plan_sha256','amendment_sha256','trial_directory','trial_receipt_sha256')},
        'pause_sha256':pause['content_sha256'],'action':action,'reason':reason,'operator':'Howard Weale',
        'operator_approval':operator_approval,'issued_at_utc':datetime.now(timezone.utc).isoformat(),
        'verdict_changed':False,'review':REVIEW})
    validate_decision(value,pause,signer.public)
    target=pause_path.parent/'decision.json';pending=pause_path.parent/'decision.pending'
    require(not target.exists() and not pending.exists(),'Operator decision already exists')
    with pending.open('xb') as f:f.write(canonical(value))
    require(not target.exists(),'Operator decision appeared concurrently');pending.rename(target)
    return value
