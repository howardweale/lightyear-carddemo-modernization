"""Build a new unsigned assessment from retained public CI archives, never execute them."""
import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import zipfile

from lightyear_control_tower.decisions import digest
from lightyear_control_tower.factory_order import body_hash
from lightyear_control_tower.factory_policy import FactoryDecisions
from lightyear_factory.release_grade import checklist, reasons as grade_reasons, paragraph
from lightyear_factory.tower_authority import proof_contract
from lightyear_mainframe.equivalence_evidence import seal
from tools.verify_public_retention import verify

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'docs/factory/evidence-retention-2026-10-18-intcalc.json'
EVIDENCE = 'docs/factory/release-evidence-2026-10-18'
REPORT = 'docs/factory/intcalc-releasability-2026-10-18'
CONSTANT_IDS = {f'CBACT04C-constant-output-{n}' for n in (492, 493, 494)}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sealed(row):
    need(seal({k:v for k,v in row.items() if k != 'content_sha256'}) == row['content_sha256'], 'current-receipt-seal')
    return row


def ordered_state(root, proof=None, public_key=None, trusted_head=None):
    """Missing current trusted journal is unknown, never evidence of no decisions."""
    if proof is None or public_key is None or trusted_head is None:
        return dict(state='unknown', complete=False, reason='current-ordered-decision-proof-not-supplied')
    try:
        index = json.loads((root/'docs/factory/intcalc-signing-order-2026-10-17.json').read_bytes())
        contracts = []
        for row in index['items']:
            raw = (root/row['path']).read_bytes()
            need(sha256(raw).hexdigest() == row['sha256'], 'ordered-template-hash')
            contracts.append(json.loads(raw))
        need(len(contracts) == 6, 'ordered-template-count')
        final = proof_contract(proof)
        need(final['program'] == 'INTCALC' and final['signing_order']['position'] == 6, 'ordered-final-position')
        need(body_hash(final) == body_hash(contracts[-1]), 'ordered-final-body')
        need(final['signing_order']['packet_sha256'] == digest([body_hash(c) for c in contracts]), 'ordered-packet')
        need(final['details']['effective_condition'] == 'unconditional', 'ordered-policy-conditional')
        authority = FactoryDecisions(public_key, trusted_head, evidence_root=root)
        authority.verify(proof, 'scenario-threshold-approval', final, ('approve',))
        return dict(state='verified-current', complete=True, reason=None,
                    journal_head=trusted_head, decision_sha256=proof['decision_sha256'])
    except (KeyError, ValueError, TypeError, OSError):
        return dict(state='unverified', complete=False, reason='current-ordered-decision-proof-invalid')


