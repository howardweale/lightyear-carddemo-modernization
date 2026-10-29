"""CI-only native controller journal tests; synthetic HTTP and input bound.

No admission is forged and no full run is claimed. These invoke the controller
journal boundary directly; real signed full-controller cases remain separate.
"""
import copy
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.controller_count_accounting import bind_controller_counts, unavailable_count_bound
from lightyear_factory.count_charge_account import CountInputBound, CountChargeJournalError
from lightyear_factory.flex_billing import flex_billing_policy
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator, _reconcile_accounting_journal
from lightyear_factory.providers import OpenAIResponsesProvider, ProviderError
from lightyear_factory.transport_journal import TransportJournalError


class ControllerCountAccountingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.sends = []
        self.count_failure = None
        self.provider = OpenAIResponsesProvider('synthetic-credential',
            model='gpt-5.4-2026-03-05', opener=self.open,
            input_usd_per_million=5.5, output_usd_per_million=24.75,
            max_output_tokens=16, max_retries=0, service_tier='flex', billing_policy=flex_billing_policy())
        self.budget = AccountedModelProvider(self.provider, SimpleNamespace(max_model_cost_usd=10))
        self.controller = FactoryOrchestrator.__new__(FactoryOrchestrator)
        c = self.controller
        c.agents = SimpleNamespace(bounded_provider=self.budget)
        c._receipt_identity = {'content_sha256': 'a'*64}
        c._receipt_journal = RunLedger(Path(self.temp.name)/'attempt-accounting.jsonl')
        c._receipt_started = time.monotonic(); c._receipt_transports = []; c._receipt_pending = False
        header = bind_controller_counts(c)
        # These existing component tests retain their original synthetic profile.
        # The new live-profile tests separately exercise the real default resolver.
        header.pop('count_bound_profile')
        c._receipt_count_account.profile = None
        c._receipt_journal.append('READY', 'model_reservations',
            dict(attempt_identity_sha256='a'*64, protocol=5, **header))
        c._checkpoint_accounting(); c._bind_reservation_journal()
        self.component = c._receipt_count_account
        # Preserve the original missing-resolver negative fixture explicitly.
        # New default-resolver integration cases live in a separate test class.
        self.component.resolver = unavailable_count_bound
        self.instruction = 'Return a public synthetic control.'
        self.schema = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']}
        self.invocation_hash = canonical_hash(dict(instruction=self.instruction,payload={},schema=self.schema))
        self.cost = (100*5.5+16*24.75)/1000000
        c._reserve_model_call(dict(call_sequence=1, role='planner', request_sha256=self.invocation_hash,
            invocation_sha256=self.invocation_hash,input_tokens=100,output_tokens=16,estimated_cost_usd=self.cost))
        no_network = patch('socket.create_connection',side_effect=AssertionError('real network forbidden'))
        no_network.start(); self.addCleanup(no_network.stop)

    def synthetic_bound(self, raw):
        return CountInputBound(hashlib.sha256(raw).hexdigest(), 100, 'b'*64)

    def open(self, request, **kwargs):
        retained = RunLedger(self.controller._receipt_journal.path)
        self.assertTrue(retained.verify())
        self.assertEqual(retained.events[-1]['kind'], 'model_transport_reserved')
        physical = retained.events[-1]['payload']['reservation']
        self.assertEqual(physical['request_sha256'], hashlib.sha256(request.data).hexdigest())
        self.sends.append(request.full_url)
        counts = [e['payload']['event'] for e in retained.events if e['kind']=='count_financial']
        if request.full_url.endswith('/input_tokens'):
            self.assertEqual(counts[-1]['kind'], 'count_charge_reserved')
            self.assertEqual(counts[-1]['other_exposure_usd'], str(Decimal(str(self.cost))))
            if self.count_failure: raise self.count_failure
            payload = dict(input_tokens=17)
        else:
            self.assertEqual(counts[-1]['kind'], 'count_charge_observed')
            self.assertEqual(counts[-1]['counted_input_tokens'], 17)
            self.assertEqual(json.loads(request.data)['service_tier'], 'flex')
            payload = dict(model='gpt-5.4-2026-03-05',status='completed',service_tier='flex',
                output=[dict(content=[dict(type='output_text',text='{"ok":true}')])],
                usage=dict(input_tokens=17,output_tokens=1))
        result=io.BytesIO(json.dumps(payload).encode()); result.headers={}; return result

    def invoke(self):
        return self.budget._complete_with_transport_journal('planner',self.instruction,{},self.schema,
                                                          100,16,5.5,24.75)

    def replay(self, events=None):
        return _reconcile_accounting_journal(events or self.controller._receipt_journal.events,'a'*64)

    def test_real_controller_callbacks_retain_count_and_native_physical_evidence(self):
        self.component.resolver = self.synthetic_bound
        result = self.invoke()
        self.assertEqual(result.content, {'ok':True})
        self.assertEqual(len(self.sends),2)
        self.assertIsNone(self.provider.count_account)
        self.assertIsNone(self.provider.count_bound_resolver)
        report = self.replay()['count_financial_accounting']
        self.assertEqual(report['count_account']['count_exposure_usd'],'0.0000935')
        self.assertEqual(report['pending_generation_reserve_usd'],str(Decimal(str(self.cost))))
        self.assertIs(report['billing_final'],False)
        self.assertIsNone(report['actual_provider_cost_usd'])

    def test_unestablished_pre_send_bound_refuses_without_transport_or_count_charge(self):
        with self.assertRaisesRegex(ContractError,'bound-not-established-before-send'): self.invoke()
        self.assertEqual(self.sends,[])
        self.assertFalse(any(e['kind']=='count_financial' for e in self.controller._receipt_journal.events))
        self.assertEqual(self.replay()['count_financial_accounting']['count_account']['calls'],[])

    def test_failed_count_is_held_with_no_generation_and_native_recovery(self):
        self.component.resolver = self.synthetic_bound
        self.count_failure = TimeoutError('synthetic count timeout')
        with self.assertRaises(ProviderError): self.invoke()
        self.assertEqual(len(self.sends),1)
        self.assertEqual(self.replay()['count_financial_accounting']['count_account']['count_exposure_usd'],'0.00055')

    def test_existing_journal_fsync_failure_stops_before_every_transport(self):
        self.component.resolver = self.synthetic_bound
        with patch('lightyear_factory.controller_count_accounting.os.fsync',side_effect=TimeoutError('synthetic fsync')):
            with self.assertRaises(CountChargeJournalError): self.invoke()
        self.assertEqual(self.sends,[])
        report=self.replay()['count_financial_accounting']
        self.assertTrue(report['pending_count_before_send'])
        self.assertEqual(report['count_account']['count_exposure_usd'],'0.00055')

    def test_removed_or_rehashed_financial_evidence_never_replays_as_paid_or_zero(self):
        self.component.resolver = self.synthetic_bound; self.invoke()
        original=self.controller._receipt_journal.events
        missing=[e for e in original if e['kind']!='count_financial']
        with self.assertRaises(ContractError): self.replay(missing)
        changed=copy.deepcopy(original)
        row=next(e['payload']['event'] for e in changed if e['kind']=='count_financial')
        row['other_exposure_usd']='0'; row['content_sha256']=canonical_hash(row,{'content_sha256'})
        with self.assertRaisesRegex(ContractError,'generation-exposure'): self.replay(changed)


    def test_live_financial_sink_refuses_protocol_downgrade_before_send(self):
        self.component.resolver = self.synthetic_bound
        old = self.controller._receipt_journal
        replacement = RunLedger(Path(self.temp.name)/'old-protocol.jsonl')
        for index, event in enumerate(old.events):
            payload = copy.deepcopy(event['payload'])
            if index == 0:
                payload = dict(attempt_identity_sha256='a'*64, protocol=2)
            replacement.append(event['state'],event['kind'],payload)
        old.path.write_bytes(replacement.path.read_bytes())
        before = old.path.read_bytes()
        with self.assertRaises(CountChargeJournalError): self.invoke()
        self.assertEqual(self.sends,[])
        self.assertEqual(old.path.read_bytes(),before)

    def test_live_generation_requires_financial_settlement_not_just_durable_count(self):
        self.component.resolver = self.synthetic_bound
        with patch.object(self.component.book,'observe',return_value=None):
            with self.assertRaises(TransportJournalError) as caught:
                self.invoke()
        self.assertIsInstance(caught.exception.__cause__,ContractError)
        self.assertEqual(str(caught.exception.__cause__),
                         'count-controller-generation-before-durable-settlement')
        self.assertEqual(len(self.sends),1)
        events=RunLedger(self.controller._receipt_journal.path).events
        self.assertFalse(any(e['kind']=='model_transport_reserved' and
            e['payload']['reservation']['transport_kind']=='responses' for e in events))
        report=self.replay()['count_financial_accounting']['count_account']['calls']
        self.assertEqual(report[-1]['state'],'reserved-unknown')

    def test_count_component_cannot_be_detached_to_downgrade_live_header(self):
        before=self.controller._receipt_journal.path.read_bytes()
        self.budget.count_controller=None
        with self.assertRaisesRegex(ContractError,'live-header-binding'):
            self.controller._checkpoint_accounting()
        self.assertEqual(self.controller._receipt_journal.path.read_bytes(),before)


if __name__=='__main__': unittest.main()
