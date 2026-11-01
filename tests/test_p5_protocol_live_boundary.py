"""CI-only live-write versus legacy replay boundary; no authority or network.

The synthetic admission-shaped object exercises journal initialization only.
It is not passed to admission validation and grants no execution authority.
"""
import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator, _reconcile_accounting_journal
from lightyear_factory.providers import OpenAIResponsesProvider
from lightyear_factory.transport_journal import TransportJournalError, transport_journal_scope
from test_p5_transport_replay import IDENTITY, observation, reservation, snapshot


class ProtocolLiveBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(prefix='p5-live-protocol-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.serial = 0

    def sink(self, protocol=4):
        self.serial += 1
        sink = FactoryOrchestrator.__new__(FactoryOrchestrator)
        sink._receipt_identity = dict(content_sha256=IDENTITY)
        sink._receipt_journal = RunLedger(self.root/str(self.serial)/'accounting.jsonl')
        sink._receipt_journal.append('READY', 'model_reservations',
            dict(attempt_identity_sha256=IDENTITY, protocol=protocol))
        sink._receipt_journal.append('OBSERVED', 'sanitized_accounting',
            dict(attempt_identity_sha256=IDENTITY, accounting=snapshot()))
        return sink

    def refuse(self, sink, value):
        before = sink._receipt_journal.path.read_bytes()
        with self.assertRaises((ContractError, TransportJournalError)):
            sink._reserve_model_transport(value)
        self.assertEqual(sink._receipt_journal.path.read_bytes(), before)

    def generation(self, counted):
        return dict(reservation(), input_token_preflight=dict(input_tokens=7,
            count_request_sha256=counted['request_sha256'],
            count_projection_sha256=counted['canonical_request_sha256']))

    def count(self, sink):
        counted = reservation(kind='input-token-count')
        ticket = sink._reserve_model_transport(counted)
        sink._observe_model_transport(ticket,
            dict(observation(kind='input-token-count'), input_token_count=7))
        return counted

    def test_new_initialization_writes_four_and_cannot_reopen_existing_attempt(self):
        run = self.root/'new-run'
        run.mkdir()
        workspace = self.root/'workspace.json'
        workspace.write_text('{}', encoding='utf-8')
        admission = dict(status='passed', work_order_sha256='b'*64, nonce_sha256='c'*64)
        admission['content_sha256'] = canonical_hash(admission)
        controller = FactoryOrchestrator.__new__(FactoryOrchestrator)
        controller.model_admission = object()
        controller.execution_context = SimpleNamespace(admission_receipt=admission)
        controller.factory_input_paths = dict(workspace=str(workspace))
        controller.workspace_read_manifest = {}
        controller.agents = SimpleNamespace(bounded_provider=None)
        with patch.object(controller, '_failure_accounting', return_value=snapshot()):
            controller._begin_reconciliation_evidence(run, 'new-run',
                SimpleNamespace(content_sha256='b'*64))
            journal = RunLedger(run/'attempt-accounting.jsonl')
            self.assertTrue(journal.verify())
            self.assertEqual(journal.events[0]['payload']['protocol'], 4)
            before = journal.path.read_bytes()
            with self.assertRaises(FileExistsError):
                controller._begin_reconciliation_evidence(run, 'new-run',
                    SimpleNamespace(content_sha256='b'*64))
            self.assertEqual(journal.path.read_bytes(), before)

    def test_archived_two_generation_replays_read_only_but_live_writes_are_refused(self):
        sink = self.sink(protocol=2)
        value = reservation()
        event = sink._receipt_journal.append('RESERVED', 'model_transport_reserved',
            dict(attempt_identity_sha256=IDENTITY, transport_sequence=1, reservation=value))
        before = sink._receipt_journal.path.read_bytes()
        loaded = RunLedger(sink._receipt_journal.path)
        self.assertTrue(loaded.verify())
        replay = _reconcile_accounting_journal(loaded.events, IDENTITY)
        self.assertEqual(replay['reserved_in_flight']['input_tokens'], 999)
        self.assertNotIn('input_token_preflight', replay['model_transport_accounting'][0]['reservation'])
        self.assertEqual(sink._receipt_journal.path.read_bytes(), before)
        ticket = dict(attempt_identity_sha256=IDENTITY, transport_sequence=1,
            request_sha256=value['request_sha256'], reservation_event_sha256=event['event_sha256'])
        with self.assertRaises(TransportJournalError):
            sink._observe_model_transport(ticket, observation())
        self.assertEqual(sink._receipt_journal.path.read_bytes(), before)
        with self.assertRaises(TransportJournalError):
            sink._reserve_model_call(dict(call_sequence=1, role='planner',
                request_sha256='b'*64, invocation_sha256='b'*64,
                input_tokens=999, output_tokens=16, estimated_cost_usd=.01079))
        self.assertEqual(sink._receipt_journal.path.read_bytes(), before)
        with self.assertRaises(TransportJournalError):
            sink._checkpoint_accounting()
        self.assertEqual(sink._receipt_journal.path.read_bytes(), before)
        for value in (reservation(), reservation(kind='input-token-count')):
            self.refuse(self.sink(protocol=2), value)

    def test_new_journal_rejects_legacy_null_and_unbacked_generation_before_append(self):
        counted = reservation(kind='input-token-count')
        for value in (reservation(), dict(reservation(), input_token_preflight=None),
                      self.generation(counted)):
            with self.subTest(value=value):
                self.refuse(self.sink(), value)

    def test_no_count_adapter_is_refused_before_stub_send_or_journal_write(self):
        for protocol in (2, 4):
            with self.subTest(protocol=protocol):
                sink = self.sink(protocol)
                sent = []
                def opener(request, **kwargs):
                    sent.append(request.full_url)
                    raise AssertionError('generation reached the stub without a durable count')
                provider = OpenAIResponsesProvider('fixture-not-a-secret', model='test-model',
                    opener=opener, token_preflight=False, max_retries=0,
                    max_output_tokens=16, input_usd_per_million=10, output_usd_per_million=50)
                before = sink._receipt_journal.path.read_bytes()
                value = reservation()
                with transport_journal_scope(sink._reserve_model_transport, sink._observe_model_transport,
                        invocation=value['invocation'], bounds=value['bounds']), \
                     patch('lightyear_factory.providers.urlopen', side_effect=AssertionError('network forbidden')):
                    with self.assertRaises(TransportJournalError):
                        provider.complete('planner', 'synthetic', {'x': 1},
                            {'type': 'object', 'properties': {}, 'additionalProperties': False})
                self.assertEqual(sent, [])
                self.assertEqual(sink._receipt_journal.path.read_bytes(), before)

    def test_live_generation_uses_persisted_matching_count_and_replays(self):
        sink = self.sink()
        counted = self.count(sink)
        for key, bad in (('input_tokens', 8), ('count_request_sha256', 'f'*64),
                         ('count_projection_sha256', 'f'*64)):
            value = self.generation(counted)
            value['input_token_preflight'][key] = bad
            self.refuse(sink, value)
        ticket = sink._reserve_model_transport(self.generation(counted))
        loaded = RunLedger(sink._receipt_journal.path)
        self.assertTrue(loaded.verify())
        self.assertEqual(loaded.events[-1]['event_sha256'], ticket['reservation_event_sha256'])
        self.assertEqual(loaded.events[-2]['payload']['observation']['input_token_count'], 7)
        result = _reconcile_accounting_journal(loaded.events, IDENTITY)
        self.assertEqual(result['reserved_in_flight']['reservation_ticket'], ticket)

    def test_unobserved_failed_count_and_old_observation_shape_cannot_authorize_generation(self):
        for mode in ('unobserved', 'failed', 'old-shape'):
            sink = self.sink()
            counted = reservation(kind='input-token-count')
            ticket = sink._reserve_model_transport(counted)
            if mode == 'failed':
                sink._observe_model_transport(ticket,
                    dict(observation(failed=True, kind='input-token-count'), input_token_count=None))
            elif mode == 'old-shape':
                before = sink._receipt_journal.path.read_bytes()
                with self.assertRaises(TransportJournalError):
                    sink._observe_model_transport(ticket, observation(kind='input-token-count'))
                self.assertEqual(sink._receipt_journal.path.read_bytes(), before)
            self.refuse(sink, self.generation(counted))

    def test_live_journal_downgrade_or_memory_only_count_is_refused(self):
        sink = self.sink()
        counted = self.count(sink)
        good = sink._receipt_journal.path.read_bytes()
        events = copy.deepcopy(sink._receipt_journal.events)
        replacement = self.root/'downgraded.jsonl'
        old = RunLedger(replacement)
        for index, event in enumerate(events):
            payload = event['payload']
            if index == 0:
                payload['protocol'] = 2
            old.append(event['state'], event['kind'], payload)
        sink._receipt_journal.path.write_bytes(replacement.read_bytes())
        self.refuse(sink, self.generation(counted))
        sink._receipt_journal = RunLedger(sink._receipt_journal.path)
        self.refuse(sink, self.generation(counted))
        # An in-memory observation cannot substitute for the persisted count.
        sink._receipt_journal.path.write_bytes(good)
        sink._receipt_journal = RunLedger(sink._receipt_journal.path)
        sink._receipt_journal.path.write_bytes(b'\n'.join(good.splitlines()[:2])+b'\n')
        self.refuse(sink, self.generation(counted))


if __name__ == '__main__':
    unittest.main()
