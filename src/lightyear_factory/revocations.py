"""Authority-side revocation export. No proposal may grant annotation trust."""
import os
import json
from pathlib import Path
from datetime import datetime,timezone,date,timedelta
from lightyear_control_tower.decisions import canonical,digest,ZERO
from .annotations import outcome_summary


def binding(ledger):
    return dict(public_key_pem=ledger.ledger_key.decode(),channel=digest(dict(
        key=ledger.ledger_key.decode(),scope=ledger.scope,inventory=ledger.inventory_sha256)))


def replace(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp-'+os.urandom(8).hex())
    with temporary.open('xb') as f:
        f.write(canonical(value));f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)


def validity(now=None):
    issued=now or datetime.now(timezone.utc)
    return dict(issued_at=issued.isoformat(),valid_until=(issued+timedelta(minutes=15)).isoformat())


def subscriptions_for(ledger,events=None):
    events=ledger.events() if events is None else events
    expected=[]
    for event in events:
        if event['event']=='revocation-subscription' and event['payload'] not in expected:
            expected.append(event['payload'])
    registry=ledger.path.with_suffix('.revocation-subscriptions.json')
    actual=json.loads(registry.read_bytes()) if registry.exists() else []
    if actual != expected:raise ValueError('bound projection subscription missing or changed')
    return expected


def publish(ledger,signer,subscriptions,*,now=None):
    events=ledger.events();states=ledger.replay(events);today=(now or datetime.now(timezone.utc)).date()
    if subscriptions!=subscriptions_for(ledger,events):raise ValueError('subscription binding')
    common=dict(**validity(now),channel=binding(ledger)['channel'],sequence=len(events),
                ledger_head=events[-1]['content_sha256'] if events else ZERO)
    # Publish each head first: an interrupted list update refuses guidance.
    for subscription in subscriptions:
        directory=Path(subscription['directory'])
        replace(directory/'head.json',signer.sign(dict(schema='annotation-live-head/1',**common)))
        revoked=[]
        for name in subscription['annotation_ids']:
            s=states.get(name)
            if (not s or s['status'] not in {'approved','proposed'} or outcome_summary(s)['flagged'] or
                    date.fromisoformat(s.get('review_after',s['annotation']['review_after']))<=today):revoked.append(name)
        replace(directory/'revocations.json',signer.sign(dict(schema='annotation-revocations/1',**common,
            projection_sha256=subscription['projection_sha256'],revoked=sorted(revoked))))


def subscribe(ledger,signer,projection_directory):
    """Operator setup after projection creation; cannot approve the projection."""
    import gzip
    directory=Path(projection_directory).resolve()
    raw=(directory/'projection.json.gz').read_bytes()
    projection=json.loads(gzip.decompress(raw))
    if projection.get('revocation_binding')!=binding(ledger) or signer.public!=ledger.ledger_key:
        raise ValueError('revocation-authority-binding')
    import hashlib
    item=dict(directory=str(directory/'revocations'),projection_sha256=hashlib.sha256(raw).hexdigest(),
              annotation_ids=sorted(a['id'] for a in projection.get('annotations',[])))
    ledger.append('revocation-subscription',item,signer)
    return item


def refresh(ledger,signer,*,now=None):
    """Authority heartbeat: publish a fresh validity window without a ledger edit.

    Operators schedule this at less than 15 minutes (recommended five). Missing
    subscription state refuses; offline authorities cause readers to fail closed.
    """
    if signer.public!=ledger.ledger_key:raise ValueError('revocation authority')
    return publish(ledger,signer,subscriptions_for(ledger),now=now)
