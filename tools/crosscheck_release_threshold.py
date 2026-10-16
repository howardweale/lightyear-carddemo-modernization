"""Independent receipt-to-denominator arithmetic; does not call the Tower assessor."""
import argparse
import json
from pathlib import Path


def recompute(fresh, reviews, accepted, scope, *, scope_decisions=None):
    from lightyear_mainframe.claim_scope import load_decisions, digest, check_consistency
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
