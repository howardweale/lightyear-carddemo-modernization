"""Disposable CI relationships/refusals only; no admitted context or service."""
from copy import deepcopy
import json,os,unittest
from pathlib import Path
from types import SimpleNamespace
from lightyear_factory.contracts import WorkOrder,ContractError,canonical_hash
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution import configured_receipt_case as route
from lightyear_execution.configured_receipt_context import ConfiguredReceiptExecutionContext,_preflight,admit_configured_receipt_context
from lightyear_execution.configured_abort_preflight_join import match_abort_preflight
import test_configured_receipt_answer_consumption as messages
import test_configured_abort_preflight_join as preflight_examples

class FixedAnswerRouteIntegration(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        root=Path(__file__).resolve().parents[1]
        doc=json.loads((root/'docs/factory/p5-human-clean-control/configured-build-control/work-order.json').read_bytes())
        self.control=WorkOrder.from_dict(doc)
        self.answer=WorkOrder.from_dict(dict(doc,id=route.ANSWER))

    def test_native_order_routes_to_original_exact_proof_functions(self):
        from lightyear_execution.configured_receipt_admission import verify_configured_receipt_plan
        from lightyear_execution.configured_receipt_answer_admission import verify_answer_receipt_plan
        self.assertIs(route.plan_verifier(self.control),verify_configured_receipt_plan)
        self.assertIs(route.plan_verifier(self.answer),verify_answer_receipt_plan)
        self.assertIs(route.plan_verifier(SimpleNamespace(order_id=route.ANSWER)),verify_configured_receipt_plan)

    def test_selected_proof_and_role_entries_refuse_asserted_admission(self):
        for order in (self.control,self.answer):
            with self.subTest(case=order.order_id):
                with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
                    route.plan_verifier(order)({'status':'passed'},order,object())
                with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
                    route.role_verifier(order)({'status':'passed'},order,object(),'provider','secret:lease:OPENAI_API_KEY')

    def test_selected_reservation_entries_refuse_before_any_api(self):
        for case,order in ((route.CONTROL,self.control),(route.ANSWER,self.answer)):
            with self.assertRaisesRegex(ExecutionContractError,'real-verifier'):
                route.reservation_entry(case)({'status':'passed'},order,object())

    def test_policy_selection_preserves_distinct_exact_parsers(self):
        from lightyear_execution.configured_receipt_policy import parse_configured_receipt_policy
        from lightyear_execution.configured_receipt_answer_policy import parse_answer_receipt_policy
        self.assertIs(route.policy_parser(self.control),parse_configured_receipt_policy)
        self.assertIs(route.policy_parser(self.answer),parse_answer_receipt_policy)
        for order in (self.control,self.answer):
            with self.assertRaises(ExecutionContractError):route.policy_parser(order)({'approved':True})

    def test_original_context_preflight_refuses_answer_without_native_authority(self):
        with self.assertRaisesRegex(ExecutionContractError,'native-context'):
            _preflight({'status':'passed'},self.answer,*[object() for _ in range(7)])
        with self.assertRaisesRegex(ExecutionContractError,'native-context'):
            admit_configured_receipt_context(object(),self.answer,object(),object(),
                source_root=object(),input_paths=object(),read_manifest=object(),model_config_path=object(),
                public_isolation_path=object(),evidence_path=object())

    def test_asserted_answer_binding_cannot_create_live_context_or_lease(self):
        for action in ('authorize','provider','transport'):
            context=object.__new__(ConfiguredReceiptExecutionContext)
            context._order=self.answer
            context._binding={'review':{'drill_binding':{'case_id':route.ANSWER}}}
            with self.subTest(action=action),self.assertRaisesRegex(ExecutionContractError,'fresh-process'):
                if action=='authorize':context.authorize('builder','execute',None)
                elif action=='provider':context.lease_secret('provider','OPENAI_API_KEY',None)
                else:context.lease_transport_key(*[object() for _ in range(5)])

    def test_case_selection_rejects_unknown_missing_and_nonstrings(self):
        for value in (None,{},True,1,'other','ANSWER-FRAGMENT'):
            for entry in (route.consumption_tools,route.signer_path,route.reservation_entry):
                with self.subTest(value=value,entry=entry.__name__),self.assertRaises(ExecutionContractError):entry(value)
            with self.assertRaises(ExecutionContractError):route.review_case({'drill_binding':{'case_id':value}})

    def test_public_signer_path_is_case_specific(self):
        from lightyear_execution.configured_receipt_materials import SIGNERS as control
        from lightyear_execution.configured_receipt_answer_materials import SIGNERS as answer
        self.assertEqual(route.signer_path(route.CONTROL),control)
        self.assertEqual(route.signer_path(route.ANSWER),answer)
        self.assertNotEqual(control,answer)

    def test_consumption_serialization_and_admission_join_use_exact_answer_case(self):
        record=messages.sample();before=deepcopy(record)
        serializer,join,_=route.consumption_tools(route.ANSWER)
        self.assertEqual(serializer(record),json.dumps(record,sort_keys=True,separators=(',',':')).encode())
        self.assertIsNone(join(record,messages.joined(record)))
        self.assertEqual(record,before)
        with self.assertRaises(ExecutionContractError):route.consumption_tools(route.CONTROL)[0](record)
        record['case_id']=route.CONTROL;record['content_sha256']=canonical_hash(record,{'content_sha256'})
        with self.assertRaises(ExecutionContractError):serializer(record)

    def test_observer_selection_uses_original_get_only_public_entries(self):
        from lightyear_execution.configured_consumption_observation import observe_existing_consumption as control
        from lightyear_execution.configured_receipt_answer_consumption_observation import observe_existing_consumption as answer
        self.assertIs(route.consumption_tools(route.CONTROL)[2],control)
        self.assertIs(route.consumption_tools(route.ANSWER)[2],answer)
        # Only argument rejection; neither service observer is invoked.
        with self.assertRaises(TypeError):answer({}, {},api=object())

    def answer_preflight_mappings(self):
        # Existing explicitly untrusted relationship fixture, not a passed proof.
        a,r,c=preflight_examples.AbortPreflightRelations().mappings()
        r['drill_binding']['case_id']=route.ANSWER
        r['content_sha256']=canonical_hash(r,{'content_sha256'})
        return a,r,c

    def test_answer_postreap_relations_do_not_widen_control_default(self):
        args=self.answer_preflight_mappings();before=deepcopy(args)
        self.assertIsNone(match_abort_preflight(*args,_case_id=route.ANSWER))
        self.assertEqual(args,before)
        with self.assertRaisesRegex(ContractError,'preflight-case'):match_abort_preflight(*args)

    def test_answer_postreap_still_rejects_changed_review_nonce_run_and_workflow(self):
        for change in ('digest','nonce','run','workflow','case'):
            a,r,c=self.answer_preflight_mappings()
            if change=='digest':r['content_sha256']='0'*64
            elif change=='nonce':a['nonce_sha256']='0'*64
            elif change=='run':c['run_id']+=1
            elif change=='workflow':a['ci']['workflow_ref']='changed'
            else:r['drill_binding']['case_id']=route.CONTROL;r['content_sha256']=canonical_hash(r,{'content_sha256'})
            with self.subTest(change=change),self.assertRaises(ContractError):
                match_abort_preflight(a,r,c,_case_id=route.ANSWER)

    def test_unrelated_context_is_still_rejected_by_existing_security_boundary(self):
        from lightyear_execution.configured_receipt_security import observe_authorization
        with self.assertRaisesRegex(ExecutionContractError,'original-context'):
            observe_authorization(SimpleNamespace(_order=self.answer),{'role':'provider'})

    def test_no_caller_case_or_proof_override_in_public_context_entry(self):
        for name in ('case_id','review','api','clock','environment','consumption'):
            with self.subTest(name=name),self.assertRaises(TypeError):
                admit_configured_receipt_context(object(),self.answer,object(),object(),**{name:object()})
