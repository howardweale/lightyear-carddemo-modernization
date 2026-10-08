"""Offline migration proposals; never transfer legacy approval or outcome authority."""
import json
from lightyear_control_tower.decisions import verify_envelope, ZERO, digest
from .annotations import annotation

def propose(raw, public_key):
    if raw and not raw.endswith(b'\n'):raise ValueError('legacy-ledger-incomplete')
    previous=ZERO;proposals=[];seen=set()
    for sequence,line in enumerate(raw.splitlines(),1):
        event=json.loads(line)
        if (not verify_envelope(event,public_key) or event.get('sequence')!=sequence
            or event.get('previous_sha256')!=previous):raise ValueError('legacy-signature-or-chain')
        previous=event['content_sha256']
        if event.get('event')!='create':continue
        original=event['payload']['annotation'];item=dict(original)
        item.update(provenance='inferred',portable=False)
        item=annotation(item)
        if item['id'] in seen:raise ValueError('legacy-duplicate-annotation')
        seen.add(item['id']);proposals.append(item)
    return dict(schema='annotation-migration-proposals/1',legacy_sha256=__import__('hashlib').sha256(raw).hexdigest(),
        legacy_head=previous,proposals=proposals,approval_transferred=False,outcomes_transferred=False,
        required='fresh leak checks, named owner and Tower decisions before guidance',model_calls=0)
