"""Synthetic launch refusals; no authority, models, seed or private store."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lightyear_factory.contracts import ContractError, WorkOrder, canonical_hash
from lightyear_factory.copau_boundary import (
    DISABLED_GRAPH, SETTINGS, digest, encoded, enforce, validate_launch, disabled_graph)


class CopauRunBoundaryTests(unittest.TestCase):
    def fixture(self):
        root = Path(__file__).resolve().parents[1]
        raw = json.loads((root/'docs/factory/copau-f2-preparation-2026-10-22/request.json').read_bytes())
        order = WorkOrder.from_dict(raw['work_order'])
        boundary = dict(schema='copau-run-visible-boundary/1', main_commit='a'*40,
            work_order_sha256=order.content_sha256, launch_settings=dict(SETTINGS),
            launch_settings_sha256=digest(encoded(SETTINGS)), graph_declaration=dict(DISABLED_GRAPH),
            surfaces=dict(graph=dict(status='disabled', records=0,
                exception='copau-empty-graph-2026-10-24',
                declaration_sha256=digest(encoded(DISABLED_GRAPH))), prompts={}, contexts={}))
        return order, boundary

    def test_graph_file_and_abbreviated_or_equals_overrides_refused(self):
        order, boundary = self.fixture()
        for flags in (['--graph','public.json'], ['--graph=public.json'], ['--gra','public.json'],
                      ['--evidence-pack','public.json'], ['--approved-projection','public.json']):
            with self.subTest(flags=flags), self.assertRaises(ContractError):
                validate_launch(order, flags, boundary)

    def test_graph_tool_policy_and_node_ids_refused(self):
        order, boundary = self.fixture()
        for mutation in ('mode','policy','roots','annotated'):
            raw = order.to_dict()
            if mutation == 'mode': raw['metadata']['graph'] = 'on-demand'
            if mutation == 'policy': raw['metadata']['graph_policy'] = {'call_budget':1}
            if mutation == 'roots': raw['scope']['graph_node_ids'] = ['public:node']
            if mutation == 'annotated': raw['metadata']['context_schema'] = '1.1'
            changed = WorkOrder.from_dict(raw)
            candidate = copy.deepcopy(boundary); candidate['work_order_sha256'] = changed.content_sha256
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                validate_launch(changed, [], candidate)

    def test_memory_setting_and_metadata_refused(self):
        order, boundary = self.fixture()
        for flags in (['--memory-root','public'], ['--memory-policy=public.json'], ['--disable-memory']):
            with self.subTest(flags=flags), self.assertRaises(ContractError):
                validate_launch(order, flags, boundary)
        raw = order.to_dict();raw['metadata']['memory'] = 'enabled'
        changed = WorkOrder.from_dict(raw);boundary['work_order_sha256'] = changed.content_sha256
        with self.assertRaises(ContractError):validate_launch(changed, [], boundary)

    def test_zero_records_requires_exact_disabled_declaration_exception(self):
        _, boundary = self.fixture(); row = boundary['surfaces']['graph']
        disabled_graph(row, DISABLED_GRAPH)
        for field, value in (('records',1),('records',False),('exception','unapproved'),('status','empty'),('declaration_sha256','0'*64)):
            changed = dict(row); changed[field] = value
            with self.subTest(field=field,value=value),self.assertRaises(ContractError):disabled_graph(changed, DISABLED_GRAPH)
        with self.assertRaises(ContractError):disabled_graph(row, dict(DISABLED_GRAPH,nodes=1))

    def test_boundary_and_order_changes_refused(self):
        order, boundary = self.fixture()
        for field, value in (('schema','other'),('main_commit','unknown'),
                             ('work_order_sha256','0'*64),('launch_settings_sha256','0'*64),
                             ('launch_settings',dict(SETTINGS,memory='enabled'))):
            changed = copy.deepcopy(boundary);changed[field] = value
            with self.subTest(field=field),self.assertRaises(ContractError):validate_launch(order, [], changed)

    def test_enforcement_requires_signed_plan_binding_and_disables_objects(self):
        order, boundary = self.fixture();before = order.to_dict()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);path = root/'boundary.json';raw = encoded(boundary);path.write_bytes(raw)
            plan = dict(executable_commit='a'*40, run_visible_boundary=dict(path='boundary.json',
                sha256=digest(raw),launch_settings_sha256=boundary['launch_settings_sha256'],main_commit='a'*40))
            plan['content_sha256'] = canonical_hash(plan)
            admission = Mock();admission.paths = ('plan.json',)
            admission._committed_json.side_effect = lambda name: boundary if name == 'boundary.json' else plan
            admission.verify_plan.return_value = {'plan_sha256':plan['content_sha256']}
            args = SimpleNamespace(source_root=root, factory_run_boundary=path, graph=Path('default'),
                                   evidence_pack=Path('default'),approved_projection=None,disable_memory=False)
            enforce(args,order,[],admission)
            self.assertIsNone(args.graph);self.assertIsNone(args.evidence_pack)
            self.assertIsNone(args.approved_projection);self.assertTrue(args.disable_memory)
            self.assertEqual(before,order.to_dict())
            plan['run_visible_boundary']['sha256']='0'*64
            plan['content_sha256']=canonical_hash(plan,{'content_sha256'})
            admission.verify_plan.return_value={'plan_sha256':plan['content_sha256']}
            with self.assertRaises(ContractError):enforce(args,order,[],admission)

    def test_missing_boundary_refused_before_nonce_and_credentials_in_cli(self):
        from lightyear_factory.cli import main
        order, _ = self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);envelope=root/'envelope.json';envelope.write_text('{"nonce":"synthetic"}')
            admission=Mock()
            with patch('lightyear_factory.model_admission.FactoryModelAdmission.from_external_trust',return_value=admission), patch(
                'lightyear_factory.cli.ExecutionPolicy.load'), patch('lightyear_factory.cli.verify_work_order',return_value=(order,{})), patch(
                'lightyear_factory.cli.AdmissionNonceStore') as nonce, patch('lightyear_factory.cli.HardenedExecutionContext') as context:
                with self.assertRaisesRegex(ContractError,'^copau-run-visible-boundary-refused$'):
                    main(['run','--provider','configured','--signed-work-order',str(envelope),'--execution-runtime','docker',
                          '--factory-plan','plan','--factory-approval','proof','--factory-contract','contract',
                          '--factory-trust','trust','--factory-scope','scope','--factory-freeze','freeze',
                          '--factory-workspace','workspace','--factory-private-expected-values','unused-synthetic'])
                nonce.assert_not_called();context.assert_not_called();admission.private_expected_values.assert_not_called()

    def test_empty_packed_context_uses_no_graph_or_memory_loader(self):
        from lightyear_factory.context import GraphContextAssembler
        order,_=self.fixture()
        with tempfile.TemporaryDirectory() as temp, patch('lightyear_factory.context.load_graph') as graph:
            context=GraphContextAssembler(None,None).assemble(order,Path(temp))
            self.assertEqual([],context['nodes']);self.assertEqual([],context['edges'])
            self.assertEqual([],context['source_excerpts']);self.assertIsNone(context['semantic_memory'])
            graph.assert_not_called()
