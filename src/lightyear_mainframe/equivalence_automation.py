"""Additive, source-bound equivalence triage and conservative resolution ledger.

Historical arguments are inputs, never authority. Unknown reachability is not an
oracle gap. This module has no compiler, model, network or execution capability.
"""
from collections import Counter, deque
import hashlib
import json
import math
from pathlib import Path
import random
import re

from .generic_scenario_ir import BoundSource, translate
from .scenario_coverage import code
from .systematic_mutation import generate, apply

PROGRAMS = {'INTCALC': 'CBACT04C', 'POSTTRAN': 'CBTRN02C', 'TRANREPT': 'CBTRN03C'}
ROUTES = ('S1', 'S2', 'S3', 'S4', 'needs a person')


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def sealed(value):
    return {**value, 'content_sha256': digest(value)}


def verify(value):
    if digest({k: v for k, v in value.items() if k != 'content_sha256'}) != value.get('content_sha256'):
        raise ValueError('evidence-seal-mismatch')
    return value


def bound(path, text):
    return BoundSource(path, text, digest(text.encode()))


def load_ir(root, program):
    path = f'spec/mainframe/public-source/{program}.cbl'
    text = (root / path).read_text()
    books = {p.stem: bound(p.relative_to(root).as_posix(), p.read_text())
             for p in sorted((root / 'spec/mainframe/copybooks').glob('*.cpy'))}
    return text, translate(bound(path, text), books)


def refs(expr):
    return ({expr['value']} if expr['kind'] == 'reference' else set()).union(
        *(refs(x) for x in expr.get('operands', [])))


def slice_to_outputs(ir, starts, outputs):
    """A may-path is informative; absence proves nothing in incomplete IR."""
    graph = {}
    for edge in ir['data_flow']:
        graph.setdefault(edge['source'], set()).add(edge['target'])
    controls = set().union(*(refs(s['expression']) for s in ir['statements'] if s['kind'] == 'condition'))
    queue = deque((s, 0) for s in sorted(starts)); seen = set(); distance = None
    while queue:
        node, depth = queue.popleft()
        if node in seen: continue
        seen.add(node)
        if node in outputs and distance is None: distance = depth
        queue.extend((n, depth + 1) for n in sorted(graph.get(node, ())))
    return dict(reaches_output=True if distance is not None else False if ir['translation_complete'] and outputs else None,
                reaches_control=bool(seen & controls) if ir['translation_complete'] or seen & controls else None,
                reaches_money=True if any(re.search(r'(AMT|AMOUNT|BAL|CREDIT|DEBIT|INTEREST)',n) for n in seen & outputs) else False if ir['translation_complete'] else None,
                output_distance=distance, may_reachable=sorted(seen),
                complete=ir['translation_complete'], semantics=ir['flow_semantics'])


def historical_population(root, job):
    old = json.loads((root / f'docs/factory/systematic-{job.lower()}-review311.json').read_text())['mutants']
    arguments = {r['id']: r for r in old if r['status'] == 'equivalent (argued, listed)'}
    for r in json.loads((root / 'docs/factory/post-campaign-equivalence-review311.json').read_text())['arguments']:
        if r['id'].startswith(PROGRAMS[job] + '-'):
            arguments[r['id']] = r
    individual = {r['id'] for r in json.loads((root / 'docs/factory/equivalence-individual-review-2026-10-12.json').read_text())['mutants']}
    return old, arguments, individual


