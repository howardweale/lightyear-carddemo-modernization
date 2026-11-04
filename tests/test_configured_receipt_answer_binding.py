"""CI-only untrusted policy/binding relationships; no proof or admission."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest

from lightyear_factory.contracts import WorkOrder
from lightyear_execution.contracts import ExecutionContractError, ExecutionPolicy
from lightyear_execution.configured_receipt_policy import (
    POLICY_ID as CONTROL_POLICY_ID, parse_configured_receipt_policy)
from lightyear_execution.configured_receipt_admission import _validate_configured_binding
from lightyear_execution.configured_receipt_answer_policy import POLICY_ID, parse_answer_receipt_policy
from lightyear_execution.configured_receipt_answer_admission import (
    _validate_answer_binding, verify_answer_receipt_plan)


class AnswerProofPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        root = Path(__file__).resolve().parents[1]
        self.document = json.loads((root / 'docs/factory/p5-human-clean-control/configured-build-control/work-order.json').read_bytes())
        self.document['id'] = 'answer-fragment'
        self.order = WorkOrder.from_dict(self.document)
        self.value = json.loads((root / 'tests/fixtures/p5_public/human-clean-control/execution-policy.json').read_bytes())
        self.value['id'] = POLICY_ID
        self.value['secrets']['allowed_names'] = ['OPENAI_API_KEY', 'FACTORY_TRANSPORT_KEY']
        self.value['identities']['roles'].update(
            provider={'actions': ['secret:lease:OPENAI_API_KEY']},
            recorder={'actions': ['secret:lease:FACTORY_TRANSPORT_KEY']})
        self.policy = parse_answer_receipt_policy(self.value)
        self.executable = 'b' * 40
        self.binding = dict(schema='factory-human-drill-admission/1', case_id='answer-fragment',
            nonce_sha256='a' * 64, work_order_sha256=self.order.content_sha256,
            execution_policy_sha256=self.policy.content_sha256,
            role_actions={role: list(actions) for role, actions in self.policy.role_actions.items()},
            ci=dict(repository='howardweale/lightyear-carddemo-modernization',
                workflow_ref='howardweale/lightyear-carddemo-modernization/.github/workflows/p5-configured-answer-main.yml@' + self.executable,
                job='answer-fragment', run_attempt=1),
            stub_only=False, external_model_calls=3, max_attempts=1)

    def test_exact_policy_roundtrip_preserves_input_without_authority(self):
        before = deepcopy(self.value)
        self.assertEqual(self.policy.to_dict(), before)
        self.assertEqual(self.value, before)
        self.assertEqual(self.policy.policy_id, POLICY_ID)
        self.assertFalse(hasattr(self.policy, 'admission_receipt'))
        self.assertFalse(hasattr(self.policy, 'lease_secret'))

    def test_policy_routes_reject_each_others_exact_ids(self):
        with self.assertRaises(ExecutionContractError):
            parse_configured_receipt_policy(self.value)
        control = deepcopy(self.value)
        control['id'] = CONTROL_POLICY_ID
        self.assertEqual(parse_configured_receipt_policy(control).to_dict(), control)
        with self.assertRaises(ExecutionContractError):
            parse_answer_receipt_policy(control)
        for parser in (ExecutionPolicy.from_dict, ExecutionPolicy.from_configured_human_dict):
            with self.assertRaises(ExecutionContractError):
                parser(self.value)

    def test_extra_scope_worker_secret_or_persistence_is_refused(self):
        for mutate in (
                lambda v: v['identities']['roles']['builder']['actions'].append('secret:lease:FACTORY_TRANSPORT_KEY'),
                lambda v: v['runtime']['allowed_environment'].append('OPENAI_API_KEY'),
                lambda v: v['runtime']['allowed_environment'].append('FACTORY_TRANSPORT_KEY'),
                lambda v: v['secrets'].update(persist_values=True)):
            value = deepcopy(self.value)
            mutate(value)
            with self.assertRaises(ExecutionContractError):
                parse_answer_receipt_policy(value)

    def test_unknown_fields_and_isolation_relaxation_are_refused(self):
        for mutate in (
                lambda v: v.update(extra=True),
                lambda v: v['isolation'].update(network_mode='host'),
                lambda v: v['admission'].update(signature_algorithm='HMAC-SHA256')):
            value = deepcopy(self.value)
            mutate(value)
            with self.assertRaises(ExecutionContractError):
                parse_answer_receipt_policy(value)

    def test_matching_binding_is_only_an_independent_copy(self):
        before = deepcopy(self.binding)
        result = _validate_answer_binding(self.binding, self.order, self.policy, self.executable)
        self.assertEqual(result, before)
        result['ci']['job'] = 'changed'
        self.assertEqual(self.binding, before)
        self.assertNotIn('status', result)
        self.assertNotIn('admission_receipt', result)
        self.assertNotIn('signature', result)

    def test_case_order_and_policy_cannot_cross_control_boundary(self):
        control_order = WorkOrder.from_dict(dict(self.document, id='configured-build-control'))
        control_policy = parse_configured_receipt_policy(dict(self.value, id=CONTROL_POLICY_ID))
        for binding, order, policy in (
                (dict(self.binding, case_id='configured-build-control'), self.order, self.policy),
                (self.binding, control_order, self.policy),
                (self.binding, self.order, control_policy)):
            with self.assertRaises(ExecutionContractError):
                _validate_answer_binding(binding, order, policy, self.executable)
        with self.assertRaises(ExecutionContractError):
            _validate_configured_binding(self.binding, self.order, self.policy, self.executable)

    def test_exact_workflow_job_attempt_and_executable_are_required(self):
        for key, value in (
                ('job', 'configured-build-control'), ('job', 'other'), ('run_attempt', True),
                ('run_attempt', 2), ('repository', 'other/repository'),
                ('workflow_ref', self.binding['ci']['workflow_ref'].replace('answer-main', 'human-main')),
                ('workflow_ref', self.binding['ci']['workflow_ref'].replace(self.executable, 'c' * 40))):
            binding = deepcopy(self.binding)
            binding['ci'][key] = value
            with self.assertRaises(ExecutionContractError):
                _validate_answer_binding(binding, self.order, self.policy, self.executable)

    def test_caps_and_boolean_substitutions_are_refused(self):
        for key, value in (('stub_only', True), ('external_model_calls', True),
                           ('external_model_calls', 0), ('max_attempts', True), ('max_attempts', 2)):
            with self.assertRaises(ExecutionContractError):
                _validate_answer_binding(dict(self.binding, **{key: value}), self.order, self.policy, self.executable)
        for order in (replace(self.order, baseline_first=False), replace(self.order, baseline_first=1),
                      replace(self.order, max_attempts=True), replace(self.order, max_model_calls=True),
                      replace(self.order, max_model_cost_usd=11.0)):
            with self.assertRaises(ExecutionContractError):
                _validate_answer_binding(self.binding, order, self.policy, self.executable)

    def test_hashes_roles_and_binding_shape_must_match(self):
        for key, value in (('nonce_sha256', 'invalid'), ('work_order_sha256', 'c' * 64),
                           ('execution_policy_sha256', 'c' * 64), ('role_actions', {}),
                           ('schema', 'other'), ('extra', True)):
            with self.assertRaises(ExecutionContractError):
                _validate_answer_binding(dict(self.binding, **{key: value}), self.order, self.policy, self.executable)

    def test_passed_mapping_cannot_enter_native_proof_review(self):
        with self.assertRaisesRegex(ExecutionContractError, 'real-verifier'):
            verify_answer_receipt_plan({'status': 'passed'}, self.order, self.policy)
