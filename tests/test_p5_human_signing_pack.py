"""Unsigned signing-pack tests; CI only, no key, signature or admission proof."""
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.ci.p5_human_signing_pack import build_unsigned_documents, prepare, DOCUMENTS, FIXTURES


class HumanSigningPackTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        from lightyear_factory.contracts import WorkOrder
        from lightyear_execution.contracts import ExecutionPolicy
        root = Path(__file__).resolve().parents[1]
        self.order = WorkOrder.load(root / FIXTURES / 'work-order.json')
        self.policy = ExecutionPolicy.load(root / DOCUMENTS / 'execution-policy.json')
        self.bound = {name: dict(path=DOCUMENTS+filename, sha256='b'*64) for name,filename in
            [('scope','scope.json'),('freeze','freeze.json'),('workspace','workspace.json'),('execution_policy','execution-policy.json')]}
        self.outputs = dict(path=DOCUMENTS+'public-outputs.json', sha256='c'*64)
        self.isolation = dict(path=DOCUMENTS+'public-isolation.json', sha256='d'*64)
        self.window = {'start':'2026-10-28T10:00:00-07:00', 'end':'2026-10-28T11:00:00-07:00'}

    def build(self, **changes):
        args = dict(order=self.order, policy=self.policy, executable='a'*40, bound=self.bound,
            outputs=self.outputs, isolation=self.isolation, observer_hash='e'*64, worker_hash='f'*64,
            window=self.window, nonce_sha256='1'*64)
        args.update(changes)
        return build_unsigned_documents(**args)

    def test_native_contract_and_exact_role_input_window_nonce_bindings(self):
        from lightyear_control_tower.factory_policy import validate_contract
        from lightyear_factory.contracts import canonical_hash
        plan, contract = self.build()
        self.assertEqual(validate_contract(contract, check_evidence=False), contract)
        self.assertEqual(contract['details']['request_seal'], canonical_hash(plan, {'content_sha256'}))
        self.assertEqual(plan['drill_admission']['nonce_sha256'], '1'*64)
        self.assertEqual(plan['drill_admission']['ci']['run_attempt'], 1)
        self.assertEqual(plan['drill_admission']['external_model_calls'], 0)
        self.assertTrue(plan['drill_admission']['stub_only'])
        self.assertEqual(plan['roles'], {r:{'provider':'p5-scripted','model':'p5-stub-2026-10-28'}
                                      for r in ('planner','builder','analyst')})
        self.assertEqual(len(contract['sources']), 6)
        for row in contract['sources']:
            self.assertEqual(set(row), {'path','sha256','commit'})
            self.assertEqual(row['commit'], plan['executable_commit'])
            self.assertTrue(row['path'].startswith(DOCUMENTS))
        self.assertNotIn('proof', plan)
        self.assertNotIn('signature', plan)

    def test_window_exceeding_policy_naive_reversed_or_empty_refuses(self):
        for window in [dict(self.window,end='2026-10-28T11:00:01-07:00'),
                       dict(self.window,start='2026-10-28T10:00:00'),
                       dict(self.window,end=self.window['start']),
                       dict(self.window,end='2026-10-28T09:00:00-07:00')]:
            with self.subTest(window=window), self.assertRaises(ValueError): self.build(window=window)

    def test_wrong_or_missing_public_source_is_refused(self):
        bad = copy.deepcopy(self.bound); del bad['scope']
        with self.assertRaises(ValueError): self.build(bound=bad)
        bad = copy.deepcopy(self.bound); bad['scope']['path'] = FIXTURES+'scope.json'
        with self.assertRaises(ValueError): self.build(bound=bad)
        with self.assertRaises(ValueError): self.build(outputs=dict(self.outputs,commit='a'*40))
        with self.assertRaises(ValueError): self.build(isolation=dict(self.isolation,sha256='bad'))

    def test_nonce_and_executable_changes_produce_distinct_seals(self):
        baseline = self.build()[0]['content_sha256']
        self.assertNotEqual(baseline, self.build(nonce_sha256='2'*64)[0]['content_sha256'])
        self.assertNotEqual(baseline, self.build(executable='b'*40)[0]['content_sha256'])
        for bad in ('', 'a'*39, 'A'*40):
            with self.subTest(executable=bad), self.assertRaises(ValueError): self.build(executable=bad)
        with self.assertRaises(ValueError): self.build(nonce_sha256='secret-text')

    def test_draft_construction_cannot_call_provider_process_or_signer(self):
        with patch('subprocess.check_output', side_effect=AssertionError('no process')):
            plan, contract = self.build()
        self.assertEqual(contract['kind'], 'engineering-run-approval')
        self.assertEqual(plan['caps']['max_attempts'], 1)
        self.assertEqual(plan['caps']['max_model_calls'], 1)

    def test_outside_ci_refuses_before_source_or_process_access(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':''}), patch('subprocess.check_output', side_effect=AssertionError('no process')):
            with self.assertRaisesRegex(ValueError, 'signing-pack-ci-only'):
                prepare(Path('absent'), 'a'*40, self.window, '1'*64)


if __name__ == '__main__': unittest.main()