def assess_data(data, fresh, *, index_ref, index, grade, ordered):
    summary = sealed(data['INTCALC/summary.json'])
    projection = sealed(data['INTCALC/loader-domain-review-projection.json'])
    rehearsal = sealed(data['INTCALC/request-06-rehearsal.json'])
    need(summary['current_head'] == projection['head'] == rehearsal['head'] == index['head'], 'current-head-mismatch')
    need(rehearsal['run_id'] == index['run_id'], 'current-run-mismatch')
    need(rehearsal['disposable_ci_signatures_only'] is True and rehearsal['releasable'] is False, 'historical-rehearsal-scope')
    need(rehearsal['reasons'] == ['provisional-or-engineering-evidence'], 'historical-rehearsal-reasons')
    need(len(fresh) == summary['expected_sites'] and len({r['id'] for r in fresh}) == len(fresh), 'current-mutant-inventory')
    counts = Counter(r['status'] for r in fresh)
    killed = counts['killed-divergent'] + counts['killed-failure']
    eligible = len(fresh) - counts['not-compiled']
    rate = f'{killed}/{eligible}'
    need(eligible > 0 and all(x['kill_rate'] == rate for x in projection['raw_thresholds'].values()), 'current-raw-rate')
    need(all(x['passed'] for x in projection['independent_crosscheck'].values()), 'current-crosscheck')
    by_id = {r['id']:r for r in fresh}
    constants = []
    missing = []
    for field, record in sorted(data['INTCALC/constant-field-evidence.json'].items()):
        for mutant in record['mutants']:
            if mutant['id'] not in CONSTANT_IDS:
                continue
            raw = by_id[mutant['id']]
            need(seal(raw) == mutant['record_sha256'] and raw['status'] == mutant['status'], 'current-constant-record')
            row = dict(field=field, **mutant)
            row['caught'] = bool(row['evidence_complete'] and row['caught_comparison']
                and row['valid_comparisons'] > 0 and row['status'] in ('killed-divergent', 'killed-failure'))
            constants.append(row)
            if not row['caught']:
                missing.append(row['id'])
    need({r['id'] for r in constants} == CONSTANT_IDS and len(constants) == 3, 'current-constant-inventory')
    programs = {}
    for program in ('INTCALC', 'POSTTRAN'):
        scopes = data[program+'/threshold-2-by-scope.json']
        for row in scopes.values():
            sealed(row)
            need(row['current_head'] == index['head'], 'current-program-head')
        measured = scopes['twin']
        programs[program] = dict(business=measured['business'], io=measured['io'],
            diversity=measured['distinct_values_per_output_field'], below_two_values=measured['below_two_values'],
            threshold_by_scope=scopes)
    assessments = {}
    for overlay in projection['overlays']:
        need(overlay['head'] == index['head'] and overlay['sites_removed'] == 0, 'current-loader-binding')
        for row in overlay['assessments']:
            if row['id'] in assessments:
                stable = lambda x:{k:v for k,v in x.items() if k not in {'comparison_evidence_sha256','raw_record_sha256'}}
                need(stable(assessments[row['id']]) == stable(row), 'current-loader-shards')
            assessments[row['id']] = row
    pending = sorted(r['id'] for r in assessments.values() if r['assessment'] != 'resolved-by-valid-comparisons')
    scopes = {name:dict(raw=projection['raw_thresholds'][name], projected=row,
                       crosscheck=projection['independent_crosscheck'][name])
              for name,row in projection['projected_thresholds'].items()}
    blockers = grade_reasons(grade)
    if not ordered['complete']:
        blockers.append(ordered['reason'])
    if missing:
        blockers.append('caught-constant-evidence-required: '+', '.join(missing))
    if pending:
        blockers.append('unresolved-loader-evidence: '+', '.join(pending))
    if programs['INTCALC']['business']['covered'] != programs['INTCALC']['business']['total']:
        blockers.append('incomplete-business-outcomes')
    verdict = ('Not releasable: '+'. '.join(blockers)+'.') if blockers else 'Evidence prerequisites satisfied; this unsigned assessment grants no release authority.'
    value = dict(schema='intcalc-releasability/3', prepared_on='2026-10-18', supersedes='intcalc-releasability-2026-10-17.json',
        head=index['head'], run_id=index['run_id'], evidence_index=index_ref, verdict=verdict,
        claim_scope='twin', effective=ordered['complete'], release_authorized=False, zos_confirmation=False,
        raw_mutation_counts=dict(counts), raw_kill_rate=rate, scopes=scopes, programs=programs,
        constant_mutants=constants, missing_caught_constant_fields=missing,
        remaining_evidence_gaps=pending, raw_evidence_gap_ids=sorted(r['id'] for r in fresh if r['status']=='evidence-gap'),
        loader_domain=dict(assessment_counts=dict(Counter(r['assessment'] for r in assessments.values())),
            assessments=list(assessments.values()), effective=False, sites_removed=0),
        rehearsal=dict(path=EVIDENCE+'/INTCALC/request-06-rehearsal.json',
            file_sha256=index['sources'][0]['files'][EVIDENCE+'/INTCALC/request-06-rehearsal.json'],
            content_sha256=rehearsal['content_sha256'], reasons=rehearsal['reasons']),
        release_grade=grade, ordered_decisions=ordered, blockers=blockers,
        authority='Unsigned evidence projection; no production authority', authorized_by='Howard', performed_by='Codex CI')
    value['content_sha256'] = digest(value)
    return value


def render(value):
    lines = ['# INTCALC releasability - '+value['prepared_on'], '',
        f"As of {value['prepared_on']}: retained campaign {value['run_id']} at `{value['head']}`.",
        'Twin-scoped engineering measurement. No z/OS confirmation or release authority.', '',
        'Raw kills / eligible: '+value['raw_kill_rate']+'.', '',
        '| Constant mutant | Outcome | Valid comparisons | Complete caught evidence | Record SHA-256 |',
        '|---|---|---:|---|---|']
    for row in sorted(value['constant_mutants'], key=lambda x:x['id']):
        lines.append(f"| {row['id']} | {row['status']} | {row['valid_comparisons']} | {row['caught']} | `{row['record_sha256']}` |")
    lines += ['', '| Scope | Raw kills / eligible | Projected kills / eligible |', '|---|---|---|']
    for scope,row in value['scopes'].items():
        lines.append(f"| {scope} | {row['raw']['kill_rate']} | {row['projected']['kill_rate']} |")
    receipt = value['rehearsal']
    lines += ['', 'Historical request-06 rehearsal file SHA-256: `'+receipt['file_sha256']+'`.',
        'Its content seal is `'+receipt['content_sha256']+'`; recorded reason: '+', '.join(receipt['reasons'])+'.',
        'Those were disposable CI signatures. The historical receipt is preserved exactly.', '',
        paragraph(value['release_grade']), '',
        'Current ordered decision evidence: '+value['ordered_decisions']['state']+'. '+
            (value['ordered_decisions'].get('reason') or 'Verified against the externally supplied current journal.')+'.',
        'Missing current journal evidence is unknown; this report does not assert that no human decisions exist.', '',
        'Projected exclusions remain conditional on exact effective decisions; no loader kill credit is added.',
        'All original archives and member hashes are indexed by [the retention manifest](evidence-retention-2026-10-18-intcalc.json).',
        '', value['verdict'], '']
    return '\n'.join(lines)


