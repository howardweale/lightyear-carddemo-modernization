"""CI-only structural refusals; no fake successful proof or model execution."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

from lightyear_factory.contracts import WorkOrder
from lightyear_execution.contracts import ExecutionPolicy, ExecutionContractError
from lightyear_execution.configured_human_admission import (
    _validate_configured_binding, verify_configured_human_plan)


class ConfiguredHumanPlanBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        root = Path(__file__).resolve().parents[1]
        fixture = root / 'tests/fixtures/p5_public/human-clean-control'
        document = json.loads((fixture / 'work-order.json').read_bytes())
        document['id'] = 'configured-build-control'
        document['policy']['max_model_calls'] = 3
        document['policy']['max_model_cost_usd'] = 10.0
        self.order = WorkOrder.from_dict(document)
        policy = json.loads((fixture / 'execution-policy.json').read_bytes())
        policy['id'] = 'lightyear:configured-human:configured-build-control'
        policy['secrets']['allowed_names'] = ['OPENAI_API_KEY']
        policy['identities']['roles']['provider'] = {'actions': ['secret:lease:OPENAI_API_KEY']}
        self.policy = ExecutionPolicy.from_configured_human_dict(policy)
        self.head = '1'*40
        self.binding = dict(schema='factory-human-drill-admission/1',
            case_id='configured-build-control', nonce_sha256='2'*64,
            work_order_sha256=self.order.content_sha256,
            execution_policy_sha256=self.policy.content_sha256,
            role_actions={r:list(a) for r,a in self.policy.role_actions.items()},
            ci=dict(repository='howardweale/lightyear-carddemo-modernization',
                workflow_ref='howardweale/lightyear-carddemo-modernization/.github/workflows/p5-factory-drills.yml@'+self.head,
                job='configured-build-control', run_attempt=1),
            stub_only=False, external_model_calls=3, max_attempts=1)

    def validate(self, value):
        return _validate_configured_binding(value, self.order, self.policy, self.head)

    def test_structural_copy_is_not_admission_and_does_not_alias_input(self):
        result = self.validate(self.binding)
        self.assertEqual(result, self.binding)
        self.assertNotIn('execution_authorized', result)
        result['ci']['job'] = 'changed'
        self.assertEqual(self.binding['ci']['job'], 'configured-build-control')

    def test_caller_supplied_review_never_substitutes_for_real_verifier(self):
        for fake in ({'status':'passed'}, object(), None):
            with self.subTest(fake=type(fake).__name__), self.assertRaisesRegex(
                    ExecutionContractError, 'real-verifier'):
                verify_configured_human_plan(fake, self.order, self.policy)

    def test_no_added_authority_fields_or_dropped_binding_fields(self):
        changed = deepcopy(self.binding); changed['execution_authorized'] = True
        with self.assertRaisesRegex(ExecutionContractError, 'binding-shape'):
            self.validate(changed)
        for key in self.binding:
            changed = deepcopy(self.binding); del changed[key]
            with self.subTest(key=key), self.assertRaisesRegex(ExecutionContractError, 'binding-shape'):
                self.validate(changed)

    def test_other_case_stub_relabel_and_call_cap_changes_refuse(self):
        for field, value in (('case_id','human-clean-control'), ('stub_only',True),
                ('stub_only',0), ('external_model_calls',0), ('external_model_calls',True),
                ('external_model_calls',4), ('max_attempts',True), ('max_attempts',2)):
            changed=deepcopy(self.binding);changed[field]=value
            with self.subTest(field=field,value=value), self.assertRaisesRegex(
                    ExecutionContractError, 'case-and-caps'):
                self.validate(changed)

    def test_digest_swaps_and_invalid_nonce_refuse(self):
        for field, value in (('nonce_sha256','A'*64), ('nonce_sha256',''),
                ('work_order_sha256','0'*64), ('execution_policy_sha256','0'*64)):
            changed=deepcopy(self.binding);changed[field]=value
            with self.subTest(field=field), self.assertRaisesRegex(
                    ExecutionContractError, 'order-policy-binding'):
                self.validate(changed)

    def test_role_deletion_extra_role_and_cross_role_lease_refuse(self):
        changes=[]
        changed=deepcopy(self.binding);del changed['role_actions']['builder'];changes.append(changed)
        changed=deepcopy(self.binding);changed['role_actions']['operator']=['*'];changes.append(changed)
        changed=deepcopy(self.binding);changed['role_actions']['builder'].append('secret:lease:OPENAI_API_KEY');changes.append(changed)
        for changed in changes:
            with self.assertRaisesRegex(ExecutionContractError, 'role-binding'):
                self.validate(changed)

    def test_workflow_branch_wrong_head_retry_and_external_repository_refuse(self):
        for field, value in (('workflow_ref',self.binding['ci']['workflow_ref'].replace(self.head,'main')),
                ('workflow_ref',self.binding['ci']['workflow_ref'].replace(self.head,'3'*40)),
                ('run_attempt',True),('run_attempt',2),('repository','other/repository'),
                ('job','../job'),('job','')):
            changed=deepcopy(self.binding);changed['ci'][field]=value
            with self.subTest(field=field), self.assertRaisesRegex(ExecutionContractError, 'ci-binding'):
                self.validate(changed)

    def test_ci_claim_cannot_add_run_or_credential_fields(self):
        for field in ('run_id','token','passed'):
            changed=deepcopy(self.binding);changed['ci'][field]='untrusted'
            with self.assertRaisesRegex(ExecutionContractError, 'ci-binding'):
                self.validate(changed)
