"""One authorized CI comparison of unchanged POSTTRAN attempt 1 with its twin."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

from tools.prepare_posttran_phase2 import ROOT, OUTPUTS, sha, digest, save
from tools.check_posttran_attempt1_phase1 import CANDIDATE, EXPECTED, policy, limits, structural
PLAN = ROOT / 'docs/factory/posttran-phase2-plan-2026-10-14.json'


def authorize(plan, env, head):
    payload = {k: v for k, v in plan.items() if k != 'content_sha256'}
    if digest(payload) != plan.get('content_sha256'): raise ValueError('phase2-plan-seal')
    if env.get('GITHUB_ACTIONS') != 'true' or env.get('GITHUB_EVENT_NAME') != 'pull_request' or env.get('GITHUB_RUN_ATTEMPT') != '1': raise ValueError('phase2-first-PR-CI-attempt-only')
    if env.get('POSTTRAN_PHASE2_APPROVED_PLAN') != plan['content_sha256'] or env.get('POSTTRAN_PHASE2_APPROVED_HEAD') != head: raise ValueError('phase2-explicit-plan-and-head-approval-required')
    if plan.get('generation_attempt') != 1 or plan.get('model_calls') != 0 or plan.get('retries') != 0: raise ValueError('phase2-bounds')
    return plan


def verify():
    plan = json.loads(PLAN.read_bytes())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    authorize(plan, os.environ, head)
    for path, expected in {**plan['bound_files'], **plan['candidate_files']}.items():
        p = (ROOT / path).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or p.is_symlink() or sha(p.read_bytes()) != expected: raise ValueError('phase2-bound-file-changed:' + path)
    if sha(CANDIDATE.read_bytes()) != EXPECTED: raise ValueError('phase2-candidate-changed')
    return plan, head


def reserve(output):
    plan, head = verify()
    name = 'posttran-phase2-consumed-' + plan['content_sha256']
    repository = os.environ['GITHUB_REPOSITORY']
    if repository != 'howardweale/lightyear-carddemo-modernization': raise ValueError('phase2-repository')
    # Atomic, persistent repository ref consumes the attempt before any execution.
    # A timeout is an unknown reservation outcome: stop; never retry this request.
    url = f'https://api.github.com/repos/{repository}/git/refs'
    body = json.dumps({'ref': 'refs/tags/' + name, 'sha': head}).encode()
    request = urllib.request.Request(url, data=body, method='POST', headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        reserved = json.load(response)
    if reserved['object']['sha'] != head: raise ValueError('phase2-reservation-ref-binding')
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'reservation.json', dict(plan_sha256=plan['content_sha256'], head=head, run_id=os.environ['GITHUB_RUN_ID'], attempt=1, consumed_before_execution=True))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write(f"reservation={name}\npreparation_run={plan['preparation_run']}\n")


def returncodes_agree(candidate, twin, scenario):
    if candidate == twin and candidate in (0, 4): return True
    return scenario == 'generated:posttran-duplicate-id' and candidate == 999 and twin == 12


def twin_action(action, work, name=None, kind=None):
    from lightyear_mainframe.legacy_twin import build, run
    plan = json.loads(PLAN.read_bytes())
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('POSTTRAN_PHASE2_APPROVED_PLAN') != plan['content_sha256']:
        raise ValueError('phase2-twin-execution-not-authorized')
    if action == 'build': return build(work / 'twin-build', jobs=['POSTTRAN'])
    return run(work / 'twin-build', name, work / 'twin-runs' / (kind + '-' + name), generated=name if kind == 'generated' else None)


def field_disagreements(dd, legacy, candidate):
    from lightyear_mainframe.records import load_copybook, from_ascii_fixed
    from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
    from itertools import zip_longest
    binding = dataset_binding(load_bindings(), 'POSTTRAN', 'STEP15', dd)
    layout = load_copybook(ROOT / binding['copybook'])
    left, right = from_ascii_fixed(layout, legacy), from_ascii_fixed(layout, candidate)
    source = (ROOT / 'spec/mainframe/public-source/CBTRN02C.cbl').read_text().splitlines()
    differences = []
    for ordinal, (a, b) in enumerate(zip_longest(left, right)):
        af = {r['path']: r for r in a['fields']} if a else {}
        bf = {r['path']: r for r in b['fields']} if b else {}
        for path in sorted(af.keys() | bf.keys()):
            x, y = af.get(path), bf.get(path)
            if x is not None and y is not None and x['raw_hex'] == y['raw_hex'] and x['value'] == y['value']: continue
            name = path.rsplit('.', 1)[-1]
            lines = [i for i, text in enumerate(source, 1) if re.search(r'(?<![A-Z0-9-])' + re.escape(name) + r'(?![A-Z0-9-])', text)]
            differences.append(dict(field=dd + ':' + path, record_ordinal=ordinal,
                legacy_value=x['value'] if x else None, candidate_value=y['value'] if y else None,
                legacy_raw_hex=x['raw_hex'] if x else None, candidate_raw_hex=y['raw_hex'] if y else None,
                source_lines=lines, source_reference_basis='Occurrences of the field name in pinned CBTRN02C; empty means no direct named reference.'))
    if not differences and legacy != candidate:
        differences.append(dict(field=dd + ':record-framing', legacy_value=legacy.hex(), candidate_value=candidate.hex(), source_lines=[]))
    return differences


def execute(output, archive, reservation):
    plan, head = verify()
    record = json.loads(reservation.read_bytes())
    if record != dict(plan_sha256=plan['content_sha256'], head=head, run_id=os.environ['GITHUB_RUN_ID'], attempt=1, consumed_before_execution=True): raise ValueError('phase2-reservation-binding')
    if sha(archive.read_bytes()) != plan['twin']['image_archive_sha256']: raise ValueError('phase2-image-archive-changed')
    subprocess.run(['docker', 'load', '-i', str(archive)], check=True, timeout=240)
    image = plan['twin']['image_id']
    if subprocess.check_output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], text=True).strip() != image: raise ValueError('phase2-image-id')
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='posttran-phase2-results/1', plan_sha256=plan['content_sha256'], head=head,
        run_id=os.environ['GITHUB_RUN_ID'], generation_attempt=1, cases=[], unresolved=[],
        model_calls=0, release_authorized=False, zos_confirmation=False, oracle_status='provisional', candidate_edited=False)
    def persist():
        report['counts'] = {s: sum(r['status'] == s for r in report['cases']) for s in ('equivalent', 'divergent', 'indeterminate')}
        report['complete'] = len(report['cases']) == plan['scenario_count']
        save(output / 'results.json', report)
        counts = report['counts']
        title = f"{counts['equivalent']} of {plan['scenario_count']} scenarios equivalent, {counts['divergent']} divergent, {counts['indeterminate']} indeterminate"
        (output / 'results.md').write_text(title + '\n\nTwin-scoped, AI-generated-candidate evidence. Not z/OS confirmation or release approval.\n\nPlan: `' + plan['content_sha256'] + '`. Complete: ' + str(report['complete']) + '.\n\n| Scenario | Result |\n| --- | --- |\n' + ''.join('| ' + r['scenario'] + ' | ' + r['status'] + ' |\n' for r in report['cases']) + '\nFull receipt bindings, keep-or-fix checks, and proposed unresolved entries are in results.json.\n')
    def twin(action, scenario=None):
        command = ['docker', 'run', '--rm', '--network=none', '--memory=2g', '--cpus=2',
            '-v', str(ROOT) + ':/source:ro', '-v', str(output) + ':/work', '-w', '/source',
            '-e', 'PYTHONPATH=/source/src:/source', '-e', 'GITHUB_ACTIONS=true',
            '-e', 'POSTTRAN_PHASE2_APPROVED_PLAN=' + plan['content_sha256'], image, 'python3', '-B', '-m', 'tools.run_posttran_phase2',
            '--twin-action', action, '--output', '/work']
        if scenario: command += ['--scenario', scenario['name'], '--kind', scenario['kind']]
        subprocess.run(command, check=True, timeout=180)
    persist()
    try:
        twin('build')
        version = subprocess.check_output(['javac', '-version'], text=True).strip()
        if not re.match(r'javac 21(?:\.|$)', version): raise ValueError('Java21-required')
        classes = output / 'classes'; classes.mkdir()
        compiled = subprocess.run(['javac', '-proc:none', '--release', '21', '-d', str(classes), str(CANDIDATE)], capture_output=True, timeout=120)
        (output / 'compile.stdout').write_bytes(compiled.stdout); (output / 'compile.stderr').write_bytes(compiled.stderr)
        if compiled.returncode: raise ValueError('candidate-compilation-failed')
        from lightyear_mainframe.legacy_twin import public_inputs
        from lightyear_mainframe.scenario_generation import case
        from lightyear_mainframe.posttran_invariants import check
        for index, scenario in enumerate(plan['scenarios']):
            row = dict(scenario=scenario['id'], input_sha256=scenario['input_sha256'], status='indeterminate')
            report['cases'].append(row)
            try:
                _, meta, images, _ = case(scenario['name']) if scenario['kind'] == 'generated' else public_inputs(scenario['name'])
                if {dd: sha(raw) for dd, raw in images.items()} != scenario['input_sha256'] or meta['candidate_timestamp'] != scenario['timestamp']: raise ValueError('scenario-binding-changed')
                base = output / f'candidate-{index:02d}'; inputs = base / 'inputs'; dest = base / 'outputs'
                inputs.mkdir(parents=True); dest.mkdir()
                for dd, raw in images.items(): (inputs / dd).write_bytes(raw)
                pol = base / 'candidate.policy'; pol.write_text(policy(inputs, dest, classes))
                cmd = ['java', '-Xmx512m', '-Djava.security.manager', '-Djava.security.policy==' + str(pol), '-cp', str(classes), 'PosttranCandidate', str(inputs), str(dest), scenario['timestamp']]
                child = subprocess.run(cmd, cwd=base, capture_output=True, timeout=20, preexec_fn=limits,
                    env={k: v for k, v in os.environ.items() if k in ('PATH', 'JAVA_HOME', 'LANG')})
                (base / 'stdout').write_bytes(child.stdout); (base / 'stderr').write_bytes(child.stderr)
                if {p.name: sha(p.read_bytes()) for p in inputs.iterdir()} != scenario['input_sha256']: raise ValueError('candidate-input-changed')
                after = structural(dest); code = int((dest / 'RETURN-CODE').read_text().strip())
                if child.returncode != code % 256: raise ValueError('candidate-process-contract')
                twin('run', scenario)
                folder = output / 'twin-runs' / (scenario['kind'] + '-' + scenario['name'])
                receipt = json.loads((folder / 'run-receipt.json').read_bytes())
                if receipt['input_ascii_sha256'] != scenario['input_sha256']: raise ValueError('twin-input-binding')
                expected = {dd: (folder / 'after' / dd).read_bytes() for dd in OUTPUTS}
                row.update(candidate_code=code, twin_code=receipt['returncode'],
                    twin_receipt_sha256=sha((folder / 'run-receipt.json').read_bytes()),
                    candidate_outputs={dd: sha(raw) for dd, raw in after.items()}, twin_outputs={dd: sha(raw) for dd, raw in expected.items()})
                differences = [dd for dd in OUTPUTS if after[dd] != expected[dd]]
                if not returncodes_agree(code, receipt['returncode'], scenario['id']): differences.append('RETURN-CODE')
                row['status'] = 'divergent' if differences else 'equivalent'
                row['keep_or_fix_checks'] = dict(candidate=check(images, after, timestamp=scenario['timestamp'], returncode=code, returncode_contract='source-abcode'),
                    twin=check(images, expected, timestamp=scenario['timestamp'], returncode=receipt['returncode']))
                if scenario['id']=='public:posttran-public':
                    rejects={lane:len(data['DALYREJS'])//431 for lane,data in (('candidate',after),('twin',expected))}
                    row['keep_or_fix_checks']['public_reject_count']=dict(expected=38,observed=rejects,passed=all(n==38 for n in rejects.values()))
                    if not all(n==38 for n in rejects.values()):
                        row['status']='indeterminate'
                        report['unresolved'].append(dict(scenario=scenario['id'],input_sha256=scenario['input_sha256'],field='DALYREJS:record-count',legacy_value=rejects['twin'],candidate_value=rejects['candidate'],expected_keep_value=38,source_lines=[403],classification='keep-or-fix related',classification_author='Codex proposal',accepted=False))
                if not all(row['keep_or_fix_checks'][lane]['passed'] for lane in ('candidate','twin')):
                    row['status']='indeterminate'
                    report['unresolved'].append(dict(scenario=scenario['id'],input_sha256=scenario['input_sha256'],field='keep-or-fix-invariants',legacy_value=row['keep_or_fix_checks']['twin'],candidate_value=row['keep_or_fix_checks']['candidate'],source_lines=[379,403,423,545,561,710],classification='keep-or-fix related',classification_author='Codex proposal',accepted=False))
                for dd in differences:
                    details = field_disagreements(dd, expected[dd], after[dd]) if dd in expected else [dict(field='RETURN-CODE', legacy_value=receipt['returncode'], candidate_value=code, source_lines=[710])]
                    for detail in details:
                        report['unresolved'].append(dict(scenario=scenario['id'], input_sha256=scenario['input_sha256'], **detail,
                            classification='needs information', classification_author='Codex proposal', accepted=False))
            except Exception as exc:
                row['status'] = 'indeterminate'; row['reason'] = str(exc)
                report['unresolved'].append(dict(scenario=scenario['id'], input_sha256=scenario['input_sha256'], field=None,
                    legacy_value=None, candidate_value=None, source_lines=[], reason=str(exc),
                    classification='needs information', classification_author='Codex proposal', accepted=False))
            persist()
    except Exception as exc:
        report['run_error'] = str(exc)
        done = {r['scenario'] for r in report['cases']}
        for s in plan['scenarios']:
            if s['id'] not in done:
                report['cases'].append(dict(scenario=s['id'], input_sha256=s['input_sha256'], status='indeterminate', reason=str(exc)))
                report['unresolved'].append(dict(scenario=s['id'], input_sha256=s['input_sha256'], field=None, legacy_value=None, candidate_value=None, source_lines=[], reason=str(exc), classification='needs information', classification_author='Codex proposal', accepted=False))
    finally: persist()


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--reserve', action='store_true'); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--archive', type=Path); p.add_argument('--reservation', type=Path); p.add_argument('--twin-action', choices=['build', 'run']); p.add_argument('--scenario'); p.add_argument('--kind')
    a = p.parse_args()
    if a.twin_action: twin_action(a.twin_action, a.output, a.scenario, a.kind)
    elif a.reserve: reserve(a.output)
    else: execute(a.output, a.archive, a.reservation)
