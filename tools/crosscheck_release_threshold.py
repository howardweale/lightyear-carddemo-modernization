"""Independent receipt-to-denominator arithmetic; does not call the Tower assessor."""
import argparse
import json
from pathlib import Path


# Independent overlay parsing and claim checks. No engine scope functions are
# imported: a parser/selection defect must be visible to this cross-check.
from hashlib import sha256
import re
ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_OVERLAYS = frozenset({'3f5f5f84f68d5410bc0070f75e4d3e9b471a3d853233b9658153d4fe76228f6c'})


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def check_consistency(argument,scope):
    host = argument.get('compiler_storage_semantics') or argument.get('compiler_runtime_contract')
    host = host or re.search(r'not (?:native )?z/OS(?!-specific)|host CEE3ABD terminating shim',argument.get('argument',''))
    if host and scope != 'host-compiler-scoped':
        raise ValueError('claim-scope-host-semantics-unclassified')


def load_decisions(root=ROOT, *, public_key=None, trusted_head=None):
    paths = sorted((root/'docs/factory').glob('claim-scope-decisions-*.json'))
    if not paths:return dict(arguments=[],acceptances=[])
    def read(path):
        document=json.loads(path.read_bytes())
        seal=digest({key:value for key,value in document.items() if key!='content_sha256'})
        if seal!=document.get('content_sha256'):raise ValueError('claim-scope-decision-hash')
        if seal not in ACCEPTED_OVERLAYS:raise ValueError('claim-scope-decision-unbound')
        for group in ('arguments','acceptances'):
            identities=[]
            for item in document[group]:
                identities.append((item['id'],item['record_sha256'],item['source_sha256']))
                if item['claim_scope'] not in ('host-compiler-scoped','twin-and-zos'):
                    raise ValueError('claim-scope-decision-inventory')
            if len(set(identities))!=len(identities):raise ValueError('claim-scope-decision-inventory')
        return document
    original=read(root/'docs/factory/claim-scope-decisions-2026-10-15.json')
    if original['content_sha256']!='3f5f5f84f68d5410bc0070f75e4d3e9b471a3d853233b9658153d4fe76228f6c':
        raise ValueError('claim-scope-baseline-changed')
    current=read(paths[-1])
    for group in ('arguments','acceptances'):
        for item in current[group]:
            if item['claim_scope']!='twin-and-zos':continue
            prior=[r for r in original[group] if all(r[k]==item[k] for k in ('id','record_sha256','source_sha256','claim_scope'))]
            if len(prior)==1:continue
            if public_key is None or trusted_head is None:raise ValueError('claim-scope-signed-review-required')
            reviews=[r for r in current.get('scope_reviews',[]) if (r['kind'],r['id'])==(group,item['id'])]
            if len(reviews)!=1:raise ValueError('claim-scope-signed-review-required')
            from lightyear_factory.tower_authority import proof_contract
            from lightyear_control_tower.factory_policy import FactoryDecisions
            proof=reviews[0]['proof'];contract=proof_contract(proof);details=contract['details']
            subject=dict(kind=group,**{k:item[k] for k in ('id','record_sha256','source_sha256','claim_scope')})
            if details['claim_scope']!='zos-facing' or details['items']!=[item['id']] or details['packet_sha256']!=digest(subject):
                raise ValueError('claim-scope-review-binding')
            verified=FactoryDecisions(public_key,trusted_head).verify(proof,'equivalence-review',contract,('accept',))
            if verified['validation']['items'][item['id']]['outcome']!='accept':raise ValueError('claim-scope-review-not-accepted')
    return current


def recompute(fresh, reviews, accepted, scope, *, scope_decisions=None):
    decisions = load_decisions() if scope_decisions is None else scope_decisions
    by_id = {r['id']: r for r in reviews}; approvals = {r['id']: r for r in accepted}
    if len({r['id'] for r in fresh}) != len(fresh): raise ValueError('duplicate-mutant-site')
    kills, exclusions, refusals, unresolved = set(), set(), set(), set()
    for receipt in fresh:
        key = receipt['id']; review = by_id.get(key, {}); status = receipt['status']
        if status.startswith('killed-') or review.get('refuted'):
            witness = receipt if status.startswith('killed-') else review.get('witness', {})
            (kills if isinstance(witness, dict) and all(witness.get(k, {}).get('status') == 'executed' for k in ('baseline', 'actual')) else unresolved).add(key)
            continue
        if status == 'not-compiled': refusals.add(key); continue
        if status == 'evidence-gap': unresolved.add(key); continue
        argument = review.get('argument', {})
        source = review.get('mutant', {}).get('source_sha256')
        # Independently join the dated records; do not call the engine's scope
        # selection or denominator implementation.
        args = [r for r in decisions['arguments'] if r['id']==key and r['record_sha256']==digest(argument) and r['source_sha256']==source]
        argument_scope = args[0]['claim_scope'] if len(args)==1 else None
        if scope == 'zos-facing': check_consistency(argument, argument_scope)
        approval = approvals.get(key)
        approvals_scoped = [r for r in decisions['acceptances'] if approval and r['id']==key and r['record_sha256']==digest(approval) and r['source_sha256']==source]
        acceptance_scope = approvals_scoped[0]['claim_scope'] if len(approvals_scoped)==1 else None
        individual = bool(approval and approval['source_sha256']==source and (scope=='twin' or acceptance_scope=='twin-and-zos'))
        host = argument_scope != 'twin-and-zos' and not (individual and acceptance_scope=='twin-and-zos')
        eligible_proof = scope == 'twin' and review.get('TCE', {}).get('identical') or review.get('class_covered') or individual
        (exclusions if eligible_proof and not (scope == 'zos-facing' and host) else unresolved).add(key)
    denominator = len(fresh) - len(exclusions) - len(refusals)
    return dict(sites=len(fresh), killed=len(kills), eligible=denominator, kill_rate=f'{len(kills)}/{denominator}',
        compiler_refusals=sorted(refusals), excluded_ids=sorted(exclusions), unresolved_ids=sorted(unresolved),
        minimum_50_met=denominator >= 50, at_least_90_percent=denominator > 0 and 10 * len(kills) >= 9 * denominator)


def check(fresh, reviews, accepted, scope, tower):
    computed = recompute(fresh, reviews, accepted, scope)
    expected = {k: tower[k] for k in ('sites', 'killed', 'eligible', 'kill_rate', 'minimum_50_met', 'at_least_90_percent')}
    expected.update(compiler_refusals=sorted(tower['compiler_refusals']),
        excluded_ids=sorted(r['id'] for r in tower['excluded_equivalents']), unresolved_ids=sorted(r['id'] for r in tower['unresolved_survivors']))
    if computed != expected: raise ValueError('independent-threshold-crosscheck-disagrees:' + scope)
    return dict(passed=True, claim_scope=scope, recomputed=computed)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('input', type=Path); a = p.parse_args()
    value = json.loads(a.input.read_bytes()); print(json.dumps(check(**value), indent=2))
