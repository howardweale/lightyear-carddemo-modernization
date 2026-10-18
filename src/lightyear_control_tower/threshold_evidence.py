"""Typed condition evidence. Hash binding alone is not proof of a condition."""
from hashlib import sha256
import json

from .requests import confined, read_bytes

TYPE_ERROR = 'threshold-condition-evidence-type'


def require(ok):
    if not ok: raise ValueError(TYPE_ERROR)


def typed(condition, raw, contract, evidence):
    from .threshold_conditions import CONDITIONS
    try:
        value = json.loads(raw)
        require(isinstance(value, dict))
        index = [sha256(x.encode()).hexdigest() for x in CONDITIONS].index(condition)
        if index == 0:
            require(value.get('schema') == 'factory-legacy-twin/1' and value.get('phase') == 'B1-equivalence-followup')
            require(value.get('job') == contract['program'])
            require(value.get('current_head') == contract['details'].get('evidence_head'))
            counts = value.get('counts')
            require(isinstance(counts, dict) and bool(counts) and all(type(n) is int and n >= 0 for n in counts.values()))
            require(sum(counts.values()) == value.get('population') and value['population'] > 0)
            require(type(value.get('target_cases')) is int and value['target_cases'] >= 0)
            require(value.get('target_valid_comparisons') == value['target_cases'] and value.get('target_evidence_gap_ids') == [])
            require(value.get('fresh_sites') == value.get('expected_sites') and value.get('fresh_sites',0) > 0)
        elif index == 1:
            require(value.get('schema') == 'threshold-equivalence-reviews/1')
            require(value.get('program') == contract['program'] and value.get('evidence_head') == contract['details'].get('evidence_head'))
            require(value.get('claim_scope') in ('twin','zos-facing'))
            ids = value.get('required_ids')
            require(isinstance(ids,list) and bool(ids) and all(isinstance(i,str) and i for i in ids) and len(set(ids)) == len(ids))
            require(isinstance(value.get('proofs'),list) and bool(value['proofs']))
            covered = set()
            from lightyear_factory.tower_authority import proof_contract
            for proof in value['proofs']:
                c = proof_contract(proof)
                require(c.get('kind') == 'equivalence-review' and c.get('program') == contract['program'])
                require(c['details']['claim_scope'] == value['claim_scope'])
                event = next(e for e in proof['journal']['events'] if e['content_sha256'] == proof['decision_sha256'])
                require(event['payload']['outcome'] == 'accept')
                for item in c['details']['items']:
                    require(event['payload']['validation']['items'][item]['outcome'] == 'accept')
                    covered.add(item)
            expected = contract['details'].get('required_review_ids')
            require(isinstance(expected,list) and bool(expected) and len(set(expected))==len(expected))
            require(set(ids) == set(expected) == covered)
        elif index == 2:
            require(value.get('schema') in ('release-evidence-index/1','release-evidence-index/2'))
            require(value.get('conclusion') == 'success' and value.get('head') == contract['details'].get('evidence_head'))
            require(type(value.get('run_id')) is int and value['run_id'] > 0 and bool(value.get('sources')))
            require(all(row.get('head') == value['head'] and row.get('run_id') == value['run_id'] for row in value['sources']))
        else:
            require(evidence['path'] == 'docs/factory/keep-or-fix-register.json')
            require(value.get('schema') == 'factory-keep-or-fix-register/1')
            require(isinstance(value.get('defects'),list) and bool(value['defects']))
            ids = [row['id'] for row in value['defects']]
            require(len(set(ids)) == len(ids) and all(isinstance(i,str) and i for i in ids))
        return value
    except (KeyError, TypeError, ValueError, StopIteration) as error:
        raise ValueError(TYPE_ERROR) from error


def verify_reviews(contract, root, *, events=None, authority=None, journal=None):
    """Trust is supplied by the signing service or consuming authority, never the packet.

    At signing, each nested decision must equal an event in the already verified
    service journal. At consumption, reverify it against the externally trusted
    current journal so a later revocation/invalidation cannot be hidden.
    """
    from .threshold_conditions import CONDITIONS, REPOSITORY
    from lightyear_factory.tower_authority import proof_contract
    fingerprint=sha256(CONDITIONS[1].encode()).hexdigest()
    row=next((r for r in contract['details'].get('conditions',[]) if r['condition_sha256']==fingerprint and r['state']=='met'),None)
    if row is None: return
    evidence=row['evidence']; raw=read_bytes(confined(root or REPOSITORY,evidence['path']))
    require(sha256(raw).hexdigest()==evidence['sha256'])
    bundle=typed(fingerprint,raw,contract,evidence)
    for proof in bundle['proofs']:
        if authority is not None:
            refreshed=dict(proof,journal=journal)
            c=proof_contract(refreshed)
            authority.verify(refreshed,'equivalence-review',c,('accept',))
        else:
            nested=next(e for e in proof['journal']['events'] if e['content_sha256']==proof['decision_sha256'])
            require(events is not None and nested in events)
            c=proof_contract(proof)
            # Reject subsequent replacement or register invalidation before signing.
            for event in events:
                p=event.get('payload',{})
                if event['sequence'] <= nested['sequence']: continue
                if p.get('kind')=='equivalence-review' and p.get('bound')==nested['payload'].get('bound'):
                    require(False)
                if p.get('kind')=='legacy-behaviour-disposition' and p.get('outcome')=='fix':
                    require(p.get('validation',{}).get('contract',{}).get('details',{}).get('entry_id') not in c['details']['dependencies'])
