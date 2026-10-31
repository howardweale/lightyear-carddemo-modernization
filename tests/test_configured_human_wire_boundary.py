"""CI-only pending-byte relations/refusals; never passed authority or a send."""
import ast,os,unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from urllib.request import Request
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_human_wire_boundary import match_pending_request,require_original_wire_open


class ConfiguredWireBoundaryTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def relation(self,kind='responses'):
        url='https://api.openai.com/v1/'+('responses' if kind=='responses' else 'responses/input_tokens')
        request=Request(url,data=b'{"synthetic":true}',method='POST')
        row=dict(role='planner',provider='openai-responses',model='pinned-model',transport_kind=kind,
            provider_attempt=1,invocation={'call_sequence':1},request_sha256=sha256(request.data).hexdigest(),
            request_bytes=len(request.data))
        event=dict(kind='model_transport_reserved',event_sha256='a'*64,
            payload=dict(attempt_identity_sha256='b'*64,transport_sequence=1,reservation=row))
        return request,event

    def test_original_byte_relations_for_count_and_generation_are_not_authority(self):
        for kind in ('responses','input-token-count'):
            request,event=self.relation(kind);before=deepcopy(event)
            self.assertEqual(match_pending_request([event],'b'*64,request,'planner','pinned-model',1),(event,event['payload']['reservation']))
            self.assertEqual(event,before)

    def test_observed_or_missing_reservation_refused(self):
        request,event=self.relation()
        for rows in ([],[event,{'kind':'model_transport_observed'}]):
            with self.assertRaisesRegex(ContractError,'pending-reservation'):
                match_pending_request(rows,'b'*64,request,'planner','pinned-model',1)

    def test_raw_bytes_role_kind_identity_and_size_must_match(self):
        request,event=self.relation()
        for key,value in (('request_sha256','c'*64),('request_bytes',True),('role','builder'),('transport_kind','input-token-count')):
            changed=deepcopy(event);changed['payload']['reservation'][key]=value
            with self.assertRaises(ContractError):match_pending_request([changed],'b'*64,request,'planner','pinned-model',1)
        with self.assertRaises(ContractError):match_pending_request([event],'c'*64,request,'planner','pinned-model',1)

    def test_completed_logical_call_and_retry_refused(self):
        request,event=self.relation()
        with self.assertRaises(ContractError):match_pending_request([event],'b'*64,request,'planner','pinned-model',2)
        event['payload']['reservation']['provider_attempt']=2
        with self.assertRaises(ContractError):match_pending_request([event],'b'*64,request,'planner','pinned-model',1)

    def test_no_controller_or_passed_receipt_can_open_transport(self):
        request,_=self.relation()
        for value in (object(),{'status':'passed'}):
            with self.assertRaisesRegex(ContractError,'native-provider'):require_original_wire_open(value,request)

    def test_final_native_opener_is_after_original_live_wire_boundary(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'src/lightyear_execution/configured_human_recorded_transport.py').read_text())
        function=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='open_native_recorded_transport')
        calls={n.func.id:n.lineno for n in ast.walk(function) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        self.assertLess(calls['require_original_wire_open'],calls['opener'])
