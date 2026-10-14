"""Evidence-only overlay for the approved, pinned INTCALC loader domain.

Never changes raw campaign dispositions or makes a conditional decision effective.
"""
from collections import Counter
import json
import re
from pathlib import Path

from .equivalence_evidence import seal
from .legacy_twin import ROOT, FILES, sha, unframe, verify_build, write_json

SCENARIO = 'intcalc-duplicate-category'
PROPOSAL = '0706ffff6b402568715f3f83174327b166791c6fee88d530016cde77c6f8d882'


def sealed(value):
    return {**value, 'content_sha256': seal(value)}


def verify_seal(value):
    if value.get('content_sha256') != seal({k: v for k, v in value.items() if k != 'content_sha256'}):
        raise ValueError('loader-domain-seal')
    return value


def source_binding():
    proposal = json.loads((ROOT / 'docs/factory/intcalc-duplicate-category-proposal-2026-10-12.json').read_bytes())
    verify_seal(proposal)
    if proposal['content_sha256'] != PROPOSAL:
        raise ValueError('loader-domain-proposal-changed')
    approval = json.loads((ROOT / 'docs/factory/intcalc-duplicate-category-approval-2026-10-12.json').read_bytes())
    verify_seal(approval)
    if approval['approved'] is not True or approval['content_sha256'] != 'ebfd9cd159be1afa3fbad7e122195088ed2f0892272f0576302357135a4bb745':
        raise ValueError('loader-domain-approval-changed')
    for item in proposal['bound_sources']:
        if sha((ROOT / item['path']).read_bytes().replace(b'\r\n', b'\n')) != item['lf_sha256']:
            raise ValueError('loader-domain-bound-source-changed:' + item['path'])
    return proposal['bound_sources']


def loader_receipt(target, folder, *, instrumented, head):
    """Verify actual load-TCATBALF logs and bytes, never exception text alone."""
    from .scenario_generation import case
    target, folder = Path(target).resolve(), Path(folder).resolve()
    sources = source_binding()
    build = verify_build(target)
    if build['coverage_instrumented'] is not instrumented or any(build.get(k) for k in ('legacy_mutant', 'systematic_mutant', 'fault_declaration', 'cp037_keys')):
        raise ValueError('loader-domain-baseline-required')
    job, _, images, _ = case(SCENARIO)
    if job != 'INTCALC':
        raise ValueError('loader-domain-job')
    log = folder / 'logs/load-TCATBALF.json'
    actual = json.loads(log.read_bytes())
    expected_command = [str(target / 'INTCALC/bin/TCATBALF'), 'load', str(folder / 'before/TCATBALF'), str(folder / 'files/TCATBALF')]
    if actual != {'command': expected_command, 'returncode': 66}:
        raise ValueError('loader-domain-wrong-refusal')
    if list((folder / 'logs').glob('program.*')) or (folder / 'run-receipt.json').exists() or list((folder / 'after').iterdir()):
        raise ValueError('loader-domain-program-started')
    flat = unframe(images['TCATBALF'], FILES[job]['TCATBALF'][0])
    if (folder / 'before/TCATBALF').read_bytes() != flat:
        raise ValueError('loader-domain-input-changed')
    keys = [flat[i:i + 17].hex() for i in range(0, len(flat), 50)]
    duplicates = {key: n for key, n in sorted(Counter(keys).items()) if n > 1}
    if not duplicates:
        raise ValueError('loader-domain-no-duplicate')
    # Earlier indexed loads must have succeeded, with the exact generated input.
    for dd in ('ACCTFILE', 'TCATBALF'):
        if (folder / 'before' / dd).read_bytes() != unframe(images[dd], FILES[job][dd][0]):
            raise ValueError('loader-domain-input-changed:' + dd)
    if json.loads((folder / 'logs/load-ACCTFILE.json').read_bytes())['returncode'] != 0:
        raise ValueError('loader-domain-earlier-load-failed')
    return sealed(dict(schema='intcalc-loader-domain-receipt/1', head=head, scenario=SCENARIO,
        proposal_sha256=PROPOSAL, bound_sources=sources, instrumented=instrumented,
        build_receipt_sha256=sha((target / 'build-receipt.json').read_bytes()),
        loader_source_sha256=sha((target / 'INTCALC/TCATBALF.cob').read_bytes()),
        loader_binary_sha256=sha((target / 'INTCALC/bin/TCATBALF').read_bytes()),
        input_sha256={dd: sha(raw) for dd, raw in images.items()}, duplicate_keys_hex=duplicates,
        logs_sha256={p.name: sha(p.read_bytes()) for p in sorted((folder / 'logs').iterdir()) if p.is_file()},
        returncode=66, program_started=False, classification='expected-loader-refusal',
        kill_credit=False, equivalence_credit=False, comparison_credit=False, coverage_credit=False,
        effective=False, release_authorized=False))


