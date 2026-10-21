"""Offline CI fixtures for complete stranded-work reporting and one issue."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
import subprocess
from unittest.mock import patch
from tools.ci.stranded_work import GitHub, MARKER, audit, markdown, update_issue

MAIN = 'a'*40
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)


def pr(number, base='branch', merged='2026-10-18T12:00:00Z'):
    return dict(number=number, base={'ref': base}, merged_at=merged,
        head={'sha': 'b'*40}, merge_commit_sha='c'*40, html_url=f'https://example.test/pull/{number}')


class Fake:
    def __init__(self):
        self.prs = [pr(1), pr(2, 'main'), pr(3, merged=None), pr(4, merged='2026-10-01T12:00:00Z')]
        self.commits = {1: [{'sha': 'd'*40}, {'sha': 'e'*40}]}
        self.states = {'d'*40: dict(status='behind', ahead_by=0), 'e'*40: dict(status='ahead', ahead_by=1)}
        self.issues = []; self.writes = []; self.refs = [MAIN, MAIN]

    def request(self, route, method='GET', data=None):
        if method != 'GET':
            self.writes.append((route, method, data)); return dict(number=10, **data)
        if route == 'git/ref/heads/main': return {'object': {'sha': self.refs.pop(0)}}
        if route.startswith('pulls/'):
            detail = deepcopy(next(p for p in self.prs if p['number'] == int(route.split('/')[1])))
            detail['commits'] = 2
            return detail
        return self.states[route.rsplit('...', 1)[1]]

    def pages(self, route):
        if route.startswith('pulls?'): return deepcopy(self.prs)
        if route.startswith('issues?'): return deepcopy(self.issues)
        return deepcopy(self.commits[int(route.split('/')[1])])


class StrandedWorkTests(unittest.TestCase):
    def test_only_recent_non_main_missing_commits_are_reported(self):
        client = Fake(); report = audit(client, NOW)
        self.assertTrue(report['complete']); self.assertEqual(1, report['scanned_merged_non_main'])
        self.assertEqual(['e'*40], report['stranded'][0]['unreachable_commits'])
        self.assertEqual([], client.writes)

    def test_reachable_stack_is_clear_and_text_changes(self):
        before = audit(Fake(), NOW); client = Fake(); client.states['e'*40] = dict(status='identical', ahead_by=0)
        after = audit(client, NOW)
        self.assertEqual([], after['stranded']); self.assertNotEqual(markdown(before), markdown(after))
        self.assertIn('None.', markdown(after))

    def test_window_boundary_is_inclusive_and_future_is_excluded(self):
        client = Fake(); client.prs = [pr(1, merged='2026-10-05T14:00:00Z'), pr(5, merged='2026-10-20T12:00:00Z')]
        self.assertEqual(1, audit(client, NOW)['scanned_merged_non_main'])

    def test_main_movement_incomplete_or_duplicate_input_refused(self):
        for kind in ('moved', 'empty', 'duplicate-pr', 'duplicate-commit'):
            client = Fake()
            if kind == 'moved': client.refs[1] = 'f'*40
            elif kind == 'empty': client.commits[1] = []
            elif kind == 'duplicate-pr': client.prs.append(pr(1))
            else: client.commits[1].append({'sha': 'e'*40})
            with self.subTest(kind=kind), self.assertRaises(ValueError): audit(client, NOW)

    def test_api_commit_cap_and_head_drift_are_refused(self):
        for kind in ('truncated', 'bad-count', 'head-drift', 'base-drift'):
            client = Fake(); original = client.request
            def request(route, method='GET', data=None):
                result = original(route, method, data)
                if route == 'pulls/1':
                    if kind == 'truncated': result['commits'] = 251
                    elif kind == 'bad-count': result['commits'] = True
                    elif kind == 'head-drift': result['head']['sha'] = 'f'*40
                    else: result['base']['ref'] = 'main'
                return result
            client.request = request
            with self.subTest(kind=kind), self.assertRaises(ValueError): audit(client, NOW)

    def test_comparison_failure_is_not_treated_as_reachable(self):
        for value in ({'status': 'unknown', 'ahead_by': 0}, {'status': 'behind', 'ahead_by': 1},
                      {'status': 'ahead', 'ahead_by': 0}, {'status': 'ahead', 'ahead_by': True}):
            client = Fake(); client.states['e'*40] = value
            with self.subTest(value=value), self.assertRaises(ValueError): audit(client, NOW)

    def test_one_issue_created_updated_then_closed(self):
        report = audit(Fake(), NOW); client = Fake(); update_issue(client, report)
        self.assertEqual(('issues', 'POST'), client.writes[0][:2])
        client.issues = [dict(number=10, body=MARKER, state='open')]
        update_issue(client, report); self.assertEqual(('issues/10', 'PATCH'), client.writes[-1][:2])
        report['stranded'] = []; update_issue(client, report)
        self.assertEqual('closed', client.writes[-1][2]['state'])

    def test_duplicate_issue_refused_and_clean_run_does_not_open_issue(self):
        report = audit(Fake(), NOW); client = Fake()
        client.issues = [dict(number=n, body=MARKER, state='open') for n in (10, 11)]
        with self.assertRaises(ValueError): update_issue(client, report)
        client.issues = []; report['stranded'] = []
        self.assertIsNone(update_issue(client, report)); self.assertEqual([], client.writes)


class GitHubRequestTests(unittest.TestCase):
    def result(self, status=None, body='{"ok": true}', stderr=None):
        return subprocess.CompletedProcess([], 0 if status is None else 1,
            stdout=body, stderr=stderr if stderr is not None else f'gh: HTTP {status}')

    def test_transient_get_retries_then_returns_complete_json(self):
        for status in ('500', '502', '503', '504'):
            responses = [self.result(status), self.result(status, stderr=f'gh: unavailable (HTTP {status})'), self.result()]
            with self.subTest(status=status), patch('tools.ci.stranded_work.subprocess.run', side_effect=responses) as run, patch('tools.ci.stranded_work.time.sleep') as sleep:
                self.assertEqual({'ok': True}, GitHub('owner/repo').request('pulls/399'))
                self.assertEqual(3, run.call_count); self.assertEqual([((2,),), ((4,),)], [c[:1] for c in sleep.call_args_list])
                self.assertEqual(run.call_args_list[0], run.call_args_list[2])
                self.assertEqual(60, run.call_args.kwargs['timeout'])

    def test_exhaustion_fails_without_captured_output(self):
        failure = self.result('503', body='PRIVATE_BODY', stderr='PRIVATE_TOKEN (HTTP 503)')
        with patch('tools.ci.stranded_work.subprocess.run', return_value=failure) as run, patch('tools.ci.stranded_work.time.sleep') as sleep:
            with self.assertRaises(RuntimeError) as error: GitHub('owner/repo').request('pulls/399?secret=PRIVATE_QUERY')
            self.assertEqual('stranded-work-api: GET pulls/399 HTTP 503; exit 1; attempts 3', str(error.exception))
            self.assertEqual(3, run.call_count); self.assertEqual(2, sleep.call_count)

    def test_permanent_ambiguous_and_unknown_errors_do_not_retry(self):
        for stderr in ('gh: HTTP 401', 'gh: HTTP 403', 'gh: HTTP 404', 'gh: HTTP 429', 'private transport error', 'HTTP 503 HTTP 403'):
            with self.subTest(stderr=stderr), patch('tools.ci.stranded_work.subprocess.run', return_value=self.result('error', stderr=stderr)) as run, patch('tools.ci.stranded_work.time.sleep') as sleep:
                with self.assertRaises(RuntimeError): GitHub('owner/repo').request('pulls/399')
                self.assertEqual(1, run.call_count); sleep.assert_not_called()

    def test_writes_and_get_payloads_are_never_retried(self):
        for method in ('POST', 'PATCH', 'GET'):
            with self.subTest(method=method), patch('tools.ci.stranded_work.subprocess.run', return_value=self.result('503')) as run, patch('tools.ci.stranded_work.time.sleep') as sleep:
                with self.assertRaises(RuntimeError): GitHub('owner/repo').request('issues', method, {'body': 'PRIVATE_PAYLOAD'})
                self.assertEqual(1, run.call_count); sleep.assert_not_called()
                self.assertIn('--input', run.call_args.args[0])

    def test_timeout_and_invalid_json_fail_without_retry_or_body(self):
        cases = (subprocess.TimeoutExpired(['PRIVATE_COMMAND'], 60, output='PRIVATE_OUTPUT'), self.result(body='PRIVATE_JSON'))
        for case in cases:
            with self.subTest(case=type(case).__name__), patch('tools.ci.stranded_work.subprocess.run', side_effect=[case]) as run, patch('tools.ci.stranded_work.time.sleep') as sleep:
                with self.assertRaises(RuntimeError) as error: GitHub('owner/repo').request('pulls/399')
                self.assertNotIn('PRIVATE', str(error.exception)); self.assertIsNone(error.exception.__cause__)
                self.assertEqual(1, run.call_count); sleep.assert_not_called()

    def test_invalid_route_is_redacted_in_failure(self):
        with patch('tools.ci.stranded_work.subprocess.run', return_value=self.result('403')):
            with self.assertRaisesRegex(RuntimeError, 'GET redacted HTTP 403'):
                GitHub('owner/repo').request('secret\nPRIVATE')


if __name__ == '__main__': unittest.main()
