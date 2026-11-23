"""CI-only binding/parser tests; no keys, signatures or admission grants."""
import copy
import os
from types import SimpleNamespace
import unittest

from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.tower_drill_admission import _validate_drill_binding, verify_human_drill_plan


class TowerDrillPlanBindingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.order = SimpleNamespace(content_sha256='a'*64, max_attempts=1)
        self.policy = SimpleNamespace(content_sha256='b'*64, allowed_secret_names=(),
                                      role_actions={'planner': ('factory:plan',)})
        self.binding = dict(schema='factory-human-drill-admission/1', case_id='clean-control',
            nonce_sha256='c'*64, work_order_sha256='a'*64, execution_policy_sha256='b'*64,
            role_actions={'planner': ['factory:plan']}, stub_only=True, external_model_calls=0,
            max_attempts=1, ci=dict(repository='howardweale/lightyear-carddemo-modernization',
                workflow_ref='howardweale/lightyear-carddemo-modernization/.github/workflows/p5-factory-drills.yml@'+'d'*40,
                job='disposable-drills', run_attempt=1))

    def test_binding_copy_is_not_an_execution_admission(self):
        parsed = _validate_drill_binding(self.binding, self.order, self.policy)
        self.assertEqual(parsed, self.binding)
        parsed['role_actions']['planner'].append('factory:build')
        self.assertEqual(self.binding['role_actions']['planner'], ['factory:plan'])
        with self.assertRaises(ExecutionContractError):
            verify_human_drill_plan(SimpleNamespace(status='passed'), self.order, self.policy)

    def test_scope_order_nonce_and_role_changes_refuse(self):
        changes = {'stub_only': False, 'external_model_calls': True, 'max_attempts': 2,
                   'nonce_sha256': 'invalid', 'work_order_sha256': 'f'*64,
                   'execution_policy_sha256': 'f'*64, 'role_actions': {'planner': ['factory:build']}}
        for key, value in changes.items():
            mutated = copy.deepcopy(self.binding); mutated[key] = value
            with self.subTest(field=key), self.assertRaises(ExecutionContractError):
                _validate_drill_binding(mutated, self.order, self.policy)
        self.policy.allowed_secret_names = ('OPENAI_API_KEY',)
        with self.assertRaises(ExecutionContractError):
            _validate_drill_binding(self.binding, self.order, self.policy)

    def test_ci_identity_must_be_exact_and_attempt_one(self):
        for key, value in {'repository': 'fork/example', 'workflow_ref': 'main',
                           'run_attempt': True, 'job': '../other'}.items():
            mutated = copy.deepcopy(self.binding); mutated['ci'][key] = value
            with self.subTest(field=key), self.assertRaises(ExecutionContractError):
                _validate_drill_binding(mutated, self.order, self.policy)


if __name__ == '__main__':
    unittest.main()