def executed(row):
    return (row.get('status') == 'executed' and type(row.get('returncode')) is int
        and bool(row.get('outputs')) and all(isinstance(r, dict) and re.fullmatch(r'[0-9a-f]{64}', r.get('sha256', '')) for r in row['outputs'].values())
        and all(re.fullmatch(r'[0-9a-f]{64}', row.get(k, '')) for k in ('stdout_sha256', 'stderr_sha256')))


def assess(rows, expected_cases, control, instrumented, head):
    """Assess every raw gap separately, retaining all mutant sites."""
    from .systematic_mutation import outcome
    for receipt, mode in ((control, False), (instrumented, True)):
        verify_seal(receipt)
        if (receipt['head'] != head or receipt['scenario'] != SCENARIO or
            receipt['proposal_sha256'] != PROPOSAL or receipt['instrumented'] is not mode or
            receipt['returncode'] != 66 or receipt['program_started'] is not False):
            raise ValueError('loader-domain-baseline-binding')
    if control['input_sha256'] != instrumented['input_sha256'] or control['duplicate_keys_hex'] != instrumented['duplicate_keys_hex']:
        raise ValueError('loader-domain-baselines-disagree')
    expected = sorted(set(expected_cases) - {SCENARIO})
    assessments = []
    for row in rows:
        if row['status'] != 'evidence-gap':
            continue
        comparisons = row.get('valid_domain_comparisons', [])
        names = [r['case'] for r in comparisons]
        remaining = [g for g in row.get('evidence_gaps', []) if g['case'] != SCENARIO]
        remaining += [dict(case='fault:'+r.get('fault','unknown'),status=r.get('status')) for r in row.get('fault_challenges',[]) if r.get('status')!='survived']
        complete = sorted(names) == expected and len(names) == len(set(names))
        valid = complete and all(executed(r['baseline']) and executed(r['actual'])
            and r['status'] == outcome(r['baseline'], r['actual']) == 'survived' for r in comparisons)
        scoped = any(g['case'] == SCENARIO for g in row.get('evidence_gaps', []))
        resolved = scoped and valid and not remaining
        assessments.append(dict(id=row['id'], raw_record_sha256=seal(row),
            assessment='resolved-by-valid-comparisons' if resolved else 'still-a-gap',
            loader_scenario_assessment='outside-approved-comparison-domain' if scoped else 'not-applicable',
            expected_valid_cases=expected, observed_valid_cases=names,
            valid_comparisons=sum(executed(r['baseline']) and executed(r['actual']) for r in comparisons),
            remaining_gaps=remaining, comparison_evidence_sha256=seal(comparisons),
            proposed_status='equivalent (argued, listed)' if resolved and isinstance(row.get('disposition'), dict) else 'survived' if resolved else 'evidence-gap'))
    return sealed(dict(schema='intcalc-loader-domain-overlay/1', head=head, proposal_sha256=PROPOSAL,
        control=control, instrumented=instrumented, original_gap_count=len(assessments),
        original_sites=len(rows), sites_removed=0, assessments=assessments,
        effective=False, release_authorized=False, qualification_credit=False, measurement_credit=False))


def project(rows, overlay):
    """New in-memory projection only. The raw records remain authoritative history."""
    verify_seal(overlay)
    lookup = {r['id']: r for r in overlay['assessments']}
    if len(rows) != overlay['original_sites'] or {r['id'] for r in rows if r['status'] == 'evidence-gap'} != set(lookup):
        raise ValueError('loader-domain-population-mismatch')
    result = []
    for row in rows:
        assessment = lookup.get(row['id'])
        if assessment and seal(row) != assessment['raw_record_sha256']:
            raise ValueError('loader-domain-raw-record-changed')
        result.append({**row, 'status': assessment['proposed_status']} if assessment else dict(row))
    return result
