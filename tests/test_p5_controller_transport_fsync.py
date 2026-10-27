"""CI-only real journal sink / stub transport boundary; no admission authority.

No keys, signing, sockets, provider service or full-controller run. This covers
actual sink fsync ordering and adapter failures, not the worker network drill.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator, _reconcile_accounting_journal
from lightyear_factory.providers import OpenAIResponsesProvider, ProviderError
from lightyear_factory.transport_journal import TransportJournalError, transport_journal_scope


IDENTITY = 'a' * 64
SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
          'required': ['ok'], 'additionalProperties': False}
BOUNDS = dict(input_tokens=999, output_tokens=16, estimated_cost_usd=.01079,
              cost_estimate_available=True)


class ControllerTransportFsyncTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(prefix='p5-real-sink-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.serial = 0

    def exercise(self, *, fail_sync=None, fail_transport=None, enabled=True, retries=0):
        self.serial += 1
        path = self.root/str(self.serial)/'attempt-accounting.jsonl'
        sink = FactoryOrchestrator.__new__(FactoryOrchestrator)
        sink._receipt_identity = {'content_sha256': IDENTITY}
        sink._receipt_journal = RunLedger(path)
        ledger = sink._receipt_journal
        ledger.append('READY', 'model_reservations',
                      dict(attempt_identity_sha256=IDENTITY, protocol=2))
        ledger.append('OBSERVED', 'sanitized_accounting', dict(
            attempt_identity_sha256=IDENTITY,
            accounting=dict(schema='factory-sanitized-accounting/1', calls=0,
                input_tokens=0, output_tokens=0, estimated_cost_usd=0,
                duration_ms=0, duration_basis='observed-through-checkpoint',
                call_hashes=[], scanned_transports=[], in_flight_final_usage='none',
                billing_final=False)))
        real_fsync = os.fsync
        synced = []
        attempted = []
        sent = []
        sleeps = []

        def sync(fd):
            last = RunLedger(path).events[-1]
            attempted.append(last['kind'])
            if len(attempted) == fail_sync:
                raise TimeoutError('synthetic sink fsync refusal')
            real_fsync(fd)
            synced.append(last['event_sha256'])

        def opener(request, **kwargs):
            kind = 'input-token-count' if request.full_url.endswith('/input_tokens') else 'responses'
            if enabled:
                last = RunLedger(path).events[-1]
                self.assertEqual(last['kind'], 'model_transport_reserved')
                self.assertEqual(last['event_sha256'], synced[-1])
                record = last['payload']['reservation']
                self.assertEqual(record['transport_kind'], kind)
                self.assertEqual(record['request_sha256'], hashlib.sha256(request.data).hexdigest())
                self.assertEqual(record['bounds'], BOUNDS)
                self.assertEqual(last['payload']['attempt_identity_sha256'], IDENTITY)
            sent.append(kind)
            if kind == fail_transport:
                raise URLError('synthetic connection lost')
            payload = (dict(input_tokens=7) if kind == 'input-token-count' else
                dict(model='test-model', status='completed',
                     output=[dict(content=[dict(type='output_text', text='{"ok":true}')])],
                     usage=dict(input_tokens=7, output_tokens=3)))
            response = io.BytesIO(json.dumps(payload).encode())
            response.headers = {}
            return response

        provider = OpenAIResponsesProvider('fixture-not-a-secret', model='test-model',
            opener=opener, input_usd_per_million=10, output_usd_per_million=50,
            max_output_tokens=16, max_retries=retries, sleep=sleeps.append,
            jitter=lambda upper: 0)
        from contextlib import nullcontext
        scope = (transport_journal_scope(sink._reserve_model_transport, sink._observe_model_transport,
            invocation=dict(call_sequence=1, invocation_sha256='b'*64), bounds=BOUNDS)
            if enabled else nullcontext())
        result = error = None
        with scope, patch('os.fsync', side_effect=sync), \
             patch('socket.create_connection', side_effect=AssertionError('network forbidden')), \
             patch('socket.socket', side_effect=AssertionError('network forbidden')), \
             patch('lightyear_factory.providers.time.monotonic', return_value=1000.0):
            try:
                result = provider.complete('planner', 'fixture', {'input': 'fixture'}, SCHEMA)
            except (ProviderError, TransportJournalError) as caught:
                error = caught
        return dict(result=result, error=error, sent=sent, attempted=attempted,
                    synced=synced, sleeps=sleeps, events=RunLedger(path).events)

    def test_real_sink_fsync_precedes_count_and_generation_with_result_parity(self):
        bound = self.exercise()
        plain = self.exercise(enabled=False)
        self.assertIsNone(bound['error'])
        self.assertIsNone(plain['error'])
        self.assertEqual(bound['result'], plain['result'])
        self.assertEqual(bound['sent'], ['input-token-count', 'responses'])
        self.assertEqual(bound['attempted'], ['model_transport_reserved', 'model_transport_observed']*2)
        physical = bound['events'][2:]
        self.assertEqual([e['event_sha256'] for e in physical], bound['synced'])
        for reserve, observed in zip(physical[::2], physical[1::2]):
            ticket = observed['payload']['reservation_ticket']
            self.assertEqual(ticket['reservation_event_sha256'], reserve['event_sha256'])
            self.assertEqual(ticket['request_sha256'], reserve['payload']['reservation']['request_sha256'])

    def test_real_reservation_fsync_failure_prevents_the_corresponding_send(self):
        for fail_sync, expected in ((1, []), (3, ['input-token-count'])):
            with self.subTest(fail_sync=fail_sync):
                row = self.exercise(fail_sync=fail_sync, retries=3)
                self.assertIsInstance(row['error'], TransportJournalError)
                self.assertEqual(row['sent'], expected)
                self.assertEqual(row['sleeps'], [])
                self.assertEqual(row['attempted'][-1], 'model_transport_reserved')
                self.assertNotIn(row['events'][-1]['event_sha256'], row['synced'])

    def test_real_observation_fsync_failure_stops_before_generation_and_retry(self):
        row = self.exercise(fail_sync=2, retries=3)
        self.assertIsInstance(row['error'], TransportJournalError)
        self.assertEqual(row['sent'], ['input-token-count'])
        self.assertEqual(row['sleeps'], [])
        self.assertEqual(row['attempted'], ['model_transport_reserved', 'model_transport_observed'])
        self.assertEqual(len(row['synced']), 1)

    def test_stub_connection_loss_retains_exact_failed_transport_and_unknown_usage(self):
        for kind, expected in (('input-token-count', ['input-token-count']),
                               ('responses', ['input-token-count', 'responses'])):
            with self.subTest(kind=kind):
                row = self.exercise(fail_transport=kind)
                self.assertIsInstance(row['error'], ProviderError)
                self.assertEqual(row['sent'], expected)
                self.assertEqual(row['sleeps'], [])
                last = row['events'][-1]['payload']['observation']
                self.assertEqual(last['outcome'], 'failed')
                self.assertEqual(last['failure_type'], 'URLError')
                self.assertIsNone(last['response_usage'])
                self.assertIsNone(last['estimated_cost_usd'])
                replay = _reconcile_accounting_journal(row['events'], IDENTITY)
                failed = replay['unresolved_model_transports'][-1]
                self.assertEqual(failed['reservation']['transport_kind'], kind)
                self.assertEqual(failed['reservation']['bounds'], BOUNDS)
                self.assertEqual(failed['observation']['failure_type'], 'URLError')
                self.assertFalse(replay['billing_final'])
                self.assertEqual(replay['calls'], 0)


if __name__ == '__main__':
    unittest.main()
