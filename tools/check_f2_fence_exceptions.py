"""Validate an exact F2 exception from trusted base objects, never PR records.

This does not change the raw Java fence report or authorize a merge or run.
Human approval is recorded provenance, not machine authentication of the human.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CHECKER = 'tools/check_java_quality_fence.py'
VALIDATOR = 'tools/check_f2_fence_exceptions.py'
MANIFEST = 'docs/factory/f2-exact-byte-exceptions-2026-10-24.json'
GATE = 'tools/ci_gate.py'
BUDGETED = 'src/lightyear_factory/budgeted_providers.py'
PROVIDERS = 'src/lightyear_factory/providers.py'
POSTTRAN = 'docs/factory/posttran-phase2-plan-2026-10-16.json'
REPOSITORY = 'howardweale/lightyear-carddemo-modernization'
APPROVED_SHA = '12d195d37b6d7ed9e7ca8f290e61f8aead641c5ded2d3351db600def5816d928'
CONTROLS = {CHECKER, VALIDATOR, MANIFEST, GATE}
REPORT_KEYS = {'schema', 'base', 'head', 'fence_sha256', 'fenced_paths',
               'fenced_prefixes', 'source_records', 'blocked_paths',
               'merge_permitted', 'automatic_expiry'}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate-json-key')
        result[key] = value
    return result


def document(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def fields(value, names, code):
    require(isinstance(value, dict) and set(value) == set(names), code)


def digest(value, length=64):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value),
            'invalid-object-digest')
    return value


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def resolve(repo, value):
    digest(value, 40)
    result = git(repo, 'rev-parse', '--verify', value + '^{commit}').decode().strip()
    require(result == value, 'commit-identity')
    return result


def blob(repo, commit, path):
    row = git(repo, 'ls-tree', '-z', commit, '--', path).decode().split('\0')
    require(len(row) == 2 and row[1] == '', 'missing-or-ambiguous-blob')
    metadata, actual_path = row[0].split('\t')
    mode, kind, oid = metadata.split()
    require(actual_path == path and kind == 'blob' and mode == '100644', 'blob-mode')
    raw = git(repo, 'cat-file', 'blob', oid)
    return dict(mode=mode, sha256=sha(raw)), raw


def load_checker(repo, base):
    _, source = blob(repo, base, CHECKER)
    namespace = {'__name__': 'trusted_base_fence'}
    exec(compile(source, CHECKER, 'exec'), namespace)
    return namespace, source


def validate_raw_report(raw, expected, returncode):
    report = document(raw)
    fields(report, REPORT_KEYS, 'incomplete-fence-report')
    require(report == expected, 'unexpected-fence-report')
    require(report['schema'] == 'java-quality-fence/1', 'unknown-fence-schema')
    require(report['automatic_expiry'] is False, 'automatic-expiry-refused')
    require(report['merge_permitted'] is (not bool(report['blocked_paths'])),
            'inconsistent-fence-result')
    require(returncode == (1 if report['blocked_paths'] else 0), 'checker-error')
    return report


def validate_manifest(value):
    fields(value, {'schema', 'repository', 'base_anchor', 'activation', 'entries',
                   'identity_limitation', 'authority'}, 'manifest-fields')
    require(value['schema'] == 'f2-exact-byte-exceptions/1', 'manifest-schema')
    require(value['repository'] == REPOSITORY, 'manifest-repository')
    digest(value['base_anchor'], 40)
    require(value['activation'] == 'trusted-base-only-after-exact-head-merge-approval',
            'manifest-activation')
    require(value['identity_limitation'] ==
            'Operator-chat attribution is not independently authenticated; the agent shares Howard\'s GitHub identity. Open after-run item.',
            'identity-limitation-required')
    require(value['authority'] == {'merge': False, 'run': False, 'signing': False,
                                   'spend': False, 'gap_acceptance': False}, 'manifest-authority')
    require(isinstance(value['entries'], list) and len(value['entries']) == 1,
            'one-approved-entry-only')
    entry = value['entries'][0]
    fields(entry, {'repository', 'pr', 'path', 'mode', 'base_preimage_sha256',
                   'final_sha256', 'approved_change_commit', 'provenance'}, 'entry-fields')
    require(entry['repository'] == REPOSITORY and type(entry['pr']) is int and entry['pr'] == 455,
            'entry-target')
    require(entry['path'] == BUDGETED and entry['mode'] == '100644', 'ineligible-entry')
    digest(entry['base_preimage_sha256']); digest(entry['approved_change_commit'], 40)
    require(entry['final_sha256'] == APPROVED_SHA, 'unapproved-postimage')
    provenance = entry['provenance']
    fields(provenance, {'source', 'approved_by', 'recorded_at_pt', 'exact_sha256',
                        'statement', 'github_identity_is_human_proof'}, 'provenance-fields')
    require(provenance['source'] == 'operator-chat' and provenance['approved_by'] == 'Howard Weale',
            'approval-provenance')
    require(isinstance(provenance['recorded_at_pt'], str) and
            re.fullmatch(r'2026-10-24T\d{2}:\d{2}:\d{2}-07:00', provenance['recorded_at_pt']),
            'approval-time')
    require(provenance['exact_sha256'] == APPROVED_SHA and
            provenance['github_identity_is_human_proof'] is False, 'approval-hash-or-identity')
    require(provenance['statement'] == 'approved by Howard in the operator chat, ' +
            provenance['recorded_at_pt'] + ', exact hash ' + APPROVED_SHA, 'approval-statement')
    return entry


def ineligible_paths(repo, base, checker):
    original = document(git(repo, 'show', base + ':' + checker['ORIGINAL']))
    amendment = document(git(repo, 'show', base + ':' + checker['AMENDMENT']))
    judge = {checker['ORIGINAL'], checker['AMENDMENT']}
    judge.update(x['path'] for x in original['files'])
    judge.update(x['path'] for x in amendment['files'])
    judge.add(amendment['existing_authorized_change']['path'])
    prefixes = {p.split('/src/test/')[0] + '/src/test/' for p in judge
                if '/service/src/test/' in p}
    plan = document(git(repo, 'show', base + ':' + POSTTRAN))
    excluded = judge | set(plan['bound_files']) | set(plan['candidate_files']) | {POSTTRAN}
    prefixes.update(('docs/factory/posttran-', 'spec/mainframe/posttran-independent/'))
    return excluded, prefixes


def api(route):
    return document(subprocess.check_output(['gh', 'api', 'repos/' + REPOSITORY + '/' + route]))


def context(repo, base, head, event, environment, query=api):
    """Check live PR provenance; a main push must be the actual approved merge."""
    require(environment.get('GITHUB_REPOSITORY') == REPOSITORY and
            event.get('repository', {}).get('full_name') == REPOSITORY, 'wrong-repository')
    kind = environment.get('GITHUB_EVENT_NAME')
    live = query('pulls/455')
    require(live['number'] == 455 and live['base']['ref'] == 'main' and
            live['base']['repo']['full_name'] == REPOSITORY and
            live['head']['repo']['full_name'] == REPOSITORY, 'wrong-pr-or-repository')
    parents = git(repo, 'show', '-s', '--format=%P', head).decode().split()
    if kind == 'pull_request':
        pr = event['pull_request']
        require(pr['number'] == 455 and live['state'] == 'open' and not live['merged'], 'wrong-pr')
        require(pr['base']['sha'] == live['base']['sha'] == base and
                pr['head']['sha'] == live['head']['sha'], 'stale-pr-context')
        require(pr['head']['repo']['full_name'] == REPOSITORY, 'fork-refused')
        candidate = live['head']['sha']
        if head != candidate:
            require(parents == [base, candidate], 'unbound-checkout')
            tree = git(repo, 'merge-tree', '--write-tree', base, candidate).decode().strip()
            require(tree == git(repo, 'rev-parse', head + '^{tree}').decode().strip(),
                    'unexpected-merge-tree')
    elif kind == 'push':
        require(event.get('ref') == 'refs/heads/main' and event.get('before') == base and
                event.get('after') == head and live['merged'] is True and
                live['merge_commit_sha'] == head and parents == [base, live['head']['sha']],
                'unbound-main-merge')
        candidate = live['head']['sha']
    else:
        raise ValueError('exception-requires-pr-or-exact-main-merge')
    return dict(repository=REPOSITORY, pr=455, candidate=candidate)


def inspect(repo, base, head, event=None, environment=None, query=api):
    base = resolve(repo, base); head = resolve(repo, head)
    checker, source = load_checker(repo, base)
    # Keep the unchanged checker's actual report and exit outcome, and independently
    # reconstruct its complete result using the same trusted-base implementation.
    expected = checker['inspect'](repo, base, head)
    process = subprocess.run([sys.executable, '-B', '-c', source.decode('utf-8'),
                              '--repo', str(repo), '--base', base, '--head', head],
                             capture_output=True, check=False)
    report = validate_raw_report(process.stdout, expected, process.returncode)
    result = dict(schema='f2-fence-exception-result/1', raw_fence_report=report,
                  raw_checker_exit=process.returncode, accepted_exceptions=[],
                  fence_requirement_met=not report['blocked_paths'], merge_authorized=False,
                  run_authorized=False)
    if not report['blocked_paths']:
        return result
    _, raw = blob(repo, base, MANIFEST)
    manifest = document(raw); entry = validate_manifest(manifest)
    anchor = resolve(repo, manifest['base_anchor'])
    require(subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', anchor, base],
                           capture_output=True).returncode == 0, 'unrelated-base-anchor')
    changed = [p for p in git(repo, 'diff', '--no-renames', '--name-only', '-z', base, head)
               .decode().split('\0') if p]
    require(not (set(changed) & CONTROLS) and
            not any(p.startswith('.github/workflows/') for p in changed), 'candidate-control-change')
    # All of these objects must exist in base, including the validator itself.
    for path in CONTROLS:
        require(blob(repo, base, path) == blob(repo, head, path), 'candidate-control-change')
    require(blob(repo, base, PROVIDERS) == blob(repo, head, PROVIDERS), 'providers-change-refused')
    require(report['blocked_paths'] == [entry['path']], 'unlisted-fence-violation')
    excluded, prefixes = ineligible_paths(repo, base, checker)
    path = entry['path']
    require(path not in excluded and not any(path.startswith(p) for p in prefixes),
            'judge-or-posttran-exception-refused')
    f2 = document(git(repo, 'show', base + ':' + checker['F2']))
    require(path in {b['path'] for b in f2['engineering_source_bindings'].values()},
            'not-f2-engineering-source')
    before, _ = blob(repo, base, path); anchored, _ = blob(repo, anchor, path)
    after, _ = blob(repo, head, path)
    require(before == anchored == {'mode': entry['mode'], 'sha256': entry['base_preimage_sha256']},
            'wrong-preimage')
    require(after == {'mode': entry['mode'], 'sha256': entry['final_sha256']}, 'wrong-postimage')
    approved, _ = blob(repo, resolve(repo, entry['approved_change_commit']), path)
    require(approved == after, 'approved-commit-content')
    bound = context(repo, base, head, event or {}, environment or {}, query)
    # Re-check live provenance after object reads; stale observations never pass.
    require(context(repo, base, head, event or {}, environment or {}, query) == bound,
            'context-changed')
    result.update(accepted_exceptions=[dict(path=path, before=before, after=after,
                                          provenance=entry['provenance'])],
                  fence_requirement_met=True, manifest_sha256=sha(raw), context=bound)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    event = document(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes()) if os.environ.get('GITHUB_EVENT_PATH') else {}
    report = inspect(args.repo, args.base, args.head, event, os.environ)
    print(json.dumps(report, sort_keys=True))
    require(report['fence_requirement_met'], 'fence-requirement-not-met')


if __name__ == '__main__':
    main()
