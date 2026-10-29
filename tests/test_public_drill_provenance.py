"""CI-only trace validation with public synthetic records, never execution grants."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest

from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.public_drill_runtime import (
    PublicDrillProvider,artifact_bytes,match_invocation,verify_recorded_trace,verify_receipt_tail)


class PublicDrillProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        (self.root/'public-drill').mkdir()
        self.request=dict(instruction='Public synthetic task',payload={'text':'alpha'},schema={'type':'object'})
        self.response={'result':'public synthetic response'}
        self.step=dict(sequence=1,role='planner',invocation_sha256=canonical_hash(self.request),
            schema_sha256=canonical_hash(self.request['schema']),response_content=self.response,
            response_sha256=canonical_hash({'content':self.response}))
        self.script=dict(model='p5-stub-2026-10-27',steps=[self.step],content_sha256='a'*64)
        self.admission=dict(content_sha256='b'*64,work_order_sha256='c'*64,
            execution_policy_sha256='d'*64,plan_sha256='e'*64,decision_sha256='f'*64,
            trusted_journal_head='1'*64,nonce_sha256='2'*64)
        scope={k:v for k,v in self.admission.items() if k!='content_sha256'}
        scope.update(role='planner',action='factory:plan',status='verified-scope-only',execution_authorized=False)
        scope['content_sha256']=canonical_hash(scope);self.auth=[scope]
        self.accounting=[dict(kind='reserved',event_sha256='3'*64,payload={'reservation':dict(
            role='planner',call_sequence=1,request_sha256=self.step['invocation_sha256'],
            invocation_sha256=self.step['invocation_sha256'])})]
        binding=dict(kind='public_drill_controller_bound',sequence=1,event_sha256='4'*64,payload=dict(
            output_plan_sha256=self.script['content_sha256'],admission_receipt_sha256='b'*64,
            work_order_sha256='c'*64,provider='p5-scripted',model=self.script['model']))
        start=dict(kind='public_drill_call_started',sequence=2,event_sha256='5'*64,payload=dict(
            sequence=1,role='planner',invocation_sha256=self.step['invocation_sha256'],
            schema_sha256=self.step['schema_sha256'],request=self.write('request',self.request),
            authorization_sha256=scope['content_sha256'],logical_reservation_event_sha256='3'*64,
            output_plan_sha256=self.script['content_sha256']))
        end=dict(kind='public_drill_call_finished',sequence=3,event_sha256='6'*64,payload=dict(
            sequence=1,role='planner',start_event_sha256='5'*64,response=self.write('response',self.response),
            response_sha256=self.step['response_sha256']))
        self.events=[binding,start,end]
        call=dict(provider='p5-scripted',model=self.script['model'],role='planner',call_sequence=1,
            request_sha256=self.step['invocation_sha256'],response_sha256=self.step['response_sha256'],
            public_drill_record=dict(start_event_sha256='5'*64,end_event_sha256='6'*64,
                                    output_plan_sha256=self.script['content_sha256']))
        call['content_sha256']=canonical_hash(call);self.calls=[call]

    def write(self,kind,value):
        raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
        relative='public-drill/0001-'+kind+'.json';(self.root/relative).write_bytes(raw)
        return dict(path=relative,sha256=sha256(raw).hexdigest(),bytes=len(raw))

    def verify(self):
        return verify_recorded_trace(self.script,self.events,self.accounting,self.auth,self.calls,self.root,self.admission)

    def test_complete_trace_relations_do_not_grant_controller_origin(self):
        result=self.verify()
        self.assertTrue(result['output_plan_complete'])
        self.assertFalse(result['controller_origin_verified'])
        self.assertEqual(result['completed_public_calls'],1)
        self.assertEqual(result['unfinished_public_calls'],0)

    def test_invocation_schema_role_and_boolean_sequence_refuse(self):
        for sequence,role,instruction,payload,schema in (
            (True,'planner','Public synthetic task',self.request['payload'],self.request['schema']),
            (1,'builder','Public synthetic task',self.request['payload'],self.request['schema']),
            (1,'planner','changed',self.request['payload'],self.request['schema']),
            (1,'planner','Public synthetic task',{'text':'changed'},self.request['schema']),
            (1,'planner','Public synthetic task',self.request['payload'],{'type':'array'})):
            with self.subTest(sequence=sequence,role=role,instruction=instruction,payload=payload,schema=schema):
                with self.assertRaises(ContractError):match_invocation(self.step,sequence,role,instruction,payload,schema)

    def test_tampered_bytes_and_self_rehashed_response_refuse(self):
        self.write('response',{'result':'substituted'})
        with self.assertRaises(ContractError):self.verify()
        self.events[2]['payload']['response']=self.write('response',{'result':'substituted'})
        with self.assertRaises(ContractError):self.verify()

    def test_path_traversal_wrong_kind_and_boolean_size_refuse(self):
        reference=self.events[1]['payload']['request']
        for field,value in (('path','../request.json'),('path','public-drill/0001-response.json'),('bytes',True)):
            altered={**reference,field:value}
            with self.subTest(field=field,value=value),self.assertRaises(ContractError):
                artifact_bytes(self.root,altered,1,'request')

    def test_missing_or_duplicate_controller_binding_refuses(self):
        original=deepcopy(self.events)
        for events in (original[1:],[original[0],*original]):
            self.events=events
            with self.assertRaises(ContractError):self.verify()

    def test_missing_reservation_or_changed_authorization_refuses(self):
        original=deepcopy(self.accounting);self.accounting=[]
        with self.assertRaises(ContractError):self.verify()
        self.accounting=original
        self.auth[0]['role']='builder';self.auth[0]['content_sha256']=canonical_hash(self.auth[0],{'content_sha256'})
        self.events[1]['payload']['authorization_sha256']=self.auth[0]['content_sha256']
        with self.assertRaises(ContractError):self.verify()

    def test_reservation_sequence_and_invocation_mismatch_refuse(self):
        reservation=self.accounting[0]['payload']['reservation']
        for field,value in (('call_sequence',True),('call_sequence',2),('invocation_sha256','0'*64),('role','builder')):
            before=reservation[field];reservation[field]=value
            try:
                with self.subTest(field=field,value=value),self.assertRaises(ContractError):self.verify()
            finally:reservation[field]=before

    def test_reordered_duplicated_and_orphan_outputs_refuse(self):
        original=deepcopy(self.events)
        variants=[original+[original[2]], [original[0],original[2]],deepcopy(original)]
        variants[-1][2]['sequence']=1
        for events in variants:
            self.events=events
            with self.assertRaises(ContractError):self.verify()

    def test_self_rehashed_accounting_substitution_refuses(self):
        for field,value in (('call_sequence',True),('role','builder'),('provider','other'),('model','other'),
                            ('request_sha256','0'*64),('public_drill_record',{})):
            original=deepcopy(self.calls[0]);self.calls[0][field]=value
            self.calls[0]['content_sha256']=canonical_hash(self.calls[0],{'content_sha256'})
            try:
                with self.subTest(field=field,value=value),self.assertRaises(ContractError):self.verify()
            finally:self.calls[0]=original

    def test_unfinished_request_stays_incomplete(self):
        self.events.pop();self.calls=[]
        result=self.verify()
        self.assertFalse(result['output_plan_complete'])
        self.assertFalse(result['controller_origin_verified'])
        self.assertEqual(result['unfinished_public_calls'],1)

    def test_receipt_dictionary_cannot_construct_native_provider(self):
        with self.assertRaisesRegex(ContractError,'native-live-context'):
            PublicDrillProvider(self.admission,self.script)

    def test_native_receipt_snapshot_preserves_exact_final_scan_tail(self):
        receipt=dict(ledger_head_sha256='a'*64,status='passed')
        receipt['content_sha256']=canonical_hash(receipt)
        summary=dict(receipt_sha256=receipt['content_sha256'])
        events=[dict(event_sha256='a'*64)]
        for name,value in (('run-receipt-before-memory',{k:v for k,v in receipt.items() if k!='content_sha256'}),
                           ('run-receipt',receipt),('run-summary',summary)):
            raw=json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')
            events.append(dict(event_sha256=name,kind='model_isolation_scan_passed',payload=dict(
                status='passed',scanned=[dict(artifact=name,sha256=sha256(raw).hexdigest())])))
        self.assertEqual(verify_receipt_tail(receipt,summary,events),1)
        changed=deepcopy(events);changed[-1]['payload']['scanned'][0]['sha256']='0'*64
        with self.assertRaises(ContractError):verify_receipt_tail(receipt,summary,changed)
        changed=deepcopy(events);changed[-1]['kind']='public_drill_call_started'
        with self.assertRaises(ContractError):verify_receipt_tail(receipt,summary,changed)

    def test_missing_receipt_snapshot_and_extra_tail_refuse(self):
        receipt=dict(ledger_head_sha256='a'*64)
        with self.assertRaises(ContractError):verify_receipt_tail(receipt,{},[])
        self.assertEqual(verify_receipt_tail(receipt,{},[dict(event_sha256='a'*64)]),1)
        with self.assertRaises(ContractError):
            verify_receipt_tail(receipt,{},[dict(event_sha256='a'*64),dict(event_sha256='b'*64)])

    def test_self_rehashed_authorization_cannot_substitute_admitted_bindings(self):
        original = deepcopy(self.auth)
        original_start = deepcopy(self.events[1])
        for field in ('work_order_sha256', 'execution_policy_sha256', 'plan_sha256',
                      'decision_sha256', 'trusted_journal_head', 'nonce_sha256'):
            with self.subTest(field=field):
                self.auth = deepcopy(original)
                self.events[1] = deepcopy(original_start)
                self.auth[0][field] = '0' * 64
                self.auth[0]['content_sha256'] = canonical_hash(self.auth[0], {'content_sha256'})
                self.events[1]['payload']['authorization_sha256'] = self.auth[0]['content_sha256']
                with self.assertRaisesRegex(ContractError, 'reservation-or-role'):
                    self.verify()
        self.auth = original
        self.events[1] = original_start
        result = self.verify()
        self.assertTrue(result['output_plan_complete'])
        self.assertFalse(result['controller_origin_verified'])

    def test_failed_call_accounting_cannot_become_completed_public_output(self):
        self.events.pop()
        failed = dict(provider='p5-scripted', model=self.script['model'], role='planner',
                      call_sequence=1, status='failed', usage='reserved-upper-bound')
        failed['content_sha256'] = canonical_hash(failed)
        self.calls = [failed]
        result = self.verify()
        self.assertFalse(result['output_plan_complete'])
        self.assertFalse(result['controller_origin_verified'])
        self.assertEqual(result['completed_public_calls'], 0)
        self.assertEqual(result['unfinished_public_calls'], 1)
        self.assertEqual(result['accounted_calls'], 1)
        for field, value in (('status', 'completed'), ('usage', 'observed'),
                             ('provider', 'other'), ('model', 'other'),
                             ('call_sequence', True), ('call_sequence', 2)):
            with self.subTest(field=field, value=value):
                changed = deepcopy(failed)
                changed[field] = value
                changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
                self.calls = [changed]
                with self.assertRaisesRegex(ContractError, 'unmatched-call'):
                    self.verify()
        self.calls = [failed]
        self.assertFalse(self.verify()['output_plan_complete'])


if __name__=='__main__':unittest.main()
