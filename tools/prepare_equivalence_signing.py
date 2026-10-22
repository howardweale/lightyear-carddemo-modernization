"""Prepare unsigned public review documents from immutable Git blobs; no signing."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
from lightyear_mainframe.equivalence_automation import digest, verify, sealed
from lightyear_mainframe.equivalence_projection import project
from lightyear_control_tower.factory_policy import validate_contract

BASE = 'docs/factory/equivalence-evidence-2026-10-15'
DEST = 'docs/factory/equivalence-scale-2026-10-16'
EVIDENCE_COMMIT = '78be9cafb322b6a9dacaa94fd6027df2aeb605e5'
CLASS = 'legacy-APPL-RESULT/1'
SCORECARD = 'docs/factory/equivalence-scorecard-2026-10-22.json'
FRESH_COMMIT = 'e5b041754c7bf38c874836eff2c7f36ede90234b'
FRESH_RUN = 38930496735


def blob(root, path, commit=EVIDENCE_COMMIT):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=root)


def read(root, path):
    return json.loads(blob(root, path))


def write(root, path, value):
    path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = ((json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
           if not isinstance(value, str) else value.encode())
    if path.exists() and path.read_bytes() != raw:
        raise ValueError('immutable-generated-file-conflict:' + str(path))
    path.write_bytes(raw)


def measurements(root,total):
    programs=[];heads=set()
    for program in ('INTCALC','POSTTRAN','TRANREPT'):
        folder=DEST+'/fresh-e1/'+program
        raw=blob(root,folder+'/summary.json',FRESH_COMMIT)
        repeat_raw=blob(root,folder+'/repeat-comparison.json',FRESH_COMMIT)
        summary=verify(json.loads(raw));repeat=verify(json.loads(repeat_raw))
        if summary['head']!=repeat['head'] or summary['program']!=repeat['program'] or not repeat['identical_resolutions']:
            raise ValueError('fresh-E1-provenance-mismatch')
        heads.add(summary['head'])
        routes = copy.deepcopy(summary['routes'])
        if summary.get('held_out') is True:
            # Compiler identities are retained; no executable campaign measured
            # held-out kills or resolved campaign survivors.
            for counts in routes.values():
                counts.update(survivors_resolved=0, kills=0)
        programs.append(dict(program=program,argued_resolved=summary['argued_resolved'],
            argued_total=summary['argued_total'],generated_cases=summary['generated_cases'],
            routes=routes,identical_resolutions=repeat['identical_resolutions'],
            mutants_compared_twice=repeat['mutants'],repeat_sha256=digest(repeat_raw),summary_sha256=digest(raw)))
    if len(heads)!=1:raise ValueError('fresh-E1-mixed-heads')
    if sum(p['argued_resolved'] for p in programs)!=total['resolved_now'] or sum(p['argued_total'] for p in programs)!=total['denominator']:
        raise ValueError('fresh-E1-projection-count-mismatch')
    return dict(fresh_E1=dict(total,head=heads.pop(),run_id=FRESH_RUN,programs=programs),
        preserved_341=dict(total,evidence_commit=EVIDENCE_COMMIT),
        person_minutes_per_1000_sites=dict(method='Prospective active-review intervals times reviewer count, excluding CI wait; sum person-minutes / distinct reviewed sites * 1000.',status='not measured',value=None))


def prepare(root, audit_commit=None, *, output_root=None):
    output_root = root if output_root is None else output_root
    reports = []
    for program, source in (('INTCALC', 'CBACT04C'), ('POSTTRAN', 'CBTRN02C')):
        folder = BASE + '/' + program
        request = next(r for r in read(root, folder + '/class-requests.json')
                       if r['class_proof']['class_id'] == CLASS)
        proof = verify(request['class_proof'])
        census = verify(read(root, folder + '/legacy-class-census.json'))
        source_path = f'spec/mainframe/public-source/{source}.cbl'
        source_bytes = blob(root, source_path)
        matcher_path = 'src/lightyear_mainframe/equivalence_classes.py'
        if digest(blob(root, matcher_path)) != proof['matcher_sha256']:
            raise ValueError('published-matcher-mismatch')
        if digest(source_bytes) != census['source_sha256'] or not census['passed'] or census['raw_consumers']:
            raise ValueError('published-census-binding')
        triage = verify(read(root, 'docs/factory/equivalence-triage-2026-10-15.json'))
        population = next(p for p in triage['programs'] if p['program'] == program)
        mutants = {r['id']: r['mutant'] for r in population['rows']}
        for mid, match in proof['matches'].items():
            if (digest(mutants[mid]) != match['mutant_sha256']
                    or match['census_sha256'] != census['content_sha256']
                    or match['source_sha256'] != census['source_sha256']):
                raise ValueError('class-member-source-or-census-binding')
        # Stable sample without replacement; full membership is always included.
        members = sorted(proof['matches'])
        sample = sorted(members, key=lambda mid: digest((proof['content_sha256'] + ':' + mid).encode()))[:30]
        lines = source_bytes.decode().splitlines()
        entries = []
        for mid in sample:
            match = proof['matches'][mid]
            argument = match['argument']
            locations = sorted(set(argument.get('supporting_source_lines', []) + [argument['source_line']]))
            entries.append(dict(id=mid, binding=match,
                original=mutants[mid]['original'], replacement=mutants[mid]['replacement'],
                source_context=[dict(line=n, text=lines[n-1]) for n in locations]))
        audit = sealed(dict(schema='equivalence-class-audit/1', program=program,
            class_id=CLASS, measurement_head=proof['head'], evidence_commit=EVIDENCE_COMMIT,
            class_proof_sha256=proof['content_sha256'], matcher_path=matcher_path,
            matcher_sha256=proof['matcher_sha256'], census=census,
            census_implementation_sha256=digest(blob(root, 'src/lightyear_mainframe/equivalence_evidence.py')),
            source=dict(path=source_path, sha256=digest(source_bytes), commit=EVIDENCE_COMMIT),
            members=members, sample_method='lowest SHA256(class-proof-seal:member-id), without replacement',
            sample_size=len(sample), sample=entries, claim_scope='twin',
            signature_status='unsigned', review_statement='Howard reports reviewing the APPL-RESULT audit sample; no cryptographic signature inferred.',
            audit_observed_error_rate=None, qualification_credit=False, release_authorized=False))
        audit_path = DEST + '/' + program + '-class-audit.json'
        write(output_root, audit_path, audit)
        md = [f'# {program}: APPL-RESULT class signing packet', '',
              f'{len(members)} exact members; 30-member deterministic audit. Twin scope only.', '',
              f'Source SHA-256: `{digest(source_bytes)}`',
              f'Matcher SHA-256: `{proof["matcher_sha256"]}`',
              f'Class proof: `{proof["content_sha256"]}`', '',
              'The census and full membership are in the companion JSON. Signing is an operator review, not independent attestation. No signature has been applied.', '']
        for index, row in enumerate(entries, 1):
            md += [f'## {index}. {row["id"]}', '', row['binding']['argument']['argument'], '', '```cobol']
            md += [f'{r["line"]:4}: {r["text"]}' for r in row['source_context']]
            md += ['```', '']
        write(output_root, DEST + '/' + program + '-class-audit.md', '\n'.join(md) + '\n')
        rebound = copy.deepcopy(request)
        # Preserve measurement/proof identities. Only the import location changes.
        for binding in rebound['contract']['sources']:
            if digest(blob(root, binding['path'])) != binding['sha256']:
                raise ValueError('historical-packet-byte-mismatch')
            binding['commit'] = EVIDENCE_COMMIT
        census_path = folder + '/legacy-class-census.json'
        rebound['contract']['sources'].append(dict(path=census_path, commit=EVIDENCE_COMMIT,
                                                  sha256=digest(blob(root, census_path))))
        if audit_commit:
            raw = blob(root, audit_path, audit_commit)
            if raw != (output_root / audit_path).read_bytes():
                raise ValueError('audit-publication-mismatch')
            rebound['contract']['sources'].append(dict(path=audit_path, commit=audit_commit, sha256=digest(raw)))
            validate_contract(rebound['contract'])
            write(output_root, DEST + '/' + program + '-class-request.json', rebound)
        ledger = verify(read(root, folder + '/resolutions.json'))
        reports.append(project(ledger, [rebound], proof['matcher_sha256']))
    # Request digests depend on audit publication, so only seal the final scorecard then.
    if audit_commit:
        total = dict(denominator=sum(r['denominator'] for r in reports),
                     resolved_now=sum(r['resolved_now'] for r in reports),
                     resolved_after_pending_signatures=sum(r['resolved_after_pending_signatures'] for r in reports))
        write(output_root, SCORECARD, sealed(dict(stage='E1', evidence_commit=EVIDENCE_COMMIT,
            prepared_on='2026-10-22',
            supersedes=dict(path=DEST+'/scorecard.json', sha256=digest(blob(root, DEST+'/scorecard.json', FRESH_COMMIT))),
            operator_observation=dict(as_of='2026-10-22', source='Howard closeout instructions, 22 October 2026',
                nonempty_zos_tranrept_observed=False,
                statement='Howard reports that the 21 October Maintec TRANREPT run filtered out all records by its date window. Delivery contents were not accessed; this is operator-reported context, not record-level evidence.'),
            measurements=measurements(root,total), programs=reports, total=total,
            held_out=dict(program='TRANREPT/CBTRN03C', compiler_identities=2, sites=413,
                          class_matches=0, conclusion='no evidence of generality',
                          CBSTM03A='not measured', CBSTM03B='not measured'),
            release_authorized=False, model_calls=0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--audit-commit')
    args = parser.parse_args()
    prepare(args.root, args.audit_commit)
