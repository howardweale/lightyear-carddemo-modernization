"""Render the dated decision packet from retained receipts; no workload execution."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-10-14'
EVIDENCE = 'docs/factory/release-evidence-' + DATE
TARGETS = ['CBACT04C-receiving-scale-164-26', 'CBACT04C-receiving-scale-173-34', 'CBTRN02C-receiving-scale-173-20']
DECISIONS = ['equivalence-operator-acceptance-2026-10-12.json', 'intcalc-duplicate-category-approval-2026-10-12.json',
    'posttran-phase1-rerun-authorization-2026-10-12.json', 'b06-afternoon-preparation-2026-10-13.json', 'merge-hold-lift-2026-10-14.json']


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())
def save(path, value): path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def build(commit, root=ROOT):
    folder = root / 'docs/factory'
    def read(path): return json.loads((root / path).read_bytes())
    def source(path): return dict(path=path, sha256=sha((root / path).read_bytes()), commit=commit)
    index = read(EVIDENCE + '/index.json')
    for archive in index['sources']:
        for path, expected in archive['files'].items():
            if sha((root / path).read_bytes()) != expected: raise ValueError('retained-evidence-hash:' + path)
    supplement = read('docs/factory/equivalence-operator-acceptance-2026-10-12.json')
    diversity_rows = read('docs/factory/diversity-review-2026-10-12.json')['rows']
    programs = {}
    for job in ('INTCALC', 'POSTTRAN'):
        main = read(EVIDENCE + '/main-' + job + '-threshold-2-by-scope.json')
        prior = read(EVIDENCE + '/pr328-' + job + '-threshold-2-by-scope.json')
        before = read('docs/factory/tower-run-38198096890/' + job + '/threshold.json')
        targets = []
        current = read(EVIDENCE + '/main-' + job + '-results.json')
        previous = {r['id']: r for r in read(EVIDENCE + '/pr328-' + job + '-results.json')}
        for row in current:
            if row['id'] in TARGETS:
                fields = ('targeted_cases','targeted_valid_comparisons','targeted_evidence_complete','targeted_evidence_gaps','targeted_counts')
                measured = {k: row.get(k) for k in fields}
                targets.append(dict(id=row['id'], main=measured, pr328={k: previous[row['id']].get(k) for k in fields}, unchanged=all(row.get(k)==previous[row['id']].get(k) for k in fields), effective=False))
        varying = [dict(field=r['field'], before=before['twin']['distinct_values_per_output_field'].get(r['field']),
            main=main['twin']['distinct_values_per_output_field'].get(r['field']), pr328=prior['twin']['distinct_values_per_output_field'].get(r['field']))
            for r in diversity_rows if r['program']==job and r['classification']=='needs-variation']
        programs[job] = dict(targets=targets, varying_fields=varying, business=main['twin']['business'], io=main['twin']['io'],
            threshold_by_scope=main, incomplete_targets=[dict(id=r['id'], gaps=r.get('targeted_evidence_gaps',[])) for r in current if 'targeted_cases' in r and (r['targeted_cases']!=200 or r.get('targeted_valid_comparisons')!=200 or not r.get('targeted_evidence_complete'))])
    constants = supplement['constant_field_acceptances']
    for c in constants:
        raw = (root / c['source_path']).read_bytes().replace(b'\r\n',b'\n')
        line = raw.decode().splitlines()[c['source_line']-1]
        if sha(raw)!=c['source_sha256'] or sha(line.encode())!=c['source_line_sha256']: raise ValueError('constant-source-binding')
    fresh = read(EVIDENCE + '/main-INTCALC-mutation-results.json')
    counts = dict(Counter(r['status'] for r in fresh))
    summary = dict(schema='intcalc-releasability/1', prepared_on=DATE, evidence_index=source(EVIDENCE+'/index.json'),
        verdict='Not releasable', claim_scope='twin', effective=False, release_authorized=False, zos_confirmation=False,
        programs=programs, raw_mutation_counts=counts, raw_kill_rate='308/421',
        constants=constants, constants_source_sha256=supplement['content_sha256'],
        remaining_evidence_gaps=[r['id'] for r in fresh if r['status']=='evidence-gap'],
        loader_domain=dict(status='implementation prepared; fresh PR CI receipts pending', effective=False, no_denominator_removal=True),
        independent_crosscheck=dict(status='implemented; fresh PR CI result pending'),
        conditions=[dict(condition=c, state='not yet established on the implementation head', evidence=source('docs/factory/howard-decisions-2026-10-11b.json')) for c in read('docs/factory/howard-decisions-2026-10-11b.json')['scenario_threshold_2']['conditions']],
        blockers=['113 raw execution gaps require fresh, individually assessed loader-domain overlays.',
            'Current raw mutation rate is 308/421, below 90%; new projected rates and independent cross-check await CI.',
            'Effective threshold/2, constant-field and loader-domain decisions remain unsigned.',
            'Items 20/23/42 have 200/200 evidence but need explicit current-head effectiveness bindings.'])
    summary['content_sha256']=digest(summary);save(folder/f'intcalc-releasability-{DATE}.json',summary)
    lines=['# INTCALC releasability — '+DATE,'','**Not releasable.** Fresh loader-domain evidence and effective decisions are still pending.','',
        'This is a provisional, twin-scoped engineering assessment. It is not z/OS confirmation or a customer release.','',
        'Main evidence: run 38624637311 at `8650f58c5fdcd0916e22152b5bbbaa1182efdf71`. PR328 cross-check: run 38312412871. Artifact ZIP and retained-file hashes are in [the evidence index](release-evidence-2026-10-14/index.json).','',
        '| Criterion | Measured | State |','| --- | --- | --- |','| Business outcomes | 8/8 | Met on retained main run |','| I/O outcomes | 85/86 | Last EOF edge needs effective signed exception |',
        f"| Raw mutation kills | 308/421; {counts.get('killed-failure',0)} failure, {counts.get('killed-divergent',0)} divergent | Below 90% |",'| Systematic sites | 421 | No site removed by loader rule |',
        '| Loader gaps | 113 | Fresh CI overlay pending |','| Effective policy | scenario-threshold/2 | Conditional; unsigned |','', '## Targeted cases','', '| Item | Main valid comparisons | PR328 | Difference |','| --- | --- | --- | --- |']
    for p in programs.values():
        for t in p['targets']: lines.append(f"| {t['id']} | {t['main']['targeted_valid_comparisons']}/200 | {t['pr328']['targeted_valid_comparisons']}/200 | {'None' if t['unchanged'] else 'See JSON'} |")
    for job in programs:
        lines += ['', '## '+job+' output diversity','', '| Field | Before | Main | PR328 |','| --- | --- | --- | --- |']
        for r in programs[job]['varying_fields']: lines.append(f"| {r['field']} | {r['before']} | {r['main']} | {r['pr328']} |")
    lines += ['', 'The seven INTCALC constants remain compared and mutation-tested. Their exact source lines and hashes are retained in the JSON. Their accepted constant classification does not silently activate threshold policy.','', '## Remaining steps','']
    lines += ['- '+s for s in summary['blockers']]
    lines += ['', '**Not releasable:** finish fresh loader receipts and independent threshold reconciliation, then obtain the specific effective signatures.','']
    (folder/f'intcalc-releasability-{DATE}.md').write_text('\n'.join(lines))
    old=read('docs/factory/tower-backfill-request-2026-10-12.json')
    records=list(old['details']['records']); sources=list(old['sources'])
    for name in DECISIONS:
        path='docs/factory/'+name; record=read(path)
        records.append(dict(original_date=name[-15:-5],path=path,record=record)); sources.append(source(path))
    backfill=dict(schema='factory-contract/1',kind='factory-decision-backfill',program='factory',sources=sources,
        details=dict(records=records,activation='signed-factory-decisions-only',historical_only=True))
    save(folder/f'tower-backfill-request-{DATE}.json',backfill)
    inventory=dict(schema='backfill-inventory/1', source_files=DECISIONS, complete_for_repository_decisions=True,
        signed_b06_attempt_receipts_available=False, historical_only=True, signature=None)
    save(folder/f'tower-backfill-inventory-{DATE}.json',inventory)
    argument=read('docs/factory/io-gap-arguments.json')
    io=[r for r in argument['gaps'] if 'CBACT04C' in str(r)][0]
    save(folder/f'intcalc-io-exception-request-{DATE}.json',dict(schema='factory-contract/1',kind='io-exception-acceptance',program='INTCALC',
        sources=[source('docs/factory/io-gap-arguments.json')],details=dict(source_sha256='5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4',
            outcome_id='legacy:cobol-decision:CBACT04C:189:671',outcome='false',line=189,argument_sha256=digest(io))))
    save(folder/f'scenario-threshold-effective-request-{DATE}.json',dict(schema='factory-contract/1',kind='scenario-threshold-approval',program='INTCALC',
        sources=[source('docs/factory/howard-decisions-2026-10-11b.json')],details=dict(policy_sha256=digest(read('docs/factory/howard-decisions-2026-10-11b.json')['scenario_threshold_2']),
            version='scenario-threshold/2',effective_condition='unconditional',compiler_refusals='listed-excluded-not-blockers')))
    packet='''# Howard decision packet — 2026-10-14

**INTCALC: Not releasable.** Fresh loader-domain receipts and effective decisions remain pending.

**POSTTRAN: Phase 2 not run.** Plan preparation and authorization guards are implemented; the exact CI-generated plan must be committed and explicitly approved before comparison.

This packet is a draft, with no signature, activation, release authorization or z/OS confirmation. AI-assisted reviews are labelled as such.

## INTCALC

[The measured verdict](intcalc-releasability-2026-10-14.md) reports the retained main results, the PR328 cross-check, all targeted comparison counts, separate program diversity, source-bound constants and remaining gaps. Raw rc66 records remain unchanged. New CI overlays grant no loader-scenario kill, equivalence, comparison or coverage credit, and remove no mutant sites. The independent receipt cross-check fails on a disagreement with the threshold engine.

## Unsigned requests

- [Effective threshold/2 request](scenario-threshold-effective-request-2026-10-14.json): prepared only; not ready to sign while any listed condition remains unmet. No condition is automatically waived.
- [INTCALC I/O exception](intcalc-io-exception-request-2026-10-14.json): source-bound CBACT04C line189 false edge. The EOF flag begins N, is only set Y, and a TEST BEFORE loop admits N. The first IF tests N before the READ can set Y; no declared public fault seam changes this guard. The full argument remains in io-gap-arguments.json.
- Items 20/23/42, seven constant fields and loader-domain effectiveness: exact fresh CI bindings are pending before their final requests can be issued. The existing dated approvals remain unchanged and conditional where recorded.
- [Historical backfill](tower-backfill-request-2026-10-14.json): incorporates the October 12 scoped acceptances and constants, loader approval, Phase 1 rerun authorization, October 13 R4 template/authority records and October 14 merge-hold lift. Signed-only consumption remains inactive.

## POSTTRAN

The candidate bytes are unchanged. Preparation builds only the compiler image and input inventory, then emits a hashed plan and unsigned request. Execution requires Howard's exact plan and head approval, PR attempt1, verified file/image/input hashes, and an atomic persistent consumed-attempt ref before execution. No automatic retry, model call or candidate repair is permitted. Every differing or indeterminate scenario is recorded as a proposed unresolved entry.

The PR335 replay was **refused before compilation**: run 38600848981, job 115979402188, `rerun-exact-parent-required`. [The preserved log excerpt and hash](release-evidence-2026-10-14/posttran-pr335-replay.json) bind that finding. Phase 1's successful original run remains historical evidence.

## Main health

All 23 post-merge workflows on 8650f58c passed, including all six systematic engineering shards. PR336 merged at 69c9893c. Its latest main workflows were still finishing when this draft was prepared; no failed main run was observed. Final health must be rechecked before handoff.

## B06 Part 6

[The Part 6 evidence-gap report](b06-part6-2026-10-14.json) preserves the supplied brief's account separately from verified evidence. Signed attempt and cleanup receipts have not been located. The ten sequence/thread rows, record counts, heap and phase witnesses cannot be filled from the brief alone. No new B06 run is authorized. Further observer work is not planned; future Java work should start with outcome comparison and use targeted instrumentation only for unanswered questions.
'''
    (folder/f'howard-decision-packet-{DATE}.md').write_text(packet)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-commit',required=True);a=p.parse_args();build(a.source_commit)
