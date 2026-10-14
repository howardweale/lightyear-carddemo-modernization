"""Independent receipt-to-denominator arithmetic; does not call the Tower assessor."""
import argparse
import json
from pathlib import Path


def recompute(fresh, reviews, accepted, scope):
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
        argument = review.get('argument', {}); text = argument.get('argument', '')
        host = key == 'CBTRN02C-delete-MOVE-718-447' or bool(argument.get('compiler_storage_semantics') or argument.get('compiler_runtime_contract')) or any(s in text for s in ('not z/OS', 'not native z/OS', 'host CEE3ABD terminating shim'))
        approval = approvals.get(key)
        individual = bool(approval and approval['source_sha256'] == review.get('mutant', {}).get('source_sha256') and not (scope == 'zos-facing' and approval['scope'] == 'host-compiler-scoped'))
        if individual and approval.get('explicit_zos_scope_basis') and key in ('CBACT04C-receiving-size-133-19', 'CBTRN02C-constant-718-445'): host = False
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
