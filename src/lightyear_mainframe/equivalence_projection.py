"""Pending signatures are a projection, never a resolution or denominator edit."""
from .equivalence_automation import digest, verify, sealed


def project(ledger, requests, matcher_sha256, *, disabled_classes=()):
    verify(ledger)
    rows = {r['id']: r for r in ledger['rows']}
    if len(rows) != len(ledger['rows']):
        raise ValueError('duplicate-ledger-member')
    population = {i for i, r in rows.items() if r['argued']}
    resolved = {i for i in population if rows[i]['status'] in ('equivalent', 'killed')}
    pending = set()
    contracts = []
    for request in requests:
        proof = verify(request['class_proof'])
        contract = request['contract']
        details = contract['details']
        if (proof['head'] != ledger['head'] or proof['matcher_sha256'] != matcher_sha256
                or proof['claim_scope'] != 'twin' or details['claim_scope'] != 'twin'
                or contract['program'] != ledger['program']
                or details['class_proof_sha256'] != proof['content_sha256']
                or sorted(details['items']) != sorted(proof['matches'])):
            raise ValueError('pending-class-binding')
        if proof['class_id'] in disabled_classes:
            raise ValueError('held-out-disabled-class')
        for mid, match in proof['matches'].items():
            if mid not in rows or rows[mid]['mutant_sha256'] != match['mutant_sha256']:
                raise ValueError('pending-member-binding')
            if rows[mid]['source_sha256'] != match['source_sha256']:
                raise ValueError('pending-source-binding')
            if rows[mid]['status'] == 'killed':
                raise ValueError('class-includes-executed-kill')
            # Unobservable is never turned into an equivalent by a projection.
            if mid in population and rows[mid]['status'] in ('unresolved', 'proposed'):
                pending.add(mid)
        contracts.append(digest(contract))
    routes = {}
    for route in ('S1', 'S2', 'S3', 'S4'):
        now = {i for i in resolved if rows[i]['route'] == route}
        projected = now | (pending if route == 'S2' else set())
        routes[route] = dict(resolved_now=len(now), resolved_after_pending_signatures=len(projected))
    return sealed(dict(schema='equivalence-signature-projection/1', program=ledger['program'],
        measurement_head=ledger['head'], ledger_sha256=ledger['content_sha256'],
        denominator=len(population), resolved_now=len(resolved),
        resolved_after_pending_signatures=len(resolved | pending),
        pending_unique_members=sorted(pending), pending_contracts=sorted(set(contracts)), routes=routes,
        unobservable=sum(rows[i]['status'] == 'unobservable' for i in population),
        new_kills=0, reviewer_person_minutes_per_1000_sites=None,
        reviewer_effort_status='not-measured', signatures_verified=False,
        claim_scope='twin', release_authorized=False, historical_denominators_changed=False))
