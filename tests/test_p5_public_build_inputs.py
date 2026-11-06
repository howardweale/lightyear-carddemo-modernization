"""Formatter component tests using a synthetic report, never a pilot receipt."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.ci.p5_public_build_inputs import CASE, WORKER, ROLES, FAILED_STDOUT, compile_requests


class PublicBuildInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        source = Path(__file__).resolve().parents[1]
        (self.root / WORKER).parent.mkdir(parents=True)
        shutil.copyfile(source / WORKER, self.root / WORKER)
        self.order = json.loads((source / 'tests/fixtures/p5_public/human-clean-control/work-order.json').read_bytes())
        self.order['id'] = CASE
        self.order['goal'] = 'Repair the public arithmetic fixture using its unchanged gate.'
        self.order['non_goals'] = ['No external models, customer data or production qualification.']
        self.order['scope']['allowed_paths'] = [WORKER]
        self.order['policy']['max_model_calls'] = 3
        self.order['acceptance']['gates'][0]['command'] = ['python3', WORKER]
        self.report = dict(status='failed', gates=[dict(id='public-arithmetic', command=['python3', WORKER],
            status='failed', exit_code=1, timed_out=False, stdout=FAILED_STDOUT, stderr='',
            output_sha256=sha256(FAILED_STDOUT.encode() + b'\0').hexdigest(), expose_output_to_builder=False)])
        self.env = patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_native_sequence_formats_three_requests_without_execution(self):
        before = (self.root / WORKER).read_bytes()
        with (patch('subprocess.run', side_effect=AssertionError('no process')),
              patch('subprocess.check_output', side_effect=AssertionError('no process')),
              patch('lightyear_factory.agents.ModelAgentSet._provider_for', side_effect=AssertionError('no provider')),
              patch('lightyear_factory.orchestrator.FactoryOrchestrator.run', side_effect=AssertionError('no controller'))):
            value = compile_requests(self.root, self.order, self.report)
        self.assertEqual([s['role'] for s in value['public_outputs']['steps']], list(ROLES))
        self.assertEqual(value['requests'][1]['payload']['attempt'], 0)
        self.assertEqual(value['requests'][2]['payload']['attempt'], 1)
        self.assertEqual(value['provider_calls'], 0)
        for name in ('execution_authorized', 'controller_executed', 'baseline_origin_verified',
                     'signature_created', 'nonce_consumed', 'qualifies_for_factory_receipt'):
            self.assertIs(value[name], False)
        self.assertEqual((self.root / WORKER).read_bytes(), before)

    def test_native_envelope_and_each_request_match_exact_output_plan(self):
        from lightyear_factory.gates import builder_failure_view
        from lightyear_factory.orchestrator import FactoryOrchestrator
        from lightyear_execution.public_drill_runtime import match_invocation
        value = compile_requests(self.root, self.order, self.report)
        steps = value['public_outputs']['steps']
        expected = FactoryOrchestrator._failure_envelope(builder_failure_view(self.report), steps[1]['response_content'])
        self.assertEqual(value['requests'][2]['payload']['public_failure'], expected)
        self.assertNotIn('stdout', value['public_baseline']['gates'][0])
        for index, (step, request) in enumerate(zip(steps, value['requests']), 1):
            self.assertEqual(match_invocation(step, index, step['role'], **request), request)
            altered = deepcopy(request)
            altered['payload']['unreviewed'] = True
            with self.assertRaisesRegex(ValueError, 'public-drill-unapproved-invocation'):
                match_invocation(step, index, step['role'], **altered)

    def test_baseline_substitutions_and_private_output_refuse(self):
        for key, item in [('exit_code', 0), ('exit_code', True), ('timed_out', True),
                          ('stdout', 'unreviewed'), ('stderr', 'unreviewed'),
                          ('output_sha256', '0' * 64), ('expose_output_to_builder', True)]:
            with self.subTest(key=key, item=item):
                changed = deepcopy(self.report)
                changed['gates'][0][key] = item
                with self.assertRaisesRegex(ValueError, 'public-build-exact-baseline'):
                    compile_requests(self.root, self.order, changed)
        changed = deepcopy(self.report)
        changed['status'] = 'passed'
        with self.assertRaisesRegex(ValueError, 'public-build-baseline-shape'):
            compile_requests(self.root, self.order, changed)

    def test_one_two_or_extra_calls_network_and_wrong_case_refuse(self):
        for count in (1, 2, 4):
            changed = deepcopy(self.order)
            changed['policy']['max_model_calls'] = count
            with self.assertRaisesRegex(ValueError, 'public-build-order-scope'):
                compile_requests(self.root, changed, self.report)
        changed = deepcopy(self.order)
        changed['policy']['allow_network'] = True
        with self.assertRaisesRegex(ValueError, 'public-build-order-scope'):
            compile_requests(self.root, changed, self.report)
        changed = deepcopy(self.order)
        changed['id'] = 'human-clean-control'
        with self.assertRaisesRegex(ValueError, 'public-build-order-scope'):
            compile_requests(self.root, changed, self.report)

    def test_exact_worker_drift_refuses_and_locations_do_not_change_format(self):
        other = Path(self.temp.name) / 'other'
        shutil.copytree(self.root, other)
        self.assertEqual(compile_requests(self.root, self.order, self.report),
                         compile_requests(other, self.order, self.report))
        (other / WORKER).write_bytes((other / WORKER).read_bytes() + b'# changed\n')
        with self.assertRaisesRegex(ValueError, 'public-build-exact-worker'):
            compile_requests(other, self.order, self.report)

    def test_outside_ci_refuses_before_read_or_import(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': ''}):
            with self.assertRaisesRegex(ValueError, 'public-build-ci-only'):
                compile_requests(Path(self.temp.name) / 'absent', {}, {})

    def test_exact_agreed_case_and_other_admissions_refuse(self):
        self.assertEqual(CASE, 'configured-build-control')
        self.assertEqual(WORKER, 'tests/fixtures/p5_public/human-public-build-control/worker.py')
        value = compile_requests(self.root, self.order, self.report)
        self.assertEqual(value['public_outputs']['case_id'], 'configured-build-control')
        self.assertEqual([s['role'] for s in value['public_outputs']['steps']],
                         ['planner', 'failure_analyst', 'builder'])
        for case in ('human-clean-control', 'tower-unreachable', 'workspace-changed', 'kill-count-before-reserve', 'kill-count-after-reserve', 'kill-generation-before-reserve', 'kill-generation-after-reserve', 'kill-generation-after-observed', 'worker-network-positive-before', 'worker-network-denied', 'worker-network-positive-after', 'wall-and-window', 'budget-count-preflight', 'budget-count-overrun', 'budget-count-unknown', 'budget-generation-preflight', 'answer-fragment', 'duplicate-attempt', 'human-public-build-control'):
            with self.subTest(case=case):
                changed = deepcopy(self.order)
                changed['id'] = case
                with self.assertRaisesRegex(ValueError, 'public-build-order-scope'):
                    compile_requests(self.root, changed, self.report)
