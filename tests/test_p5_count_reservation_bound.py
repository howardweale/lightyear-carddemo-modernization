"""CI-only count/reservation boundary tests; synthetic HTTP, no provider calls."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import _reconcile_accounting_journal
from lightyear_factory.providers import OpenAIResponsesProvider, ProviderError
from lightyear_factory.transport_journal import TransportJournalError, transport_journal_scope
from test_p5_transport_replay import IDENTITY, observation, reservation, snapshot


class CountReservationBoundTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(prefix='p5-count-bound-')
        self.addCleanup(self.temp.cleanup)
        self.serial = 0

    def invoke(self, count, bound, *, mutate=False, fail_observe=False):
        sent, events = [], []
        self.serial += 1
        ledger = RunLedger(Path(self.temp.name)/f'boundary-{self.serial}')
        def durable(kind, value):
            event = ledger.append(kind.upper(), kind, value)
            with ledger.path.open('ab') as stream:
                os.fsync(stream.fileno())
            return event
        schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                  'required': ['ok'], 'additionalProperties': False}
        def reserve(record):
            durable('reserve', record)
            events.append(('reserve', copy.deepcopy(record)))
            return len(events)
        def observe(ticket, record):
            if fail_observe:
                raise TimeoutError('synthetic fsync refusal')
            durable('observe', record)
            events.append(('observe', copy.deepcopy(record)))
        def opener(request, **kwargs):
            self.assertEqual(events[-1][0], 'reserve')
            self.assertEqual(events[-1][1]['request_sha256'], hashlib.sha256(request.data).hexdigest())
            persisted = RunLedger(ledger.path)
            self.assertTrue(persisted.verify())
            self.assertEqual(persisted.events[-1]['payload']['request_sha256'], hashlib.sha256(request.data).hexdigest())
            if not request.full_url.endswith('/input_tokens'):
                self.assertEqual(persisted.events[-2]['kind'], 'observe')
                self.assertEqual(persisted.events[-2]['payload']['input_token_count'], count)
            sent.append(request.full_url)
            if request.full_url.endswith('/input_tokens'):
                if mutate:
                    schema['properties']['later'] = {'type': 'string'}
                payload = {'input_tokens': count}
            else:
                payload = {'status': 'completed', 'model': 'test-model',
                           'output': [{'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}],
                           'usage': {'input_tokens': count, 'output_tokens': 1}}
            stream = io.BytesIO(json.dumps(payload).encode())
            stream.headers = {}
            return stream
        provider = OpenAIResponsesProvider('synthetic-credential', model='test-model', opener=opener,
            max_output_tokens=16, input_usd_per_million=1, output_usd_per_million=1,
            max_retries=0)
        error = result = None
        with transport_journal_scope(reserve, observe,
                invocation={'call_sequence': 1, 'invocation_sha256': 'a'*64},
                bounds={'input_tokens': bound, 'output_tokens': 16,
                        'estimated_cost_usd': (bound+16)/1_000_000,
                        'cost_estimate_available': True}):
            try:
                with patch('lightyear_factory.providers.urlopen', side_effect=AssertionError('network forbidden')):
                    result = provider.complete('planner', 'quote \\" and snowman ☃', {'text': 'é\n'}, schema)
            except (TransportJournalError, ProviderError) as exc:
                error = exc
        return sent, events, result, error

    def test_count_equal_bound_sends_but_bound_plus_one_never_reserves_generation(self):
        for bound in (7, 59998, 60000):
            with self.subTest(bound=bound):
                sent, events, result, error = self.invoke(bound, bound)
                self.assertIsNone(error)
                self.assertIsNotNone(result)
                self.assertEqual(len(sent), 2)
                self.assertEqual(events[1][1]['input_token_count'], bound)
                self.assertIsNone(events[1][1]['response_usage'])
                self.assertIsNone(events[1][1]['estimated_cost_usd'])
                self.assertFalse(events[1][1]['cost_estimate_available'])
                preflight = events[2][1]['input_token_preflight']
                self.assertEqual(preflight['input_tokens'], bound)
                self.assertEqual(preflight['count_request_sha256'], events[0][1]['request_sha256'])
                self.assertEqual(preflight['count_projection_sha256'], events[0][1]['canonical_request_sha256'])
                sent, events, result, error = self.invoke(bound+1, bound)
                self.assertIsInstance(error, (TransportJournalError, ProviderError))
                self.assertIsNone(result)
                self.assertEqual(len(sent), 1)
                self.assertEqual([kind for kind, _ in events], ['reserve', 'observe'])

    def test_invalid_count_never_becomes_durable_valid_count_or_generation(self):
        for count in (True, -1, 1.5, '7', None):
            with self.subTest(count=count):
                sent, events, result, error = self.invoke(count, 20)
                self.assertIsInstance(error, ProviderError)
                self.assertEqual(len(sent), 1)
                self.assertIsNone(events[1][1]['input_token_count'])
                self.assertIsNone(result)

    def test_changed_projection_and_failed_count_fsync_stop_generation(self):
        sent, events, result, error = self.invoke(7, 20, mutate=True)
        self.assertIsInstance(error, TransportJournalError)
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(events), 2)
        sent, events, result, error = self.invoke(7, 20, fail_observe=True)
        self.assertIsInstance(error, TransportJournalError)
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(events), 1)

    def replay(self, actions, protocol=4):
        self.serial += 1
        path = Path(self.temp.name)/str(self.serial)
        ledger = RunLedger(path)
        ledger.append('READY', 'model_reservations', dict(attempt_identity_sha256=IDENTITY, protocol=protocol))
        ledger.append('OBSERVED', 'sanitized_accounting', dict(attempt_identity_sha256=IDENTITY, accounting=snapshot()))
        ticket = None
        sequence = 0
        for kind, value in actions:
            if kind == 'reserve':
                sequence += 1
                event = ledger.append('RESERVED', 'model_transport_reserved', dict(
                    attempt_identity_sha256=IDENTITY, transport_sequence=sequence, reservation=value))
                ticket = dict(attempt_identity_sha256=IDENTITY, transport_sequence=sequence,
                              request_sha256=value['request_sha256'], reservation_event_sha256=event['event_sha256'])
            else:
                ledger.append('OBSERVED', 'model_transport_observed', dict(
                    attempt_identity_sha256=IDENTITY, reservation_ticket=ticket, observation=value))
        self.assertTrue(ledger.verify())
        return _reconcile_accounting_journal(RunLedger(path).events, IDENTITY)

    def actions(self):
        counted = reservation(kind='input-token-count')
        observed = dict(observation(kind='input-token-count'), input_token_count=7)
        generation = dict(reservation(), input_token_preflight=dict(input_tokens=7,
            count_request_sha256=counted['request_sha256'],
            count_projection_sha256=counted['canonical_request_sha256']))
        return [('reserve', counted), ('observe', observed), ('reserve', generation)]

    def test_replay_keeps_durable_count_and_pending_generation_separate_from_usage(self):
        result = self.replay(self.actions())
        rows = result['model_transport_accounting']
        self.assertEqual(rows[0]['observation']['input_token_count'], 7)
        self.assertIsNone(rows[0]['observation']['response_usage'])
        self.assertEqual(result['calls'], 0)
        self.assertEqual(result['input_tokens'], 0)
        self.assertEqual(result['in_flight_final_usage'], 'unknown; reserved upper bound recorded')
        self.assertEqual(result['reserved_in_flight']['input_tokens'], 999)

    def test_hash_valid_count_binding_mutations_fail_closed(self):
        cases = []
        for key, bad in [('input_tokens', 8), ('count_request_sha256', 'f'*64),
                         ('count_projection_sha256', 'f'*64)]:
            rows = self.actions()
            rows[-1][1]['input_token_preflight'][key] = bad
            cases.append(rows)
        rows = self.actions(); rows[1][1]['input_token_count'] = True; cases.append(rows)
        rows = self.actions(); del rows[1][1]['input_token_count']; cases.append(rows)
        rows = self.actions(); rows[-1][1]['input_token_preflight'] = None; cases.append(rows)
        rows = self.actions(); del rows[-1][1]['input_token_preflight']; cases.append(rows)
        rows = self.actions(); rows[1][1]['input_token_count'] = 1000
        rows[-1][1]['input_token_preflight']['input_tokens'] = 1000; cases.append(rows)
        cases.append([self.actions()[-1]])
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ContractError):
                self.replay(rows)

    def test_legacy_protocol_two_remains_readable_without_claiming_count_evidence(self):
        result = self.replay([('reserve', reservation(kind='input-token-count')),
                              ('observe', observation(kind='input-token-count'))], protocol=2)
        self.assertNotIn('input_token_count', result['model_transport_accounting'][0]['observation'])
        with self.assertRaises(ContractError):
            self.replay([], protocol=3)


if __name__ == '__main__':
    unittest.main()
