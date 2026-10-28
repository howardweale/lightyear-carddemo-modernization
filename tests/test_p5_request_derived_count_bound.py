"""CI-only engineering guarantees; no assertion of provider billing bounds."""
import copy
from decimal import Decimal
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.controller_count_accounting import bind_controller_counts
from lightyear_factory.count_charge_account import CountChargeAccount, replay_count_charges
from lightyear_factory.count_request_bound import (
    bound_basis, request_bound_basis, serialized_count_bound, validate_retained_basis)
from lightyear_factory.flex_billing import flex_billing_policy
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator, _reconcile_accounting_journal
from lightyear_factory.providers import OpenAIResponsesProvider


def request(text='public synthetic input'):
    return json.dumps(dict(model='gpt-5.4-2026-03-05',instructions='public instructions',input=text,
        text=dict(format=dict(type='json_schema',name='lightyear_planner_artifact',strict=True,
                              schema={'type':'object'}))),separators=(',',':')).encode()


class RequestDerivedCountBoundTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        no_network=patch('socket.create_connection',side_effect=AssertionError('network forbidden'))
        no_network.start();self.addCleanup(no_network.stop)

    def book(self,other='0'):
        events=[]
        book=CountChargeAccount(flex_billing_policy(),cap_usd='10',attempt_identity_sha256='a'*64,
            other_exposure_usd=lambda:Decimal(other),durable_append=events.append)
        return book,events

    def test_exact_full_wire_bytes_and_two_messages_determine_hold(self):
        for value in ('','ascii','\u03bb\U0001f642','quote"\\newline\n'):
            raw=request(value);basis=request_bound_basis(raw);bound=serialized_count_bound(raw)
            self.assertEqual(bound.input_tokens,2*len(raw)+2048)
            self.assertEqual(basis['logical_messages'],2)
            self.assertEqual(bound.request_sha256,hashlib.sha256(raw).hexdigest())
            self.assertEqual(bound.evidence_sha256,canonical_hash(basis))
            self.assertFalse(basis['provider_bound_proven'])
            self.assertFalse(basis['billing_final'])

    def test_context_boundary_is_exact_and_refuses_before_parse(self):
        self.assertEqual(bound_basis('a'*64,523976)['input_tokens'],1050000)
        with self.assertRaisesRegex(ContractError,'context-before-send'):
            request_bound_basis(b'x'*523977)

    def test_unknown_surface_duplicates_nonfinite_and_surrogates_refuse(self):
        original=json.loads(request())
        cases=[dict(original,tools=[]),dict(original,conversation='synthetic'),
               dict(original,model='gpt-5.4'),dict(original,input=[{'type':'input_image'}])]
        raw_cases=[json.dumps(v).encode() for v in cases]
        raw_cases.extend([request().replace(b'"input":',b'"model":"duplicate","input":',1),
            request().replace(b'"public synthetic input"',b'NaN'),
            request().replace(b'"public synthetic input"',b'"\\ud800"'),b'\xff'])
        for raw in raw_cases:
            with self.subTest(raw=raw[:30]),self.assertRaises(ContractError):serialized_count_bound(raw)

    def test_mutated_bytes_or_rehashed_numeric_profile_refuse(self):
        raw=request();bound=serialized_count_bound(raw)
        with self.assertRaises(ContractError):bound.validate(raw+b' ')
        basis=request_bound_basis(raw);basis['margin']=1;basis['input_tokens']=len(raw)+2048
        with self.assertRaises(ContractError):
            validate_retained_basis(basis,basis['request_sha256'],basis['input_tokens'],canonical_hash(basis))

    def test_shared_cap_equality_admits_one_increment_over_refuses(self):
        raw=request();bound=serialized_count_bound(raw)
        cost=Decimal(bound.input_tokens)*Decimal('5.50')/1000000
        book,events=self.book(str(Decimal(10)-cost));book.reserve(raw,bound)
        self.assertEqual(Decimal(events[0]['reserved_cost_usd']),cost)
        book,events=self.book(str(Decimal(10)-cost+Decimal('0.0000001')))
        with self.assertRaises(ContractError):book.reserve(raw,bound)
        self.assertEqual(events,[])

    def test_only_one_request_derived_count_can_be_in_flight(self):
        raw=request();book,events=self.book();book.reserve(raw,serialized_count_bound(raw))
        with self.assertRaisesRegex(ContractError,'in-flight'):book.reserve(raw,serialized_count_bound(raw))
        self.assertEqual(len(events),1)

    def test_unknown_result_retains_hold_stops_later_calls_and_replays_stopped(self):
        raw=request();bound=serialized_count_bound(raw);book,events=self.book()
        ticket=book.reserve(raw,bound);book.observe(ticket,None)
        with self.assertRaises(ContractError):book.reserve(raw,bound)
        report=replay_count_charges(events,flex_billing_policy(),cap_usd='10',attempt_identity_sha256='a'*64)
        self.assertTrue(report['stopped']);self.assertFalse(report['billing_final'])
        self.assertEqual(report['calls'][0]['charge_usd'],events[0]['reserved_cost_usd'])

    def test_over_bound_result_records_actual_conservative_charge_then_stops(self):
        raw=request();bound=serialized_count_bound(raw);book,events=self.book()
        ticket=book.reserve(raw,bound)
        with self.assertRaisesRegex(ContractError,'bound-or-cap-exceeded'):book.observe(ticket,bound.input_tokens+1)
        self.assertEqual(events[-1]['counted_input_tokens'],bound.input_tokens+1)
        self.assertEqual(events[-1]['released_excess_usd'],'0')
        with self.assertRaises(ContractError):book.reserve(raw,bound)
        report=replay_count_charges(events,flex_billing_policy(),cap_usd='10',attempt_identity_sha256='a'*64)
        self.assertTrue(report['stopped'])

    def test_success_releases_only_excess_retains_nonzero_charge_and_basis(self):
        raw=request();book,events=self.book();ticket=book.reserve(raw,serialized_count_bound(raw));book.observe(ticket,17)
        self.assertEqual(book.snapshot()['count_exposure_usd'],'0.0000935')
        self.assertEqual(book.snapshot()['calls'][0]['bound_basis'],request_bound_basis(raw))
        self.assertIsNone(events[-1]['provider_billed_cost_usd'])

    def controller(self,mode='normal',directory=None):
        if directory is None:
            temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        else:
            temp=SimpleNamespace(name=directory)
        sends=[]
        c=FactoryOrchestrator.__new__(FactoryOrchestrator)
        def opened(req,**kwargs):
            retained=RunLedger(c._receipt_journal.path);self.assertTrue(retained.verify())
            physical=retained.events[-1]['payload']['reservation']
            self.assertEqual(physical['request_sha256'],hashlib.sha256(req.data).hexdigest())
            sends.append(req.full_url)
            rows=[e['payload']['event'] for e in retained.events if e['kind']=='count_financial']
            if req.full_url.endswith('/input_tokens'):
                self.assertEqual(rows[-1]['bound_basis'],request_bound_basis(req.data))
                self.assertEqual(rows[-1]['reserved_input_tokens'],2*len(req.data)+2048)
                if mode=='kill-after-count-send':
                    with (Path(temp.name)/'sent.txt').open('wb') as stream:
                        stream.write(b'one count send; no generation\n');stream.flush();os.fsync(stream.fileno())
                    os._exit(79)
                if mode=='unknown':raise TimeoutError('synthetic interruption')
                count=rows[-1]['reserved_input_tokens']+1 if mode=='over' else 17
                value=dict(input_tokens=count)
            else:
                self.assertEqual(rows[-1]['counted_input_tokens'],17)
                value=dict(model='gpt-5.4-2026-03-05',status='completed',service_tier='flex',
                    output=[dict(content=[dict(type='output_text',text='{"ok":true}')])],
                    usage=dict(input_tokens=17,output_tokens=1))
            result=io.BytesIO(json.dumps(value).encode());result.headers={};return result
        provider=OpenAIResponsesProvider('synthetic-credential',model='gpt-5.4-2026-03-05',opener=opened,
            input_usd_per_million=5.5,output_usd_per_million=24.75,max_output_tokens=16,
            max_retries=0,service_tier='flex',billing_policy=flex_billing_policy())
        budget=AccountedModelProvider(provider,SimpleNamespace(max_model_cost_usd=10))
        c.agents=SimpleNamespace(bounded_provider=budget);c._receipt_identity={'content_sha256':'a'*64}
        c._receipt_journal=RunLedger(Path(temp.name)/'attempt.jsonl')
        c._receipt_started=time.monotonic();c._receipt_transports=[];c._receipt_pending=False
        header=bind_controller_counts(c)
        c._receipt_journal.append('READY','model_reservations',dict(attempt_identity_sha256='a'*64,protocol=5,**header))
        c._checkpoint_accounting();c._bind_reservation_journal()
        instruction='Public synthetic control.';schema={'type':'object','properties':{'ok':{'type':'boolean'}}}
        digest=canonical_hash(dict(instruction=instruction,payload={},schema=schema))
        cost=(100*5.5+16*24.75)/1000000
        c._reserve_model_call(dict(call_sequence=1,role='planner',request_sha256=digest,invocation_sha256=digest,
            input_tokens=100,output_tokens=16,estimated_cost_usd=cost))
        invoke=lambda:budget._complete_with_transport_journal('planner',instruction,{},schema,100,16,5.5,24.75)
        return c,sends,invoke

    def test_controller_default_uses_real_request_bound_before_stub_count_opener(self):
        c,sends,invoke=self.controller();result=invoke()
        self.assertEqual(result.content,{'ok':True});self.assertEqual(len(sends),2)
        report=_reconcile_accounting_journal(c._receipt_journal.events,'a'*64)
        self.assertEqual(report['count_financial_accounting']['count_account']['count_exposure_usd'],'0.0000935')

    def test_controller_unknown_and_over_bound_each_allow_only_the_count_send(self):
        for mode in ('unknown','over'):
            with self.subTest(mode=mode):
                c,sends,invoke=self.controller(mode)
                with self.assertRaises(Exception):invoke()
                self.assertEqual(len(sends),1);self.assertTrue(sends[0].endswith('/input_tokens'))
                with self.assertRaises(Exception):invoke()
                self.assertEqual(len(sends),1)
                report=_reconcile_accounting_journal(c._receipt_journal.events,'a'*64)
                self.assertTrue(report['count_financial_accounting']['count_account']['stopped'])

    def test_controller_replay_refuses_stripped_required_basis(self):
        c,sends,invoke=self.controller();invoke();events=copy.deepcopy(c._receipt_journal.events)
        event=next(e['payload']['event'] for e in events if e['kind']=='count_financial')
        del event['bound_basis'];event['content_sha256']=canonical_hash(event,{'content_sha256'})
        with self.assertRaisesRegex(ContractError,'basis-missing'):_reconcile_accounting_journal(events,'a'*64)

    def test_abrupt_exit_before_reserve_proves_zero_count_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,'-B',__file__,'--count-kill-child','before',directory],
                                  capture_output=True,timeout=60)
            self.assertEqual(result.returncode,78,result.stderr.decode(errors='replace'))
            self.assertFalse((Path(directory)/'sent.txt').exists())
            journal=RunLedger(Path(directory)/'attempt.jsonl');self.assertTrue(journal.verify())
            self.assertFalse(any(e['kind'] in {'count_financial','model_transport_reserved'} for e in journal.events))

    def test_abrupt_exit_after_count_send_replays_full_hold_without_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,'-B',__file__,'--count-kill-child','after',directory],
                                  capture_output=True,timeout=60)
            self.assertEqual(result.returncode,79,result.stderr.decode(errors='replace'))
            self.assertEqual((Path(directory)/'sent.txt').read_bytes(),b'one count send; no generation\n')
            journal=RunLedger(Path(directory)/'attempt.jsonl');self.assertTrue(journal.verify())
            transports=[e for e in journal.events if e['kind']=='model_transport_reserved']
            self.assertEqual(len(transports),1)
            self.assertEqual(transports[0]['payload']['reservation']['transport_kind'],'input-token-count')
            report=_reconcile_accounting_journal(journal.events,'a'*64)['count_financial_accounting']
            row=report['count_account']['calls'][0]
            self.assertEqual(row['state'],'reserved-unknown');self.assertEqual(row['charge_usd'],row['reserved_cost_usd'])
            self.assertFalse(report['billing_final'])


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--count-kill-child':
        case=RequestDerivedCountBoundTests();case.setUp()
        mode=sys.argv[2];directory=sys.argv[3]
        if mode not in {'before','after'}:raise SystemExit(80)
        controller,sends,invoke=case.controller('kill-after-count-send',directory)
        if mode=='before':controller._receipt_count_account.book._append=lambda event:os._exit(78)
        invoke();raise SystemExit(81)
    else:unittest.main()
