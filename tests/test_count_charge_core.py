"""CI-only extracted count accounting tests; no provider billing proof or network."""
from decimal import Decimal
import hashlib
import json
import os
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.count_charge_account import CountChargeAccount, replay_count_charges
from lightyear_factory.count_request_bound import (
    bound_basis, request_bound_basis, serialized_count_bound, validate_retained_basis)
from lightyear_factory.flex_billing import flex_billing_policy


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


if __name__ == "__main__":
    unittest.main()
