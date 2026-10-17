"""Unsigned review projections; never activates an approval or threshold policy."""
import json
from .legacy_twin import ROOT, sha
from .equivalence_evidence import seal, validate_dependencies
from .loader_domain import verify_seal


def supplemental_acceptances(reviews, historical, job, register, *, include_satisfied_pending=True):
    document = json.loads((ROOT / 'docs/factory/equivalence-operator-acceptance-2026-10-12.json').read_bytes())
    verify_seal(document)
    if document['content_sha256'] != '822af989952301a165f468c38183871d644b2e0e1f8321ba1cb8a4daea13bfd9': raise ValueError('supplement-decision-changed')
    accepted = {r['id']: dict(r) for r in historical}; current = {r['id']: r for r in reviews}; pending = []
    for item in document['new_acceptances']:
        if item['program'] != job: continue
        row = current.get(item['id'])
        if not row or row.get('refuted'): raise ValueError('supplement-review-missing-or-refuted:' + item['id'])
        raw = (ROOT / item['source_path']).read_bytes().replace(b'\r\n', b'\n')
        source_lines = raw.decode().splitlines()
        lines = '\n'.join(source_lines[item['source_line'] - 1:item['source_end_line']])
        if sha(raw) != item['source_sha256'] or sha(lines.encode()) != item['source_lines_sha256'] or seal(row['argument']) != item['argument_sha256']: raise ValueError('supplement-source-or-argument-changed:' + item['id'])
        validate_dependencies(row['argument'], register)
        if not item['effective_for_individual_review']:
            if row.get('targeted_cases') != 200 or row.get('targeted_valid_comparisons') != 200 or row.get('targeted_evidence_complete') is not True or row.get('targeted_evidence_gaps') or row.get('targeted_counts') != {'survived': 200}:
                continue
            pending.append(dict(id=item['id'], evidence_sha256=seal(row), reason='200/200 met; new exact-head evidence binding and explicit effective approval still required'))
            if not include_satisfied_pending: continue
        accepted[item['id']] = dict(item, scope='twin')
    return list(accepted.values()), pending, document['content_sha256']


def review_projection(fresh, reviews, historical, job, register):
    """Supplement only the twin projection; no new z/OS acceptance or gap clearing."""
    from .equivalence_evidence import mutation_threshold_report
    accepted,pending,source=supplemental_acceptances(reviews,historical,job,register,
        include_satisfied_pending=job=='INTCALC')
    raw={scope:mutation_threshold_report(fresh,reviews,historical,scope,register) for scope in ('twin','zos-facing')}
    projected={scope:mutation_threshold_report(fresh,reviews,accepted if scope=='twin' else historical,scope,register) for scope in raw}
    return dict(schema='program-review-projection/1',program=job,raw_thresholds=raw,projected_thresholds=projected,
        pending_effective_acceptances=pending,supplement_sha256=source,effective=False,release_authorized=False)
