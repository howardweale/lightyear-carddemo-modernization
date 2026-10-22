"""Offline CI fixtures for complete stranded-work reporting and one issue."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from tools.ci.stranded_work import MARKER, audit, markdown, update_issue

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


if __name__ == '__main__': unittest.main()
