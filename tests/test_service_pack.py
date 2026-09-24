"""Declarative invocation contracts and adversarial capability tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import Journeys, Response, execute_journeys, SCENARIOS
from lightyear_data.service_journeys import cloudbank_pack, PACK_PATH
from lightyear_workflow.service_pack import (
    JourneyFailure, JourneyPack, PackError, Runner, SourceLane, TargetLane, load, plan, validate_pack,
)
from tests.test_cloudbank_journeys import StatefulRuntime

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "spec/service-packs/order-approval.pack.json"


class Captures:
    def __init__(self, kind=None): self.calls = []; self.kind = kind
    def record(self, journey_id):
        self.calls.append(journey_id)
        value = {"journey": journey_id, "evidence": {"id": "A1", "status": "approved", "total_cents": 150}}
        if self.kind: value["evidence_class"] = self.kind
        return value


class Orders:
    def __init__(self, fault=None): self.calls = []; self.status = "pending"; self.fault = fault
    def request(self, service, method, path, role, body=None, headers=None):
        self.calls.append((service, method, path, role))
        if method == "POST" and self.fault != "no-effects": self.status = "approved"
        payload = {"id": "A1", "status": self.status, "total_cents": 151 if self.fault == "wrong-total" and self.status == "approved" else 150}
        return Response(200, json.dumps(payload).encode(), {})


class ValidationTests(unittest.TestCase):
    def setUp(self): self.raw = json.loads(EXAMPLE.read_text())
    def refused(self, mutate):
        raw = copy.deepcopy(self.raw); mutate(raw)
        with self.assertRaises(PackError): validate_pack(raw)

    def test_unsafe_declarations_are_rejected(self):
        changes = [
            lambda r: r['source'].update(verbs=['request']),
            lambda r: r['source'].update(url='https://production'),
            lambda r: r.update(journeys=[]),
            lambda r: r['journeys'].append(r['journeys'][0]),
            lambda r: r['target'].update(verbs=['control']),
            lambda r: r['macros']['approve']['steps'][0].update(service='unlisted'),
            lambda r: r['macros']['approve']['steps'][0].update(method='TRACE'),
            lambda r: r['macros']['approve']['steps'][0].update(role='admin'),
            lambda r: r['macros']['approve']['steps'][0].update(headers={'Authorization':'secret'}),
            lambda r: r['macros']['approve']['steps'][0].update(query={'access_token':'secret'}),
            lambda r: r['macros']['approve']['steps'][0].update(allow_error='anything'),
            lambda r: r['macros']['approve']['steps'][0].update(retry=99),
            lambda r: r['macros']['approve']['steps'][1].update(test={'$op':'eval','args':['print(1)']}),
            lambda r: r['macros']['approve']['steps'][1].update(test={'$ref':'future.status'}),
            lambda r: r['macros']['approve']['steps'][0].update(params={}),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)): self.refused(change)

    def test_urls_and_traversal_and_encoded_paths_are_refused(self):
        for path in ['https://host/orders','//host/orders','/../orders','/orders%2fadmin','/orders\\admin','/orders?token=x','/orders#fragment']:
            with self.subTest(path=path): self.refused(lambda r: r['macros']['approve']['steps'][0].update(path=path,params={}))

    def test_malformed_values_are_pack_errors(self):
        for raw in [None,[],True,{},'bad',{'pack_type':[]}]:
            with self.subTest(raw=raw), self.assertRaises(PackError): validate_pack(raw)
        for field in ['services','roles','inputs','state','macros','journeys','source','target']:
            for value in [None, True, 'bad', [None], {'bad': object()}]:
                with self.subTest(field=field,value=str(value)), self.assertRaises(PackError):
                    validate_pack({**self.raw,field:value})

    def test_cycles_including_unused_macros_are_refused(self):
        self.refused(lambda r: r['macros']['approve']['steps'].append({'op':'call','macro':'approve','args':{}}))

    def test_hidden_poll_write_is_refused(self):
        self.refused(lambda r: r['macros'].update(loop={'params':[], 'steps':[{'op':'poll','steps':[{'op':'call','macro':'approve','args':{}}], 'until':True,'attempts':2,'code':'not-ready'}], 'return':None}))

    def test_unbounded_or_boolean_loop_bounds_are_refused(self):
        for bound in [0,True,1000000]:
            self.refused(lambda r: r['macros'].update(loop={'params':[], 'steps':[{'op':'each','over':[],'as':'item','max_items':bound,'steps':[{'op':'assert','test':True,'code':'check'}]}], 'return':None}))

    def test_parallel_shared_state_write_is_refused_transitively(self):
        def change(r):
            r['state']['counter']=0
            r['macros']['approve']['steps'].append({'op':'set','name':'counter','value':1,'state':True})
            r['macros']['race']={'params':[],'steps':[{'op':'parallel','calls':[{'op':'call','macro':'approve','args':{}}],'save':'results'}],'return':None}
        self.refused(change)

    def test_duplicate_json_keys_and_oversized_pack_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pack.json'
            for content in ['{"pack_id":"a","pack_id":"b"}', ' '*1048577, '{"x":NaN}']:
                path.write_text(content)
                with self.assertRaises(PackError): load(path)

    def test_immutable_snapshot_and_forged_dataclass_revalidation(self):
        pack=validate_pack(self.raw)
        self.raw['source']['verbs'].append('request')
        detached=pack.raw;detached['source']['verbs'].append('request')
        self.assertEqual(plan(pack)['source_invocations'],[])
        with self.assertRaises(PackError): plan(JourneyPack(json.dumps(detached)))

    def test_a_label_without_observations_and_checks_is_refused(self):
        self.refused(lambda r: r['macros']['approve'].update(steps=[{'op':'set','name':'nothing','value':True}], **{'return': {'passed':True}}))
        self.refused(lambda r: r['macros']['approve'].update(steps=[r['macros']['approve']['steps'][0]], **{'return': None}))

    def test_no_python_callbacks_or_target_hosts_in_pack(self):
        self.refused(lambda r: r.update(callback='customer.module.function'))
        self.refused(lambda r: r['target'].update(base_url='https://production'))


class PlanAndLaneTests(unittest.TestCase):
    def setUp(self): self.pack=load(EXAMPLE)

    def test_plan_is_side_effect_free_and_counts_actual_calls(self):
        footprint=plan(self.pack)
        self.assertEqual(footprint['services_touched'],['orders'])
        self.assertEqual(footprint['source_reads'],['approve-order'])
        self.assertEqual(footprint['source_invocations'],[])
        self.assertEqual([(r['method'],r['max_calls']) for r in footprint['target_requests']],[('GET',2),('POST',1)])
        orders=Orders()
        result=Runner(self.pack,TargetLane(orders.request),{'order_id':'A1'}).journey('approve-order')
        self.assertEqual(result['status'],'approved')
        self.assertEqual(len(orders.calls),3)

    def test_cloudbank_plan_includes_nested_recovery_and_poll_bounds(self):
        footprint=plan(cloudbank_pack())
        actions={c['action'] for c in footprint['target_controls']}
        self.assertTrue({'crash_stop','restore_delivery','restart_all','queue'} <= actions)
        self.assertEqual(footprint['source_invocations'],[])
        self.assertEqual(len(footprint['journeys']),18)
        self.assertTrue(any(r['max_calls'] > 181 for r in footprint['target_requests']))
        self.assertTrue(any(r['path']=='/api/v1/testrunner/clear' for r in footprint['target_requests']))

    def test_unreachable_macro_does_not_inflate_plan(self):
        raw=self.pack.raw
        raw['services'].append('unused')
        raw['macros']['unused']={'params':[],'steps':[{'op':'request','service':'unused','method':'DELETE','path':'/all','save':'response'}],'return':None}
        self.assertEqual(plan(validate_pack(raw))['services_touched'],['orders'])

    def test_source_has_no_invocation_capability_even_for_get(self):
        for name in ('request','control','replay','submit','start','restart'):
            self.assertFalse(hasattr(SourceLane,name))
        reader=Captures();lane=SourceLane(reader)
        source=lane.observe(self.pack)
        self.assertEqual(reader.calls,['approve-order'])
        self.assertEqual(source['evidence_class'],'simulated')
        with self.assertRaises(PackError): Runner(self.pack,lane,{'order_id':'A1'})
        with self.assertRaises(AttributeError): lane.request=lambda:None

    def test_missing_source_evidence_never_becomes_empty_success(self):
        reader=Captures();reader.record=lambda _:{}
        with self.assertRaises(JourneyFailure):SourceLane(reader).observe(self.pack)

    def test_target_requires_capabilities_before_first_request(self):
        with self.assertRaises(PackError):Runner(self.pack,TargetLane(),{'order_id':'A1'})
        with self.assertRaises(PackError):Runner(cloudbank_pack(),TargetLane(Orders().request),{'owner':'x','run_id':'x'})

    def test_target_replay_retains_weakest_lane_evidence(self):
        for source_class,target_class,expected in [(None,'runtime_observed','simulated'),('runtime_observed','simulated','simulated'),('local_observed','runtime_observed','local_observed')]:
            source=SourceLane(Captures(source_class)).observe(self.pack)
            result=TargetLane(Orders().request,evidence_class=target_class).replay(self.pack,{'order_id':'A1'},source)
            self.assertEqual(result['status'],'passed-declared-assertions')
            self.assertEqual(result['evidence_class'],expected)
            self.assertFalse(result['source_target_comparison_performed'])
            self.assertEqual(len(result['source_sha256']),64)

    def test_source_pack_mismatch_blocks_all_target_calls(self):
        source=SourceLane(Captures()).observe(self.pack);source['pack_sha256']='bad'
        orders=Orders()
        with self.assertRaises(PackError):TargetLane(orders.request).replay(self.pack,{'order_id':'A1'},source)
        self.assertEqual(orders.calls,[])

    def test_success_status_without_effects_and_wrong_total_fail(self):
        source=SourceLane(Captures()).observe(self.pack)
        for fault,code in [('no-effects','approval-not-applied'),('wrong-total','approval-changed-total')]:
            result=TargetLane(Orders(fault).request).replay(self.pack,{'order_id':'A1'},source)
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['journeys'][0]['reason'],code)

    def test_runtime_path_escape_refused_before_transport(self):
        raw=self.pack.raw;raw['inputs']['order_id']='string'
        orders=Orders()
        for value in ['../admin','https://host','a/b','a%2fb','a\\b','..']:
            with self.subTest(value=value),self.assertRaises(JourneyFailure):
                Runner(validate_pack(raw),TargetLane(orders.request),{'order_id':value}).journey('approve-order')
        self.assertEqual(orders.calls,[])

    def test_typed_equality_does_not_accept_boolean_as_money(self):
        runner=Runner(self.pack,TargetLane(Orders().request),{'order_id':'A1'})
        self.assertFalse(runner.value({'$op':'eq','args':[[True],[1]]},{}))
        self.assertFalse(runner.value({'$op':'in','args':[True,[1]]},{}))

    def test_ambiguous_or_inexact_response_json_cannot_pass(self):
        runner=Runner(self.pack,TargetLane(Orders().request),{'order_id':'A1'})
        for body in [b'{"amount":1,"amount":2}',b'{"amount":1.00000000000000001}',b'{"amount":NaN}']:
            with self.subTest(body=body),self.assertRaisesRegex(JourneyFailure,'response-json-invalid'):
                runner.value({'$op':'json','args':[{'$ref':'response'}]},{'response':{'body':body}})

    def test_new_pack_binding_rejects_drift_and_preserves_legacy_records(self):
        from lightyear_data.service_journeys import pack_binding_valid
        self.assertTrue(pack_binding_valid({}))
        self.assertTrue(pack_binding_valid({'journey_pack_sha256':cloudbank_pack().sha256}))
        self.assertFalse(pack_binding_valid({'journey_pack_sha256':'0'*64}))

    def test_poll_attempt_count_is_bounded_even_with_frozen_clock(self):
        raw=self.pack.raw
        raw['macros']['approve']['steps']=[{'op':'poll','steps':[raw['macros']['approve']['steps'][0]],'until':False,'attempts':3,'code':'not-ready'}]
        raw['macros']['approve']['return']=None
        orders=Orders()
        with self.assertRaisesRegex(JourneyFailure,'not-ready'):
            Runner(validate_pack(raw),TargetLane(orders.request),{'order_id':'A1'},timeout=10,pause=lambda _:None,clock=lambda:0).journey('approve-order')
        self.assertEqual(len(orders.calls),3)

    def test_expression_budget_and_cleanup_reserve(self):
        raw=self.pack.raw
        raw['macros']['approve']['steps']=[{'op':'ensure','steps':[{'op':'assert','test':True,'code':'check'}], 'finally':[{'op':'request','service':'orders','method':'DELETE','path':'/fixture','save':'cleanup'}]}]
        raw['macros']['approve']['return']=None
        orders=Orders();runner=Runner(validate_pack(raw),TargetLane(orders.request),{'order_id':'A1'})
        runner.budget=2
        with self.assertRaisesRegex(JourneyFailure,'execution-budget-exhausted'):runner.journey('approve-order')
        self.assertEqual(orders.calls[0][1:3],('DELETE','/fixture'))

    def test_restoration_failure_invalidates_passing_assertions(self):
        source=SourceLane(Captures()).observe(self.pack)
        result=TargetLane(Orders().request,restore=lambda:{'status':'failed'}).replay(self.pack,{'order_id':'A1'},source)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['journeys'][0]['status'],'passed')


class CloudBankExtractionTests(unittest.TestCase):
    def test_declaration_change_changes_execution_without_python_handler(self):
        raw=cloudbank_pack().raw
        raw['journeys'][5]['args']['amount']=27
        driver=Journeys(StatefulRuntime(),'test',pack=validate_pack(raw),timeout=0)
        for j in driver.pack.journeys[:6]:driver.runner.journey(j['id'])
        self.assertEqual(driver.state()['balances'],[973,277,5])
        self.assertFalse(hasattr(driver,'operations'))
        self.assertEqual(tuple((j['id'],j['normalized_result']) for j in cloudbank_pack().journeys),SCENARIOS)

    def test_plan_covers_observed_reference_requests(self):
        runtime=StatefulRuntime()
        with patch.object(runtime,'request',wraps=runtime.request) as request:
            result=execute_journeys(runtime,{},'key','test',run_id='test',timeout=0,pause=lambda _:None)
        self.assertEqual(result['status'],'passed-shared-journeys')
        self.assertEqual(result['bindings']['journey_pack_sha256'],cloudbank_pack().sha256)
        footprint=plan(cloudbank_pack())
        import re
        from urllib.parse import urlsplit
        for call in request.call_args_list:
            service,method,path,role=call.args[:4]
            self.assertTrue(any(r['service']==service and r['method']==method and r['role']==role and re.fullmatch(re.sub(r'\{[a-z_]+\}','[A-Za-z0-9_-]+',r['path']),urlsplit(path).path) for r in footprint['target_requests']),call)

    def test_reference_adapter_cannot_hide_services_touched_by_global_controls(self):
        raw=cloudbank_pack().raw
        raw['services'].remove('azn-server')
        runtime=StatefulRuntime()
        with patch.object(runtime,'request',wraps=runtime.request) as request:
            with self.assertRaisesRegex(JourneyFailure,'journey-service-scope-invalid'):
                Journeys(runtime,'test',pack=validate_pack(raw))
        request.assert_not_called()

    def test_pack_is_in_runtime_qualification_source_identity(self):
        from lightyear_qualification.runtime_gates import identity
        self.assertIn('src/lightyear_data/packs/cloudbank.services.json',identity())


if __name__=='__main__':unittest.main()
