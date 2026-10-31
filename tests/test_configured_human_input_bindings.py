"""CI-only pure scope/refusal tests; no secret read, proof mock or provider call."""
from copy import deepcopy
import json,os
from pathlib import Path
import unittest
from lightyear_factory.contracts import ContractError,WorkOrder
from lightyear_factory.flex_billing import flex_billing_policy
from lightyear_execution.contracts import ExecutionPolicy
from lightyear_execution.configured_human_models import validate_control_model_document

class ConfiguredHumanInputBindingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.root = Path(__file__).resolve().parents[1]
        self.model = dict(provider='openai', model='gpt-5.4-2026-03-05',
            input_usd_per_million=5.5, output_usd_per_million=24.75,
            max_output_tokens=1024, service_tier='flex',
            billing_policy=flex_billing_policy())
        self.document = dict(default='control', models={'control': self.model})
        self.roles = {name:dict(provider='openai-responses', model=self.model['model'])
                      for name in ('planner','analyst','builder')}
        base = self.root/'tests/fixtures/p5_public/human-clean-control'
        order = json.loads((base/'work-order.json').read_bytes())
        order['id']='configured-build-control'
        order['policy']['max_model_calls']=3
        self.order=WorkOrder.from_dict(order)
        self.policy=ExecutionPolicy.load(base/'execution-policy.json')

    def test_pure_model_scope_preserves_unknown_billing_and_grants_nothing(self):
        before=deepcopy(self.document)
        result=validate_control_model_document(self.document,self.roles)
        self.assertEqual(result,before)
        self.assertIsNot(result,self.document)
        self.assertIs(result['models']['control']['billing_policy']['billing_final'],False)
        self.assertEqual(result['models']['control']['billing_policy']['count_billing_status'],'unknown')
        self.assertNotIn('admission_verified',result)
        self.assertNotIn('execution_authorized',result)

    def test_routing_fallback_and_additional_models_refuse(self):
        for field in ('policy','matrix_receipt','approval','trust','fallback'):
            changed=deepcopy(self.document);changed[field]={}
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'no-routing-or-fallback'):
                validate_control_model_document(changed,self.roles)
        changed=deepcopy(self.document);changed['models']['extra']=deepcopy(self.model)
        with self.assertRaisesRegex(ContractError,'single-model'):
            validate_control_model_document(changed,self.roles)

    def test_inline_secret_unreviewed_provider_and_tier_refuse(self):
        for field in ('api_key','token','password','opener','max_retries'):
            changed=deepcopy(self.document);changed['models']['control'][field]='synthetic'
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'model-fields'):
                validate_control_model_document(changed,self.roles)
        for field,value in (('provider','anthropic'),('service_tier','default'),
                            ('max_output_tokens',True),('max_output_tokens',65537)):
            changed=deepcopy(self.document);changed['models']['control'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'provider-tier'):
                validate_control_model_document(changed,self.roles)

    def test_every_role_must_match_the_exact_signed_provider_snapshot(self):
        for role in self.roles:
            changed=deepcopy(self.roles);changed[role]['model']='gpt-5.4-2026-03-06'
            with self.subTest(role=role),self.assertRaisesRegex(ContractError,'plan-roles'):
                validate_control_model_document(self.document,changed)
        with self.assertRaisesRegex(ContractError,'plan-roles'):
            validate_control_model_document(self.document,{'planner':self.roles['planner']})
        changed=deepcopy(self.document);changed['models']['control']['model']='latest'
        with self.assertRaises(ValueError):
            validate_control_model_document(changed,self.roles)

    def test_changed_billing_bound_and_prices_refuse(self):
        for field,value in (('input_usd_per_million',2.5),('output_usd_per_million',15.0)):
            changed=deepcopy(self.document);changed['models']['control'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'flex-billing-binding'):
                validate_control_model_document(changed,self.roles)
        changed=deepcopy(self.document)
        changed['models']['control']['billing_policy']['automatic_tier_fallback']=True
        with self.assertRaisesRegex(ContractError,'flex-billing-binding'):
            validate_control_model_document(changed,self.roles)

    def test_human_model_and_isolation_entries_refuse_supplied_passed_review(self):
        from lightyear_execution.contracts import ExecutionContractError
        from lightyear_execution.configured_human_models import review_configured_human_models
        from lightyear_execution.configured_human_isolation import review_configured_human_isolation
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            review_configured_human_models({'status':'passed'},self.order,self.policy,'unused',
                input_paths={},read_manifest={})
        with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
            review_configured_human_isolation({'status':'passed'},self.order,self.policy,{},'unused')

    def test_isolation_document_is_case_bound_and_has_no_authority_flags(self):
        from lightyear_execution.configured_human_isolation import validate_configured_isolation_document
        from lightyear_factory.contracts import canonical_hash
        value=dict(schema='factory-public-drill-isolation/1',case_id='configured-build-control',
            work_order_sha256=self.order.content_sha256,
            values=['public synthetic configured isolation fixture '+str(n)*40 for n in range(3)])
        value['content_sha256']=canonical_hash(value)
        self.assertEqual(validate_configured_isolation_document(value,self.order.content_sha256),tuple(value['values']))
        for field,replacement in (('case_id','human-clean-control'),('work_order_sha256','0'*64),
                ('values',value['values'][:2]),('values',[value['values'][0]]*3),('values',['short']*3)):
            changed=deepcopy(value);changed[field]=replacement
            changed['content_sha256']=canonical_hash(changed,{'content_sha256'})
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'public-isolation-content'):
                validate_configured_isolation_document(changed,self.order.content_sha256)
        changed=deepcopy(value);changed['execution_authorized']=True
        changed['content_sha256']=canonical_hash(changed,{'content_sha256'})
        with self.assertRaisesRegex(ContractError,'public-isolation-content'):
            validate_configured_isolation_document(changed,self.order.content_sha256)

    def test_isolation_digest_mismatch_refuses_even_when_scope_matches(self):
        from lightyear_execution.configured_human_isolation import validate_configured_isolation_document
        value=dict(schema='factory-public-drill-isolation/1',case_id='configured-build-control',
            work_order_sha256=self.order.content_sha256,content_sha256='0'*64,
            values=['public synthetic configured isolation fixture '+str(n)*40 for n in range(3)])
        with self.assertRaisesRegex(ContractError,'public-isolation-content'):
            validate_configured_isolation_document(value,self.order.content_sha256)
