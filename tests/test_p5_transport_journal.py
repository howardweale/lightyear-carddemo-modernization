"""CI-only actual OpenAI adapter with synthetic HTTP responses; no model calls."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.providers import OpenAIResponsesProvider
from lightyear_factory.transport_journal import TransportJournalError, transport_journal_scope


SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"], "additionalProperties": False}


def response_payload(text='{"ok":true}'):
    return {"model": "test-model", "status": "completed",
            "output": [{"content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 7, "output_tokens": 3}}


class TransportJournalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get("GITHUB_ACTIONS"), "true")
        temp = tempfile.TemporaryDirectory(prefix="p5-transport-journal-")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "attempt-accounting.jsonl"
        self.ledger = RunLedger(self.path)
        self.sent = []
        self.sleeps = []
        self.check_reservation = True

    def append(self, state, kind, payload):
        event = self.ledger.append(state, kind, payload)
        with self.path.open("ab") as stream:
            os.fsync(stream.fileno())
        return event

    def reserve(self, record):
        event = self.append("RESERVED", "transport_reserved", record)
        return event["event_sha256"]

    def observe(self, ticket, record):
        self.append("OBSERVED", "transport_observed", {"ticket": ticket, **record})

    def scope(self, reserve=None, observe=None):
        return transport_journal_scope(
            reserve or self.reserve, observe or self.observe,
            invocation={"call_sequence": 1, "invocation_sha256": "a" * 64},
            bounds={"input_tokens": 999, "output_tokens": 16,
                    "estimated_cost_usd": .01015})

    def provider(self, replies, **options):
        replies = iter(replies)
        def opener(request, **kwargs):
            digest = hashlib.sha256(request.data).hexdigest()
            if self.check_reservation:
                # Reload bytes independently before allowing the synthetic send.
                events = RunLedger(self.path).events
                self.assertEqual(events[-1]["kind"], "transport_reserved")
                self.assertEqual(events[-1]["payload"]["request_sha256"], digest)
                self.assertEqual(events[-1]["payload"]["request_bytes"], len(request.data))
            self.sent.append((request.full_url, digest))
            item = next(replies)
            if isinstance(item, BaseException):
                raise item
            stream = io.BytesIO(json.dumps(item).encode())
            stream.headers = {}
            return stream
        return OpenAIResponsesProvider("synthetic-credential", model="test-model",
            opener=opener, input_usd_per_million=10, output_usd_per_million=50,
            max_output_tokens=16, sleep=self.sleeps.append, jitter=lambda upper: 0,
            **options)

    def invoke(self, provider):
        with patch("lightyear_factory.providers.time.monotonic", return_value=1000.0):
            return provider.complete("planner", "test instruction", {"input": "test"}, SCHEMA)

    def test_count_and_response_each_have_durable_exact_byte_reservation(self):
        with self.scope():
            result = self.invoke(self.provider([{"input_tokens": 7}, response_payload()]))
        events = RunLedger(self.path).events
        self.assertEqual([e["kind"] for e in events],
            ["transport_reserved", "transport_observed"] * 2)
        reserved = events[::2]; observed = events[1::2]
        self.assertEqual([e["payload"]["transport_kind"] for e in reserved],
                         ["input-token-count", "responses"])
        self.assertEqual([e["payload"]["request_sha256"] for e in reserved],
                         [digest for url, digest in self.sent])
        self.assertEqual([e["payload"]["ticket"] for e in observed],
                         [e["event_sha256"] for e in reserved])
        self.assertIsNone(observed[0]["payload"]["response_usage"])
        self.assertIsNone(observed[0]["payload"]["estimated_cost_usd"])
        self.assertEqual(observed[1]["payload"]["response_usage"], response_payload()["usage"])
        self.assertEqual(observed[1]["payload"]["estimated_cost_usd"],
                         result.evidence["estimated_cost_usd"])
        self.assertTrue(self.ledger.verify())

    def test_reservation_fsync_failure_prevents_even_token_count_transport(self):
        def fail(record):
            raise TimeoutError("synthetic fsync failure")
        with self.scope(reserve=fail):
            with self.assertRaises(TransportJournalError):
                self.invoke(self.provider([], max_retries=3))
        self.assertEqual(self.sent, [])
        self.assertEqual(self.sleeps, [])
        self.assertFalse(self.path.exists())

    def test_observation_failure_is_not_retried_as_network_timeout(self):
        def fail(ticket, record):
            raise TimeoutError("synthetic observation fsync failure")
        with self.scope(observe=fail):
            with self.assertRaises(TransportJournalError):
                self.invoke(self.provider([response_payload()], token_preflight=False, max_retries=3))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sleeps, [])
        self.assertEqual([e["kind"] for e in self.ledger.events], ["transport_reserved"])

    def test_retry_preserves_each_ticket_and_normal_returned_evidence(self):
        def replies():
            return [HTTPError("https://api.openai.com/v1/responses", 429, "fixture", {},
                              io.BytesIO(b'{"error":{"code":"rate_limit_exceeded"}}')),
                    response_payload()]
        with self.scope():
            journalled = self.invoke(self.provider(replies(), token_preflight=False, max_retries=1))
        events = self.ledger.events
        self.assertEqual(len(events), 4)
        self.assertEqual([e["payload"]["provider_attempt"] for e in events[::2]], [1, 2])
        self.assertNotEqual(events[0]["event_sha256"], events[2]["event_sha256"])
        self.assertEqual(events[1]["payload"]["outcome"], "failed")
        self.assertIsNone(events[1]["payload"]["response_usage"])
        self.assertIsNone(events[1]["payload"]["estimated_cost_usd"])
        self.assertEqual(events[3]["payload"]["outcome"], "returned")
        self.assertEqual(events[3]["payload"]["response_usage"], response_payload()["usage"])
        self.check_reservation = False
        baseline = self.invoke(self.provider(replies(), token_preflight=False, max_retries=1))
        self.assertEqual(journalled, baseline)
        self.assertEqual(self.sleeps, [1.0, 1.0])
        self.assertEqual(len(self.ledger.events), 4)

    def test_reported_usage_survives_later_structured_content_rejection(self):
        with self.scope():
            with self.assertRaises(ContractError):
                self.invoke(self.provider([response_payload("not-json")], token_preflight=False))
        observation = self.ledger.events[-1]["payload"]
        self.assertEqual(observation["outcome"], "returned")
        self.assertEqual(observation["response_usage"], {"input_tokens": 7, "output_tokens": 3})
        self.assertEqual(observation["estimated_cost_usd"], .00022)
        self.assertEqual(len(self.sent), 1)


    def json_cases(self):
        from lightyear_factory.additional_providers import AnthropicMessagesProvider, GeminiProvider
        return [(AnthropicMessagesProvider, dict(stop_reason='end_turn',
                    content=[dict(type='text', text='{"ok":true}')],
                    usage=dict(input_tokens=4, cache_read_input_tokens=2, cache_creation_input_tokens=1, output_tokens=3))),
                (GeminiProvider, dict(candidates=[dict(finishReason='STOP', content=dict(parts=[dict(text='{"ok":true}')]))],
                    usageMetadata=dict(promptTokenCount=7, cachedContentTokenCount=2, candidatesTokenCount=2, thoughtsTokenCount=1)))]

    def json_provider(self, cls, reply):
        def opener(request, **kwargs):
            digest = hashlib.sha256(request.data).hexdigest()
            if self.check_reservation:
                last = RunLedger(self.path).events[-1]
                self.assertEqual(last['kind'], 'transport_reserved')
                self.assertEqual(last['payload']['request_sha256'], digest)
                self.assertEqual(last['payload']['request_bytes'], len(request.data))
                self.assertEqual(last['payload']['transport_kind'], cls.provider_id)
            self.sent.append((request.full_url, digest))
            return io.BytesIO(json.dumps(reply).encode())
        return cls('synthetic-2026-03-05', api_key='synthetic-credential', opener=opener,
                   input_usd_per_million=10, output_usd_per_million=50, max_output_tokens=16)

    def test_json_adapters_exact_reservation_and_normal_result_parity(self):
        for cls, reply in self.json_cases():
            with self.subTest(provider=cls.provider_id):
                self.check_reservation = False
                control = self.invoke(self.json_provider(cls, reply))
                self.check_reservation = True
                before = len(self.sent)
                with self.scope():
                    result = self.invoke(self.json_provider(cls, reply))
                self.assertEqual(len(self.sent), before+1)
                self.assertEqual(result, control)
                events = RunLedger(self.path).events
                self.assertEqual(events[-1]['payload']['ticket'], events[-2]['event_sha256'])
                self.assertEqual(events[-1]['payload']['response_usage'], dict(input_tokens=7, cached_input_tokens=2, output_tokens=3))
                self.assertEqual(events[-1]['payload']['estimated_cost_usd'], result.evidence['estimated_cost_usd'])

    def test_json_fsync_failures_stop_send_or_retry(self):
        def fail(*args):
            raise TimeoutError('synthetic journal fsync failure')
        for cls, reply in self.json_cases():
            with self.subTest(provider=cls.provider_id):
                before = len(self.sent)
                with self.scope(reserve=fail), self.assertRaises(TransportJournalError):
                    self.invoke(self.json_provider(cls, reply))
                self.assertEqual(len(self.sent), before)
                with self.scope(observe=fail), self.assertRaises(TransportJournalError):
                    self.invoke(self.json_provider(cls, reply))
                self.assertEqual(len(self.sent), before+1)
                self.assertEqual(RunLedger(self.path).events[-1]['kind'], 'transport_reserved')

    def test_json_invalid_content_keeps_completed_usage(self):
        for cls, reply in self.json_cases():
            if cls.provider_id == 'anthropic-messages':
                reply['content'][0]['text'] = 'not JSON'
            else:
                reply['candidates'][0]['content']['parts'][0]['text'] = 'not JSON'
            with self.subTest(provider=cls.provider_id), self.scope(), self.assertRaises(ContractError):
                self.invoke(self.json_provider(cls, reply))
            observed = RunLedger(self.path).events[-1]['payload']
            self.assertEqual(observed['response_usage'], dict(input_tokens=7, cached_input_tokens=2, output_tokens=3))
            self.assertEqual(observed['estimated_cost_usd'], .00022)

    def test_snapshot_rejection_keeps_usage_before_version_validation(self):
        from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
        bad = response_payload(); bad['model'] = 'wrong-2026-03-05'
        backing = self.provider([{'input_tokens': 7}, bad])
        provider = SnapshotOpenAIResponsesProvider('synthetic-credential', model='gpt-5.4-2026-03-05',
            opener=backing.opener, input_usd_per_million=10, output_usd_per_million=50,
            max_output_tokens=16, max_retries=0)
        with self.scope(), self.assertRaises(ContractError):
            self.invoke(provider)
        self.assertEqual(len(self.sent), 2)
        observed = RunLedger(self.path).events[-1]['payload']
        self.assertEqual(observed['outcome'], 'failed')
        self.assertEqual(observed['failure_type'], 'ContractError')
        self.assertEqual(observed['response_usage'], dict(input_tokens=7, output_tokens=3))
        self.assertEqual(observed['estimated_cost_usd'], .00022)



    def test_legacy_usage_coercion_return_parity_keeps_physical_usage_unpriced(self):
        cases = [('missing', None), ('empty', {}),
                 ('strings', dict(input_tokens='7', output_tokens='3')),
                 ('booleans', dict(input_tokens=True, output_tokens=False)),
                 ('floats', dict(input_tokens=7.9, output_tokens=3.1)),
                 ('negative', dict(input_tokens=-7, output_tokens=3)),
                 ('null-counts', dict(input_tokens=None, output_tokens=None)),
                 ('missing-output', dict(input_tokens=7))]
        for name, usage in cases:
            with self.subTest(usage=name):
                reply = response_payload()
                if name == 'missing':
                    del reply['usage']
                else:
                    reply['usage'] = usage
                self.check_reservation = False
                baseline = self.invoke(self.provider([reply], token_preflight=False, max_retries=0))
                self.check_reservation = True
                before = len(self.ledger.events)
                with self.scope():
                    journalled = self.invoke(self.provider([reply], token_preflight=False, max_retries=0))
                self.assertEqual(journalled, baseline)
                events = RunLedger(self.path).events
                self.assertEqual(len(events), before + 2)
                observed = events[-1]['payload']
                self.assertEqual(observed['outcome'], 'returned')
                # JSON equality distinguishes bool/float/string from integer coercion.
                self.assertEqual(json.dumps(observed['response_usage'], sort_keys=True),
                                 json.dumps(usage, sort_keys=True))
                self.assertIsNone(observed['estimated_cost_usd'])
                self.assertFalse(observed['cost_estimate_available'])
                self.assertIsNone(observed['failure_type'])
                self.assertTrue(self.ledger.verify())
        self.assertEqual(self.sleeps, [])

    def test_legacy_invalid_usage_error_parity_preserves_transport_return(self):
        cases = [(None, AttributeError), ([], AttributeError), ('invalid', AttributeError),
                 (dict(input_tokens='invalid', output_tokens=3), ValueError)]
        for usage, error in cases:
            with self.subTest(usage=usage):
                reply = response_payload(); reply['usage'] = usage
                self.check_reservation = False
                with self.assertRaises(error) as control:
                    self.invoke(self.provider([reply], token_preflight=False, max_retries=0))
                self.check_reservation = True
                before = len(self.ledger.events)
                with self.scope(), self.assertRaises(error) as journalled:
                    self.invoke(self.provider([reply], token_preflight=False, max_retries=0))
                self.assertEqual(str(journalled.exception), str(control.exception))
                self.assertEqual(len(self.ledger.events), before + 2)
                observed = RunLedger(self.path).events[-1]['payload']
                self.assertEqual(observed['outcome'], 'returned')
                self.assertIsNone(observed['failure_type'])
                self.assertEqual(observed['response_usage'], usage if isinstance(usage, dict) else None)
                self.assertIsNone(observed['estimated_cost_usd'])
                self.assertFalse(observed['cost_estimate_available'])
        self.assertEqual(self.sleeps, [])

if __name__ == "__main__":
    unittest.main()
