import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rebuild_main_status import collect_live_status as collect
from tools.release_status_records import (live_status_markdown as markdown, validate_live_status as validate,
    LIVE_REPOSITORY as REPOSITORY)

MAIN, HEAD = 'a'*40, 'b'*40
NOW = datetime(2026, 10, 22, 19, tzinfo=timezone.utc)


class LiveStatusTests(unittest.TestCase):
    def fixture(self, state='success', missing=False, race=False, wrong_head=False):
        calls = []
        pr = dict(number=362, state='closed', merged=True, base=dict(ref='main'),
                  head=dict(sha=HEAD, repo=dict(full_name=REPOSITORY)),
                  html_url='https://github.com/'+REPOSITORY+'/pull/362')
        def api(route):
            calls.append(route)
            if route == 'git/ref/heads/main':
                return dict(object=dict(sha='c'*40 if race and calls.count(route)>1 else MAIN))
            if route == 'pulls/362':
                return copy.deepcopy(pr)
            head = route.split('/')[1]
            rows = [] if missing else [dict(id=1, name='required-ci', app=dict(id=15368),
                head_sha='c'*40 if wrong_head else head,
                status='in_progress' if state=='in_progress' else 'completed',
                conclusion=None if state=='in_progress' else state,
                html_url='https://github.com/'+REPOSITORY+'/actions/runs/1/job/1')]
            return dict(total_count=len(rows), check_runs=rows)
        return api, calls

    def test_current_heads_and_clock_are_bound_without_writes(self):
        api, calls = self.fixture()
        value = collect(api, MAIN, now=NOW)
        self.assertEqual(MAIN, value['main']['head'])
        self.assertEqual(HEAD, value['pr362']['required']['head'])
        self.assertEqual(NOW.isoformat(), value['checked_at'])
        self.assertIn('success', '\n'.join(markdown(value)))
        self.assertEqual(6, len(calls))

    def test_pending_failed_missing_and_wrong_head_never_borrow_green(self):
        for state in ('in_progress', 'failure', 'cancelled'):
            api, _ = self.fixture(state=state)
            report = collect(api, MAIN, now=NOW)
            self.assertEqual(state, report['main']['state'])
            self.assertNotIn('[success]', '\n'.join(markdown(report)))
        api, _ = self.fixture(missing=True)
        self.assertIn('absent (unproved)', '\n'.join(markdown(collect(api, MAIN, now=NOW))))
        for options in ({'race':True}, {'wrong_head':True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                collect(self.fixture(**options)[0], MAIN, now=NOW)

    def test_forged_state_and_unzoned_clock_are_refused(self):
        report = collect(self.fixture()[0], MAIN, now=NOW)
        for change in ('state', 'clock', 'pr_head'):
            bad = copy.deepcopy(report)
            if change == 'state':
                bad['main']['state'] = 'in_progress'
            elif change == 'clock':
                bad['checked_at'] = '2026-10-22T19:00:00'
            else:
                bad['pr362']['head'] = 'c'*40
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate(bad)

    def test_live_clock_changes_days_and_current_block_preserves_historical_evidence(self):
        from tools.release_status_records import load, render
        from tools.check_posttran_handoff import timing
        model = load()
        prior = copy.deepcopy(model['delivery'])
        model['live_ci'] = collect(self.fixture(state='in_progress')[0], MAIN, now=NOW)
        value, text = render(model)
        self.assertIn('Current CI observation', text)
        self.assertIn('#362', text)
        self.assertEqual(timing(model['phase2'], NOW)['days_remaining'], value['phase2']['days_remaining'])
        self.assertEqual(NOW.isoformat(), value['phase2']['evaluated_at'])
        self.assertEqual(prior, model['delivery'])
        self.assertEqual(prior, value['delivery'])
        self.assertIn('as of 2026-10-17', text)

    def test_renderer_uses_one_captured_input_for_both_generations(self):
        from tools.build_factory_current_status import generate
        report = collect(self.fixture()[0], MAIN, now=NOW)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'snapshot.json'
            path.write_text(json.dumps(report))
            with patch.dict('os.environ', LIGHTYEAR_FACTORY_LIVE_STATUS=str(path)):
                first = generate()
                self.assertEqual(first, generate())
                self.assertEqual(report, first[0]['live_ci'])

    def test_rebuild_collects_after_checkout_before_render_and_aborts_on_read_failure(self):
        from tools.rebuild_main_status import rebuild
        events = []
        def command(*args):
            if args == ('rev-parse', 'FETCH_HEAD'):
                return MAIN
            if args[:1] == ('checkout',):
                events.append('checkout')
            return ''
        def observe(source, api):
            self.assertEqual(MAIN, source)
            events.append('observe')
        result = rebuild(repository=REPOSITORY, command=command, render=lambda:events.append('render'),
                         api=lambda route:self.fail('unexpected publication'), observe=observe)
        self.assertEqual('unchanged', result['state'])
        self.assertEqual(['checkout', 'observe', 'render'], events)
        def refused(source, api):
            raise RuntimeError('read failed')
        with self.assertRaisesRegex(RuntimeError, 'read failed'):
            rebuild(repository=REPOSITORY, command=command, render=lambda:self.fail('render after refusal'),
                    api=lambda route:self.fail('write after refusal'), observe=refused)

    def test_collector_refuses_invalid_api_fields_and_clock_before_serialization(self):
        for field in ('pr_state', 'pr_url', 'check_id', 'check_url'):
            api, _ = self.fixture()
            def changed(route):
                value = api(route)
                if route == 'pulls/362':
                    if field == 'pr_state':
                        value['state'] = 'invented'
                    if field == 'pr_url':
                        value['html_url'] = 'https://example.invalid/pull/362'
                elif route.startswith('commits/'):
                    if field == 'check_id':
                        value['check_runs'][0]['id'] = '1'
                    if field == 'check_url':
                        value['check_runs'][0]['html_url'] = 'https://example.invalid/run/1'
                return value
            with self.subTest(field=field), self.assertRaises(ValueError):
                collect(changed, MAIN, now=NOW)
        with self.assertRaisesRegex(ValueError, 'live-status-clock-zone'):
            collect(self.fixture()[0], MAIN, now=NOW.replace(tzinfo=None))
        self.assertEqual(collect(self.fixture()[0], MAIN, now=NOW),
                         validate(collect(self.fixture()[0], MAIN, now=NOW)))
