"""CI-only unsigned data checks. No signing, proof, controller, nonce or send."""
from copy import deepcopy
import json,os
from pathlib import Path
import unittest
from lightyear_factory.contracts import WorkOrder
from lightyear_execution.contracts import ExecutionPolicy
from lightyear_execution.configured_human_isolation import validate_configured_isolation_document
from tools.ci.p5_configured_human_inputs import build_unsigned_documents,DOCUMENTS,WORKER


class ConfiguredUnsignedInputTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        root=Path(__file__).resolve().parents[1]
        def read(name):return json.loads((root/DOCUMENTS/name).read_bytes())
        self.document=read('work-order.json');self.order=WorkOrder.from_dict(self.document)
        self.policy=ExecutionPolicy.from_configured_human_dict(read('execution-policy.json'))
        self.models=read('models.json');self.isolation=read('public-isolation.json')
        def binding(name):return dict(path=DOCUMENTS+name,sha256='a'*64)
        self.args=dict(order=self.order,policy=self.policy,models=self.models,executable='b'*40,
            bound={k:binding(n) for k,n in [('scope','scope.json'),('freeze','freeze.json'),
                ('workspace','workspace.json'),('execution_policy','execution-policy.json')]},
            isolation=binding('public-isolation.json'),model_binding=binding('models.json'),
            order_binding=binding('work-order.json'),observer_sha256='c'*64,
            window={'start':'2026-10-31T19:00:00-07:00','end':'2026-10-31T20:00:00-07:00'},
            nonce_sha256='d'*64,workflow='.github/workflows/p5-configured-human.yml',job='configured-build-control')

    def test_existing_order_shape_and_public_isolation_digest_match(self):
        self.assertEqual(self.order.to_dict(),self.document)
        self.assertEqual(len(validate_configured_isolation_document(self.isolation,self.order.content_sha256)),3)

    def test_unsigned_plan_keeps_three_roles_one_case_and_shared_cap(self):
        plan,contract=build_unsigned_documents(**self.args)
        self.assertEqual(set(plan['roles']),{'planner','analyst','builder'})
        self.assertEqual(plan['drill_admission']['case_id'],'configured-build-control')
        self.assertEqual(plan['caps']['cost_cap_microusd'],10000000)
        self.assertEqual(plan['caps']['max_model_calls'],3)
        self.assertEqual(plan['drill_admission']['max_attempts'],1)
        self.assertNotIn('public_drill_outputs',plan)
        self.assertNotIn('signature',plan);self.assertNotIn('decision',plan)
        self.assertEqual(contract['details']['request_seal'],plan['content_sha256'])

    def test_all_configuration_bytes_are_bound_as_sources(self):
        plan,contract=build_unsigned_documents(**self.args)
        self.assertEqual({s['path'] for s in contract['sources']},{DOCUMENTS+n for n in
            ('scope.json','freeze.json','workspace.json','execution-policy.json','models.json',
             'public-isolation.json','work-order.json')})
        self.assertTrue(all(s['commit']=='b'*40 for s in contract['sources']))

    def test_changed_case_or_gate_is_refused(self):
        for field in ('case','gate','cap'):
            value=deepcopy(self.document)
            if field=='case':value['id']='human-clean-control'
            elif field=='gate':value['acceptance']['gates'][0]['command']=['python3','different.py']
            else:value['policy']['max_model_cost_usd']=11.0
            args=dict(self.args,order=WorkOrder.from_dict(value))
            with self.assertRaisesRegex(ValueError,'case-scope'):build_unsigned_documents(**args)

    def test_workflow_and_window_require_exact_shape(self):
        for change in ({'workflow':'../unbound.yml'},{'nonce_sha256':'unset'},
                       {'window':{'start':'2026-10-31T19:00:00','end':'2026-10-31T20:00:00'}}):
            with self.assertRaises(ValueError):build_unsigned_documents(**dict(self.args,**change))

    def test_stub_outputs_cannot_be_supplied(self):
        with self.assertRaises(TypeError):build_unsigned_documents(**self.args,outputs={'provider':'p5-scripted'})
