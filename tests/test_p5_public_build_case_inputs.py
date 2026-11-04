"""CI-only input consistency; synthetic baseline data is not execution evidence."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest

from lightyear_factory.contracts import WorkOrder
from lightyear_execution.contracts import ExecutionPolicy
from lightyear_execution.human_drill_dispatch import validate_public_domain
from tools.ci.p5_public_build_inputs import compile_requests, FAILED_STDOUT


class PublicBuildCaseInputTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.source = Path(__file__).resolve().parents[1]
        self.prefix = 'tests/fixtures/p5_public/configured-build-control/'
        self.worker = 'tests/fixtures/p5_public/human-public-build-control/worker.py'
        self.order_path = self.source / (self.prefix + 'work-order.json')
        self.order_document = json.loads(self.order_path.read_bytes())
        self.order = WorkOrder.load(self.order_path)
        self.policy_path = self.source / (self.prefix + 'execution-policy.json')
        self.policy = ExecutionPolicy.load(self.policy_path)
        self.manifest = json.loads((self.source / (self.prefix + 'workspace.json')).read_bytes())

    def test_exact_public_inputs_and_worker_scope(self):
        for path, expected in {'tests/fixtures/p5_public/configured-build-control/work-order.json': '6549f768bf938bb21e9e0fcb22b5d150cd0abb519ca31445df67c8370504402e', 'tests/fixtures/p5_public/configured-build-control/execution-policy.json': '27914ddff75495d7b0e21249cef2d596fad25bbcd816ba922044bfc2368b9571', 'tests/fixtures/p5_public/configured-build-control/workspace.json': 'eef36a1186dae47687e1b5bb4c8ca5a9e1c0b1025a24593b1bc0e69ced475cfb'}.items():
            self.assertEqual(sha256((self.source / path).read_bytes()).hexdigest(), expected)
        self.assertEqual(self.order.order_id, 'configured-build-control')
        self.assertEqual(self.order.max_model_calls, 3)
        self.assertEqual(self.order.max_attempts, 1)
        self.assertTrue(self.order.baseline_first)
        self.assertFalse(self.order.allow_network)
        self.assertEqual(self.order.allowed_paths, (self.worker,))
        self.assertEqual(self.order.gates[0].command, ('python3', self.worker))
        self.assertFalse(self.order.gates[0].expose_output_to_builder)
        self.assertEqual(self.manifest, {self.worker: 'db4d559f1badcf6a6473d6ade51fd463f91b814f67d1a7b3bc20f31076d3d47a'})
        self.assertEqual(sha256((self.source / self.worker).read_bytes()).hexdigest(), 'db4d559f1badcf6a6473d6ade51fd463f91b814f67d1a7b3bc20f31076d3d47a')
        self.assertIsNone(validate_public_domain(self.order, self.manifest,
            'docs/factory/p5-human-clean-control/configured-build-control/outputs.json',
            'docs/factory/p5-human-clean-control/configured-build-control/isolation.json'))

    def test_policy_changes_only_case_identity(self):
        original = json.loads((self.source / 'tests/fixtures/p5_public/human-clean-control/execution-policy.json').read_bytes())
        changed = json.loads(self.policy_path.read_bytes())
        self.assertEqual(changed['id'], 'lightyear:public:configured-build-control')
        changed['id'] = original['id']
        self.assertEqual(changed, original)
        self.assertFalse(self.policy.allowed_secret_names)
        self.assertEqual(dict(self.policy.role_actions), {
            'builder': ('factory:build',), 'failure_analyst': ('factory:analyze-failure',),
            'planner': ('factory:plan',), 'verifier': ('factory:verify',)})

    def test_three_role_formatter_accepts_exact_input_without_claiming_execution(self):
        report = dict(status='failed', gates=[dict(id='public-arithmetic',
            command=['python3', self.worker], status='failed', exit_code=1, timed_out=False,
            stdout=FAILED_STDOUT, stderr='', expose_output_to_builder=False,
            output_sha256=sha256(FAILED_STDOUT.encode() + b'\0').hexdigest())])
        value = compile_requests(self.source, self.order_document, report)
        self.assertEqual(value['public_outputs']['case_id'], 'configured-build-control')
        self.assertEqual([step['role'] for step in value['public_outputs']['steps']],
                         ['planner', 'failure_analyst', 'builder'])
        self.assertEqual(value['work_order_sha256'], self.order.content_sha256)
        self.assertEqual(value['provider_calls'], 0)
        for key in ('controller_executed', 'baseline_origin_verified', 'execution_authorized',
                    'signature_created', 'nonce_consumed', 'qualifies_for_factory_receipt'):
            self.assertIs(value[key], False)
        swapped = deepcopy(self.order_document)
        swapped['id'] = 'human-clean-control'
        with self.assertRaisesRegex(ValueError, 'public-build-order-scope'):
            compile_requests(self.source, swapped, report)
