"""Run unittest discovery with an execution ledger and explicit skip policy (CI only)."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import unittest


def leaves(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from leaves(test)
        else:
            yield test


class ExecutionResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []
        self.started = {}
        self.elapsed = {}

    def startTest(self, test):
        self.started[test.id()] = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        self.elapsed[test.id()] = time.monotonic() - self.started[test.id()]
        super().stopTest(test)

    def event(self, test, outcome, reason=None):
        parent = getattr(test, 'test_case', test)
        self.events.append(dict(test_id=parent.id(), event_id=test.id(), outcome=outcome,
                                reason=reason))

    def addSuccess(self, test):
        self.event(test, 'passed')
        super().addSuccess(test)

    def addSkip(self, test, reason):
        self.event(test, 'skipped', str(reason))
        super().addSkip(test, reason)

    def addFailure(self, test, err):
        self.event(test, 'failed')
        super().addFailure(test, err)

    def addError(self, test, err):
        self.event(test, 'error')
        super().addError(test, err)

    def addExpectedFailure(self, test, err):
        self.event(test, 'expected_failure')
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self.event(test, 'unexpected_success')
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        outcome = 'passed' if err is None else ('failed' if issubclass(err[0], test.failureException) else 'error')
        self.event(subtest, outcome)
        super().addSubTest(test, subtest, err)


class ExecutionRunner(unittest.TextTestRunner):
    resultclass = ExecutionResult

    def _makeResult(self):
        self.observed = super()._makeResult()
        return self.observed


def load_policy(path, root):
    policy = json.loads(Path(path).read_text(encoding='utf-8'))
    if policy.get('schema') != 'ci-test-skip-policy/1':
        raise ValueError('skip-policy-schema')
    seen = set()
    for entry in policy['allowances']:
        key = (entry['selector'], entry['reason'], tuple(entry['platforms']))
        if key in seen or entry['scope'] not in ('test', 'class'):
            raise ValueError('skip-policy-duplicate-or-scope')
        seen.add(key)
        if not re.fullmatch(r'test_\w+(?:\.\w+){1,2}', entry['selector']):
            raise ValueError('skip-policy-selector')
        if not entry['reason'] or not entry['rationale'] or not entry['platforms']:
            raise ValueError('skip-policy-explanation')
        if not set(entry['platforms']) <= {'Linux', 'Windows', 'Darwin'}:
            raise ValueError('skip-policy-platform')
        source = 'tests/' + entry['selector'].split('.')[0] + '.py'
        digest = hashlib.sha256((Path(root) / source).read_bytes()).hexdigest()
        if digest != policy['sources'][source]:
            raise ValueError('skip-policy-source-changed:' + source)
    return policy


def allowed(policy, identity, reason, system):
    matches = [entry for entry in policy['allowances']
               if system in entry['platforms'] and reason == entry['reason']
               and (identity == entry['selector'] if entry['scope'] == 'test'
                    else identity.rsplit('.', 1)[0] == entry['selector'])]
    return len(matches) == 1


def report(planned, result, policy, system, fatal=None):
    errors = []
    if not planned or len(planned) != len(set(planned)):
        errors.append('empty-or-duplicate-discovery')
    by_id = {}
    fixtures = []
    for event in result.events:
        by_id.setdefault(event['test_id'], []).append(event)
        fixture = re.fullmatch(r'(?:setUp|tearDown)(?:Class|Module) \((.+)\)', event['test_id'])
        if fixture:
            fixtures.append((fixture[1], event))
    rows = []
    for identity in planned:
        events = list(by_id.get(identity, []))
        events.extend(event for prefix, event in fixtures if identity.startswith(prefix + '.'))
        outcomes = {e['outcome'] for e in events}
        outcome = next((v for v in ('error', 'failed', 'unexpected_success', 'expected_failure', 'skipped', 'passed')
                        if v in outcomes), 'not_run')
        skips = [dict(reason=e['reason'], allowed=allowed(policy, identity, e['reason'], system))
                 for e in events if e['outcome'] == 'skipped']
        if any(not s['allowed'] for s in skips):
            errors.append('unlisted-skip:' + identity)
        if outcome in ('error', 'failed', 'unexpected_success', 'expected_failure', 'not_run'):
            errors.append(outcome + ':' + identity)
        rows.append(dict(test_id=identity, outcome=outcome, started=identity in result.started,
                         duration_seconds=result.elapsed.get(identity), skips=skips))
    # Fixture failures can happen after the last test, outside a planned test ID.
    if not result.wasSuccessful():
        errors.append('unittest-unsuccessful')
    if fatal:
        errors.append(fatal)
    return dict(schema='ci-test-execution/1', discovered=len(planned), started=len(result.started),
                counts=dict(Counter(row['outcome'] for row in rows)), tests=rows,
                events=result.events, errors=errors, accepted=not errors)


def execute(suite, policy, system, *, stream=None):
    planned = [test.id() for test in leaves(suite)]
    runner = ExecutionRunner(verbosity=2, stream=stream)
    fatal = None
    try:
        result = runner.run(suite)
    except BaseException as exc:
        result = getattr(runner, 'observed', ExecutionResult(sys.stderr, True, 2))
        fatal = 'runner-aborted:' + type(exc).__name__
    return report(planned, result, policy, system, fatal)


def write_report(output, data, *, summary=False):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    temp.replace(output)
    counts = ', '.join(f'{k}={v}' for k, v in sorted(data.get('counts', {}).items()))
    text = ('# Python unittest execution\n\n'
            f"Discovered: {data.get('discovered', 0)}; started: {data.get('started', 0)}. {counts}\n\n"
            f"Accepted: {data['accepted']}. Skips are not passes.\n\n"
            'This report covers full Python unittest discovery in verify.sh/verify.ps1, '
            'not subsequent Java or command-line differential checks.\n')
    text += ''.join(f"\n- `{row['test_id']}`: {skip['reason']} (allowed={skip['allowed']})"
                    for row in data.get('tests', []) for skip in row['skips'])
    text += '\n' + ''.join('\n- ' + error for error in data.get('errors', [])) + '\n'
    output.with_suffix('.md').write_text(text, encoding='utf-8')
    if summary and os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
            handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = root / 'work/ci/test-execution/report.json'
    data = dict(schema='ci-test-execution/1', accepted=False, errors=['runner-not-completed'])
    context = dict(platform=platform.system(), python=platform.python_version(),
                   collected_at=datetime.now(timezone.utc).isoformat(),
                   github={key: os.environ.get(key) for key in
                           ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB')})
    try:
        context['checkout'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8')) if os.environ.get('GITHUB_EVENT_PATH') else {}
        context['pr_head'] = event.get('pull_request', {}).get('head', {}).get('sha')
        policy_path = root / 'tools/ci/test-skip-allowlist.json'
        context['policy_sha256'] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
        context['test_sources'] = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted((root / 'tests').rglob('*.py'))}
        policy = load_policy(policy_path, root)
        sys.path.insert(0, str(root))
        suite = unittest.TestLoader().discover(str(root / 'tests'))
        data = execute(suite, policy, platform.system())
    except BaseException as exc:
        data['errors'] = ['runner-setup:' + type(exc).__name__ + ':' + str(exc)]
    data['context'] = context
    write_report(output, data, summary=True)
    return 0 if data['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
