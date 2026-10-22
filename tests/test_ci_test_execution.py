import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.ci_test_execution import allowed, execute, load_policy, write_report


class ExecutionReportTests(unittest.TestCase):
    def suite(self, methods, **extra):
        cls = type('Example', (unittest.TestCase,), dict(__module__='test_fixture', **methods, **extra))
        return unittest.defaultTestLoader.loadTestsFromTestCase(cls)

    def run_report(self, methods, policy=None, **extra):
        return execute(self.suite(methods, **extra), policy or {'allowances': []}, 'Linux', stream=io.StringIO())

    def allowance(self, selector='test_fixture.Example.test_skip', scope='test'):
        return {'allowances': [dict(selector=selector, scope=scope, reason='dedicated job', platforms=['Linux'])]}

    def test_real_callbacks_separate_pass_failure_error_and_skip(self):
        def fail(t): t.fail('intentional fixture')
        def error(t): raise RuntimeError('intentional fixture')
        def skip(t): t.skipTest('dedicated job')
        r = self.run_report(dict(test_pass=lambda t: None, test_fail=fail, test_error=error, test_skip=skip))
        self.assertEqual(r['discovered'], 4)
        self.assertEqual(r['started'], 4)
        self.assertEqual(r['counts'], dict(passed=1, failed=1, error=1, skipped=1))
        self.assertFalse(r['accepted'])
        self.assertIn('unlisted-skip:test_fixture.Example.test_skip', r['errors'])
        r = self.run_report(dict(test_pass=lambda t: None, test_skip=skip), self.allowance())
        self.assertTrue(r['accepted'])
        self.assertEqual(r['counts'], dict(passed=1, skipped=1))

    def test_fixture_skip_accounts_for_every_unstarted_test(self):
        def setup(cls): raise unittest.SkipTest('dedicated job')
        r = self.run_report(dict(test_one=lambda t: None, test_two=lambda t: None),
                            self.allowance('test_fixture.Example', 'class'), setUpClass=classmethod(setup))
        self.assertTrue(r['accepted'])
        self.assertEqual(r['started'], 0)
        self.assertEqual(r['counts'], dict(skipped=2))
        self.assertTrue(all(not t['started'] for t in r['tests']))
        r = self.run_report(dict(test_one=lambda t: None), setUpClass=classmethod(setup))
        self.assertFalse(r['accepted'])

    def test_fixture_error_and_teardown_failure_never_pass(self):
        def error(cls): raise RuntimeError('fixture failed')
        for hook in ('setUpClass', 'tearDownClass'):
            with self.subTest(hook=hook):
                r = self.run_report(dict(test_one=lambda t: None), **{hook: classmethod(error)})
                self.assertFalse(r['accepted'])
                self.assertEqual(r['counts'], dict(error=1))

    def test_subtest_failure_and_skip_remain_visible(self):
        def subs(t):
            for n in (1, 2):
                with t.subTest(n=n):
                    if n == 2: t.fail('subtest fixture')
        r = self.run_report(dict(test_subs=subs))
        self.assertFalse(r['accepted'])
        self.assertEqual(r['counts'], dict(failed=1))
        self.assertEqual(len([e for e in r['events'] if e['outcome'] == 'failed']), 1)
        def skip(t):
            with t.subTest(n=1): t.skipTest('dedicated job')
        r = self.run_report(dict(test_skip=skip), self.allowance())
        self.assertTrue(r['accepted'])
        self.assertEqual(r['counts'], dict(skipped=1))

    def test_expected_failure_unexpected_success_and_empty_suite_refused(self):
        def fail(t): t.fail('expected fixture')
        for method in (unittest.expectedFailure(fail), unittest.expectedFailure(lambda t: None)):
            self.assertFalse(self.run_report(dict(test_case=method))['accepted'])
        self.assertFalse(execute(unittest.TestSuite(), {'allowances': []}, 'Linux', stream=io.StringIO())['accepted'])

    def test_duplicate_identity_and_aborted_runner_refused(self):
        case = list(self.suite(dict(test_case=lambda t: None)))[0]
        r = execute(unittest.TestSuite([case, case]), {'allowances': []}, 'Linux', stream=io.StringIO())
        self.assertIn('empty-or-duplicate-discovery', r['errors'])
        def interrupt(t): raise KeyboardInterrupt()
        r = self.run_report(dict(test_case=interrupt))
        self.assertFalse(r['accepted'])
        self.assertIn('runner-aborted:KeyboardInterrupt', r['errors'])

    def test_policy_requires_exact_identity_reason_platform_and_source(self):
        p = self.allowance()
        self.assertTrue(allowed(p, 'test_fixture.Example.test_skip', 'dedicated job', 'Linux'))
        for identity, reason, system in [('test_fixture.Example.test_other', 'dedicated job', 'Linux'),
                                         ('test_fixture.Example.test_skip', 'different', 'Linux'),
                                         ('test_fixture.Example.test_skip', 'dedicated job', 'Windows')]:
            self.assertFalse(allowed(p, identity, reason, system))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'tests').mkdir()
            source = root / 'tests/test_fixture.py'; source.write_text('# fixture\n')
            p.update(schema='ci-test-skip-policy/1', sources={'tests/test_fixture.py': hashlib.sha256(source.read_bytes()).hexdigest()})
            p['allowances'][0]['rationale'] = 'Separate environment'
            path = root / 'policy.json'; path.write_text(json.dumps(p))
            self.assertEqual(load_policy(path, root), p)
            source.write_text('# changed\n')
            with self.assertRaisesRegex(ValueError, 'source-changed'): load_policy(path, root)

    def test_cli_discovery_import_error_emits_failed_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'tests').mkdir(); (root / 'tools/ci').mkdir(parents=True)
            (root / 'tests/test_broken.py').write_text('raise ImportError("synthetic missing dependency")\n')
            (root / 'tools/ci/test-skip-allowlist.json').write_text(json.dumps(dict(schema='ci-test-skip-policy/1', sources={}, allowances=[])))
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '--no-gpg-sign', '-qm', 'fixture'], check=True)
            tool = Path(__file__).resolve().parents[1] / 'tools/ci_test_execution.py'
            env = {k: v for k, v in os.environ.items() if k != 'GITHUB_STEP_SUMMARY'}
            result = subprocess.run([sys.executable, '-B', str(tool), '--root', str(root)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((root / 'work/ci/test-execution/report.json').read_text())
            self.assertFalse(report['accepted'])
            self.assertEqual(report['counts'], {'error': 1})
            self.assertEqual(report['discovered'], 1)
            self.assertIn('tests/test_broken.py', report['context']['test_sources'])

    def test_failed_reports_have_human_readable_skip_summary(self):
        def skip(t): t.skipTest('dedicated job')
        data = self.run_report(dict(test_skip=skip))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            write_report(path, data)
            self.assertEqual(json.loads(path.read_text()), data)
            self.assertIn('Skips are not passes', path.with_suffix('.md').read_text())
            self.assertIn('allowed=False', path.with_suffix('.md').read_text())