def build(root, archives, output, run, *, proof=None, public_key=None, trusted_head=None):
    root, archives, output = Path(root), Path(archives), Path(output)
    manifest_path = root/MANIFEST
    manifest = json.loads(manifest_path.read_bytes())
    need(run['id'] == manifest['source_run'] and run['head_sha'] == manifest['source_head']
         and run['event'] == 'push' and run['head_branch'] == 'main'
         and run['status'] == 'completed' and run['conclusion'] == 'success', 'retained-run-not-green-main')
    output.mkdir(parents=True, exist_ok=False)
    folder = output/EVIDENCE
    folder.mkdir(parents=True)
    verification = folder/'retention-verification.json'
    urls = {x['url']: archives/x['name'] for x in manifest['assets']}
    verify(manifest_path, verification, open_url=lambda url, **kw:urls[url].open('rb'))
    asset = next(x for x in manifest['assets'] if x['name'] == 'equivalence-aggregate.zip')
    data = {}
    files = {EVIDENCE+'/retention-verification.json':sha256(verification.read_bytes()).hexdigest(),
             MANIFEST:sha256(manifest_path.read_bytes()).hexdigest()}
    run_bytes = (json.dumps(run,indent=2)+'\n').encode()
    (folder/'source-run.json').write_bytes(run_bytes)
    files[EVIDENCE+'/source-run.json'] = sha256(run_bytes).hexdigest()
    with zipfile.ZipFile(archives/asset['name']) as archive:
        for member in asset['files']:
            name = member['path']
            need(len(Path(name).parts) == 2 and Path(name).parts[0] in ('INTCALC', 'POSTTRAN')
                 and name.endswith('.json') and '..' not in Path(name).parts and '\\' not in name, 'aggregate-member-path')
            raw = archive.read(name)
            need(sha256(raw).hexdigest() == member['sha256'], 'aggregate-member-hash')
            if name == 'INTCALC/fresh-mutants.json':
                fresh = json.loads(raw)
            elif name.endswith('/fresh-mutants.json'):
                continue
            else:
                data[name] = json.loads(raw)
                target = folder/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                files[EVIDENCE+'/'+name] = sha256(raw).hexdigest()
    rehearsal = data['INTCALC/request-06-rehearsal.json']
    inventory = {x['path']:x['sha256'] for x in asset['files']}
    for name, expected in rehearsal['evidence_files'].items():
        need(inventory['INTCALC/'+name] == expected, 'rehearsal-member-binding')
    # A successful aggregate run is not a full protected-main workflow audit.
    # Absent full snapshot keeps that checklist gate visibly unmet.
    diagnostic = dict(evidence_head=manifest['source_head'], oracle_status=data['INTCALC/summary.json']['oracle_status'],
        run_class=data['INTCALC/summary.json']['run_class'], fixture_only=True, disposable_ci_signatures_only=True,
        release_grade=dict(claim_scope='twin', native_runtime_claimed=False))
    grade = checklist(diagnostic, scope='twin')
    grade['verified-retained-evidence-required'] = True  # verify() above checked every original archive and member.
    ordered = ordered_state(root, proof, public_key, trusted_head)
    index = dict(schema='release-evidence-index/3', head=manifest['source_head'], run_id=manifest['source_run'],
        conclusion=run['conclusion'], retention_complete=True,
        sources=[dict(head=manifest['source_head'], run_id=manifest['source_run'], files=files)],
        external_archive=dict(manifest=MANIFEST, manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest()),
        run_scope='Aggregate workflow success only; complete protected-main audit not supplied')
    raw = (json.dumps(index,indent=2)+'\n').encode()
    (folder/'index.json').write_bytes(raw)
    index_ref = dict(path=EVIDENCE+'/index.json', sha256=sha256(raw).hexdigest())
    value = assess_data(data, fresh, index_ref=index_ref, index=index, grade=grade, ordered=ordered)
    path = output/REPORT
    path.with_suffix('.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    path.with_suffix('.md').write_text(render(value),encoding='utf-8',newline='\n')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    build(ROOT,args.archives,args.output,json.loads(args.run.read_bytes()))


if __name__ == '__main__':
    main()