def triage(root, job, head):
    program = PROGRAMS[job]; text, ir = load_ir(root, program)
    inventory = {r['id']: r for r in generate(text, program)}
    held_out = job == 'TRANREPT'
    if held_out:
        old, argued, individuals = [], {}, set()
        selected = set(inventory)
        basis = {}
    else:
        old, argued, individuals = historical_population(root, job)
        retained_path = f'docs/factory/equivalence-baseline-2026-10-15/{job}.json'
        retained = verify(json.loads((root / retained_path).read_text()))
        fresh = retained['mutants']
        if set(r['id'] for r in fresh) != set(inventory):
            raise ValueError('baseline-inventory-mismatch')
        # The sealed per-mutant rows take precedence over stale aggregate ID lists.
        selected = set(argued) | {r['id'] for r in fresh if r['status'] in ('survived', 'evidence-gap')}
        from .equivalence_evidence import appl_result_census, class_covered
        census = appl_result_census(text, program)
        basis = {}
        for mid, a in argued.items():
            arg = a.get('disposition', a)
            basis[mid] = 'individual' if mid in individuals else 'class' if class_covered(inventory[mid], arg, census) else 'compiler'
    missing = selected - inventory.keys()
    if missing: raise ValueError('baseline-not-in-current-inventory:' + str(sorted(missing)))
    fields = {}
    for f in ir['fields']: fields.setdefault(f['path'].split('.')[-1], []).append(f)
    # Output dataset bindings supply field names, not a guessed money-field list.
    from .zos_bindings import load_bindings, dataset_binding
    from .records import load_copybook
    outputs = set()
    if not held_out:
        for dd in (('ACCTFILE', 'TRANSACT') if job == 'INTCALC' else ('ACCTFILE', 'TRANFILE', 'DALYREJS', 'TCATBALF')):
            layout = load_copybook(root / dataset_binding(load_bindings(), job, 'STEP15', dd)['copybook'])
            outputs.update(f.path.split('.')[-1] for f in layout.fields if not f.filler)
    rows = []
    for mid in sorted(selected):
        m = inventory[mid]
        operand = root / ('spec/mainframe/copybooks/' + m['source_path'] if m.get('source_path') else f'spec/mainframe/public-source/{program}.cbl')
        apply(operand.read_text(), m)  # Validate hash and exact original lines.
        words = ' '.join(code(line) for line in m['original'].splitlines()).split()
        kind = words[0] if words else 'unknown'
        if kind.isdigit(): kind = 'DATA'
        names = sorted(set(re.findall(r'\b[A-Z][A-Z0-9-]*\b', ' '.join(words))) & fields.keys())
        statements = [s for s in ir['statements'] if s['location']['path'].endswith(program + '.cbl') and s['location']['line'] <= m['line']]
        statement = statements[-1] if statements else None
        if statement and statement['location']['line'] < m['line'] - 5: statement = None
        target = statement.get('target') if statement else None
        sliced = slice_to_outputs(ir, {target} if target else set(names), outputs)
        current = basis.get(mid, 'survivor')
        route = 'S1' if current == 'compiler' else 'S2' if current == 'class' else 'S3' if m['operator'] == 'rounded' else 'S4'
        # These are candidate allocations, never promises of a resolution.
        rows.append(dict(id=mid, mutant=m, current_basis=current, argued=mid in argued,
                         individual_review=mid in individuals, statement_kind=kind,
                         fields={name: fields[name] for name in names}, receiving_field=target,
                         field_metadata_complete=bool(names) and all(len(fields[n]) == 1 for n in names),
                         output_slice=sliced, route=route,
                         automatic_blocker='fresh re-checkable artifact required' if current == 'compiler' else
                         'signed exact class contract required' if current == 'class' else
                         'aliases, I/O and paragraph control may be untranslated; historical argument is not a proof',
                         status='unresolved'))
    files = ['docs/factory/equivalence-b1-b2-results-2026-10-12.json',
             'docs/factory/equivalence-individual-review-2026-10-12.json',
             f'docs/factory/equivalence-baseline-2026-10-15/{job}.json'] if not held_out else []
    return sealed(dict(schema='equivalence-triage/1', head=head, program=job, held_out=held_out,
                       input_sha256={p: digest((root / p).read_bytes()) for p in files}, sources=ir['sources'],
                       ir_sha256=digest(ir), ir_issues=ir['issues'], inventory_count=len(inventory),
                       baseline_counts=dict(Counter(r['current_basis'] for r in rows)),
                       route_candidates={route: dict(individual=sum(r['route'] == route and r['individual_review'] for r in rows),
                                                      survivors=sum(r['route'] == route and not r['argued'] for r in rows),
                                                      proven_expected_resolutions=0) for route in ROUTES},
                       rows=rows, model_calls=0, claim_scope='twin', release_authorized=False))


def audit_samples(resolutions, run_hash):
    groups = {}
    for r in resolutions:
        if r['status'] in ('equivalent', 'killed'):
            groups.setdefault((r['program'], r['route']), []).append(r['id'])
    return [dict(program=p, route=route, population=len(ids),
                 items=sorted(random.Random(digest([run_hash, p, route])).sample(sorted(ids), min(30, len(ids)))),
                 reviewed=0, confirmed_errors=0, observed_error_rate=None, upper_95=None, status='unsigned-review-pending')
            for (p, route), ids in sorted(groups.items())]


def upper_bound(errors, n):
    """One-sided 95% exact binomial (Clopper-Pearson) upper limit."""
    if not 0 <= errors <= n or n < 1: raise ValueError('audit-counts')
    if errors == n: return 1.0
    lo, hi = 0., 1.
    for _ in range(70):
        p = (lo + hi) / 2
        cdf = sum(math.comb(n, k) * p**k * (1-p)**(n-k) for k in range(errors + 1))
        if cdf > .05: lo = p
        else: hi = p
    return hi


def audit_disposition(samples, reviewed):
    """Confirmed errors disable the entire program/route, not just the sample."""
    disabled = set(); result = []
    for sample in samples:
        outcomes = [reviewed[i] for i in sample['items'] if i in reviewed]
        if any(x not in ('correct', 'incorrect') for x in outcomes): raise ValueError('audit-outcome')
        n = len(outcomes); errors = outcomes.count('incorrect')
        if errors: disabled.add((sample['program'], sample['route']))
        result.append({**sample, 'reviewed': n, 'confirmed_errors': errors,
                       'observed_error_rate': errors/n if n else None,
                       'upper_95': upper_bound(errors, n) if n else None,
                       'status': 'disabled' if errors else 'complete' if n == len(sample['items']) else 'review-pending'})
    return result, disabled


def score(sites, baseline_kills, baseline_refusals, rows):
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)): raise ValueError('duplicate-resolution')
    kills = {r['id'] for r in rows if r['status'] == 'killed'}
    eq = {r['id'] for r in rows if r['status'] == 'equivalent'}
    if set(baseline_kills) & (kills | eq) or set(baseline_refusals) & (kills | eq):
        raise ValueError('overlapping-score-populations')
    k = len(baseline_kills) + len(kills); raw_n = sites - len(baseline_refusals)
    if k + len(eq) > raw_n: raise ValueError('impossible-score')
    return dict(raw=dict(numerator=k, denominator=raw_n), adjusted=dict(numerator=k, denominator=raw_n-len(eq)),
                excluded_equivalents=len(eq), unresolved=raw_n-k-len(eq),
                unobservable=sum(r['status'] == 'unobservable' for r in rows))
