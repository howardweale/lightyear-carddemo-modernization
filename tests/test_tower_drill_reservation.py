"""CI-only algorithm negatives, not human-proof or real-GitHub execution proof."""
import copy
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.tower_drill_reservation import (
    _GitHubAPI, _PREFIX, _REPOSITORY, _consume_verified_plan, reserve_human_drill_plan,
)


class SyntheticAPI:
    def __init__(self):
        self.calls = []
        self.tags = {}
        self.refs = {}
        self.run = dict(id=123, run_attempt=1, event='pull_request', status='in_progress',
                        head_sha='d'*40, head_repository={'full_name': _REPOSITORY}, workflow_id=9)
        self.jobs = dict(total_count=1, jobs=[dict(id=456, name='disposable-drills',
                        status='in_progress', head_sha='d'*40, run_id=123)])
        self.workflow = {'path': '.github/workflows/p5-factory-drills.yml'}
        self.ambiguous_ref = False
        self.corrupt_readback = False

    def request(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if method == 'GET' and path == _PREFIX + '/actions/runs/123':
            return copy.deepcopy(self.run)
        if method == 'GET' and path == _PREFIX + '/actions/workflows/9':
            return copy.deepcopy(self.workflow)
        if method == 'GET' and path.endswith('/attempts/1/jobs?per_page=100'):
            return copy.deepcopy(self.jobs)
        if method == 'POST' and path == _PREFIX + '/git/tags':
            oid = format(len(self.tags)+1, '040x')
            tag = dict(sha=oid, tag=payload['tag'], message=payload['message'],
                       object={'type': payload['type'], 'sha': payload['object'],
                               'url': 'https://api.github.com' + _PREFIX + '/git/commits/' + payload['object']})
            self.tags[oid] = tag
            return copy.deepcopy(tag)
        if method == 'POST' and path == _PREFIX + '/git/refs':
            if payload['ref'] in self.refs:
                raise ExecutionContractError('synthetic-existing-ref')
            ref = dict(ref=payload['ref'], object={'sha': payload['sha'], 'type': 'tag'})
            self.refs[payload['ref']] = ref
            if self.ambiguous_ref:
                raise ExecutionContractError('synthetic-timeout-after-create')
            return copy.deepcopy(ref)
        if method == 'GET' and '/git/ref/tags/' in path:
            return copy.deepcopy(self.refs['refs/tags/' + path.rsplit('/', 1)[1]])
        if method == 'GET' and '/git/tags/' in path:
            result = copy.deepcopy(self.tags[path.rsplit('/', 1)[1]])
            if self.corrupt_readback:
                result['message'] += 'changed'
            return result
        raise AssertionError((method, path))


class TowerDrillReservationTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        guard = patch('lightyear_execution.tower_drill_reservation.subprocess.run',
                      side_effect=AssertionError('actual subprocess forbidden in synthetic tests'))
        guard.start(); self.addCleanup(guard.stop)
        self.api = SyntheticAPI()
        self.env = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY=_REPOSITORY,
                        GITHUB_EVENT_NAME='pull_request', GITHUB_RUN_ATTEMPT='1',
                        GITHUB_RUN_ID='123', GITHUB_JOB='disposable-drills')
        self.review = dict(status='verified-plan-only', execution_authorized=False,
                           nonce_consumed=False, drill_binding=dict(case_id='clean-control',
                           nonce_sha256='c'*64, work_order_sha256='a'*64,
                           execution_policy_sha256='b'*64, ci=dict(repository=_REPOSITORY,
                               workflow_ref=_REPOSITORY+'/.github/workflows/p5-factory-drills.yml@'+'e'*40,
                               job='disposable-drills', run_attempt=1)),
                           verified_model_admission=dict(executable_commit='d'*40,
                               plan_sha256='1'*64, decision_sha256='2'*64, trusted_journal_head='3'*64))

    def reserve(self, reverify=None):
        return _consume_verified_plan(self.review, self.api, self.env,
                                      reverify or (lambda: copy.deepcopy(self.review)))

    def writes(self):
        return [row for row in self.api.calls if row[0] != 'GET']

    def test_consumption_binds_every_identity_and_never_grants_execution(self):
        result = self.reserve()
        self.assertEqual(result['status'], 'consumed-only')
        self.assertIs(result['execution_authorized'], False)
        self.assertIs(result['admission_receipt_issued'], False)
        record = result['record']
        self.assertEqual(record['ci'], dict(repository=_REPOSITORY, run_id=123, run_attempt=1,
            job='disposable-drills', job_id=456, workflow_id=9, head_sha='d'*40,
            workflow_ref=self.review['drill_binding']['ci']['workflow_ref']))
        for field in ('plan_sha256', 'decision_sha256', 'trusted_journal_head'):
            self.assertEqual(record[field], self.review['verified_model_admission'][field])
        for field in ('case_id', 'nonce_sha256', 'work_order_sha256', 'execution_policy_sha256'):
            self.assertEqual(record[field], self.review['drill_binding'][field])
        self.assertIs(record['consumed_before_execution'], True)
        self.assertEqual([row[1] for row in self.writes()], [_PREFIX+'/git/tags', _PREFIX+'/git/refs'])
        self.assertEqual(json.loads(next(iter(self.api.tags.values()))['message']), record)

    def test_existing_claim_refuses_even_same_owner_and_changed_plan(self):
        first = self.reserve()
        original = copy.deepcopy(self.api.refs)
        for change in (False, True):
            if change:
                self.review['verified_model_admission']['plan_sha256'] = '4'*64
            with self.subTest(changed_plan=change), self.assertRaises(ExecutionContractError):
                self.reserve()
        self.assertEqual(self.api.refs, original)
        self.assertEqual(next(iter(self.api.refs)), first['ref'])
        self.assertEqual(len([x for x in self.writes() if x[1].endswith('/git/refs')]), 3)
        self.assertTrue(all(x[0] == 'POST' for x in self.writes()))

    def test_ambiguous_create_stops_once_and_never_resumes(self):
        self.api.ambiguous_ref = True
        with self.assertRaisesRegex(ExecutionContractError, 'timeout-after-create'):
            self.reserve()
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(len(self.api.refs), 1)
        self.assertEqual(self.api.calls[-1][1], _PREFIX+'/git/refs')
        self.api.ambiguous_ref = False
        with self.assertRaisesRegex(ExecutionContractError, 'existing-ref'):
            self.reserve()
        self.assertEqual(len(self.api.refs), 1)

    def test_concurrent_creates_have_one_winner_in_atomic_service_model(self):
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        class AtomicAPI(SyntheticAPI):
            def request(inner, method, path, payload=None):
                if method == 'POST' and path == _PREFIX+'/git/refs':
                    barrier.wait(timeout=10)
                with lock:
                    return super().request(method, path, payload)

        self.api = AtomicAPI()

        def claim():
            try:
                return self.reserve()['status']
            except ExecutionContractError:
                return 'refused'

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim(), range(2)))
        self.assertCountEqual(results, ['consumed-only', 'refused'])
        self.assertEqual(len(self.api.refs), 1)
        self.assertEqual(len([x for x in self.writes() if x[1].endswith('/git/refs')]), 2)

    def test_environment_and_live_run_mismatches_write_nothing(self):
        for field, value in {'GITHUB_REPOSITORY': 'fork/repo', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                             'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_RUN_ID': '../123',
                             'GITHUB_ACTIONS': 'false', 'GITHUB_JOB': 'other'}.items():
            saved = dict(self.env); self.env[field] = value
            with self.subTest(field=field), self.assertRaises(ExecutionContractError):
                self.reserve()
            self.env = saved
        for field, value in {'event': 'pull_request_target', 'run_attempt': True,
                             'head_sha': 'f'*40, 'status': 'completed',
                             'head_repository': {'full_name': 'fork/repo'}, 'id': True}.items():
            saved = copy.deepcopy(self.api.run); self.api.run[field] = value
            with self.subTest(field=field), self.assertRaises(ExecutionContractError):
                self.reserve()
            self.api.run = saved
        self.assertEqual(self.writes(), [])

    def test_workflow_job_and_incomplete_inventory_refuse_before_write(self):
        self.api.workflow['path'] = '.github/workflows/unreviewed.yml'
        with self.assertRaises(ExecutionContractError):
            self.reserve()
        self.api.workflow['path'] = '.github/workflows/p5-factory-drills.yml'
        for mutate in (
            lambda x: x.update(total_count=101),
            lambda x: (x['jobs'].append(copy.deepcopy(x['jobs'][0])), x.update(total_count=2)),
            lambda x: x['jobs'][0].update(run_attempt=True),
            lambda x: x['jobs'][0].update(status='completed'),
            lambda x: x['jobs'][0].update(head_sha='f'*40),
            lambda x: x['jobs'][0].update(run_id=124),
        ):
            saved = copy.deepcopy(self.api.jobs); mutate(self.api.jobs)
            with self.subTest(mutation=mutate), self.assertRaises(ExecutionContractError):
                self.reserve()
            self.api.jobs = saved
        self.assertEqual(self.writes(), [])

    def test_trust_change_before_or_after_consumption_never_grants(self):
        changed = copy.deepcopy(self.review)
        changed['verified_model_admission']['trusted_journal_head'] = '5'*64
        with self.assertRaisesRegex(ExecutionContractError, 'plan-or-trust-changed'):
            self.reserve(lambda: changed)
        self.assertEqual(self.writes(), [])
        checks = iter([self.review, changed])
        with self.assertRaisesRegex(ExecutionContractError, 'stop-consumed'):
            self.reserve(lambda: next(checks))
        self.assertEqual(len(self.api.refs), 1)
        self.assertEqual(len(self.writes()), 2)

    def test_corrupt_readback_leaves_claim_consumed_and_refuses(self):
        self.api.corrupt_readback = True
        with self.assertRaisesRegex(ExecutionContractError, 'readback-stop'):
            self.reserve()
        self.assertEqual(len(self.api.refs), 1)
        self.assertEqual(len(self.writes()), 2)

    def test_public_entry_rejects_fake_admission_before_any_api_or_git(self):
        with patch('lightyear_execution.tower_drill_reservation._GitHubAPI') as api:
            with self.assertRaises(ExecutionContractError):
                reserve_human_drill_plan(SimpleNamespace(status='passed'), object(), object())
            api.assert_not_called()

    def test_transport_errors_are_sanitized_and_never_retried(self):
        with patch('lightyear_execution.tower_drill_reservation.subprocess.run',
                   return_value=SimpleNamespace(returncode=1, stdout=b'', stderr=b'synthetic-sensitive-error')) as run:
            with self.assertRaisesRegex(ExecutionContractError, '^drill-reservation-api-failed-stop-no-retry$'):
                _GitHubAPI().request('POST', _PREFIX+'/git/refs', {'ref': 'synthetic'})
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
