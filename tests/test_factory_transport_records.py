"""CI-only raw byte and accounting fixtures. No real provider or screen code."""
import base64
from contextlib import contextmanager
from http.client import IncompleteRead
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPSHandler, ProxyHandler
from urllib.response import addinfourl
from email.message import Message
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from lightyear_factory.additional_providers import (
    JSONProvider, TransportError, AnthropicMessagesProvider, GeminiProvider)
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError
from lightyear_factory.ledger import RunLedger
from lightyear_factory.model_transport_records import ModelTransportRecorder
from lightyear_factory.orchestrator import ArtifactStore


class FixtureProvider(JSONProvider):
    provider_id = 'fixture-offline'
    def request(self, instruction, payload, schema):
        return 'https://fixture.invalid', {'Authorization': self.api_key}, dict(
            instruction=instruction, payload=payload, schema=schema)
    def parse(self, response):
        return response['content'], dict(input_tokens=7, output_tokens=3)


class TransportRecordTests(unittest.TestCase):
    key = b'0123456789abcdef' * 2
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
              'required': ['ok'], 'additionalProperties': False}
    good = b'{ "model":"fixture-2026-10-18", "content": {"ok":true} }\n'

    def setup_provider(self, root, raw=None, failure=None):
        store = ArtifactStore(root / 'artifacts', 'fixture-records')
        ledger = RunLedger(root / 'events.jsonl')
        recorder = ModelTransportRecorder(store, ledger, key=self.key,
                                          key_id='fixture-key', attempt=1)
        calls = []
        @contextmanager
        def opener(request, **kwargs):
            calls.append(request.data)
            if failure is not None: raise failure
            with BytesIO(self.good if raw is None else raw) as response: yield response
        provider = FixtureProvider('fixture-2026-10-18', api_key='fixture-credential',
            input_usd_per_million=1, output_usd_per_million=1, max_output_tokens=8,
            opener=opener, transport_recorder=recorder)
        order = SimpleNamespace(max_model_calls=3, max_model_input_bytes=100000,
            max_model_output_bytes=100000, max_model_tokens=100000,
            max_model_cost_usd=1, max_elapsed_seconds=120)
        return AccountedModelProvider(provider, order), recorder, ledger, calls

    def decrypt(self, root, ref):
        envelope = json.loads((root / ref['path']).read_bytes())
        aad = json.dumps(envelope['context'], sort_keys=True, separators=(',', ':')).encode()
        return AESGCM(self.key).decrypt(base64.b64decode(envelope['nonce_base64']),
            base64.b64decode(envelope['ciphertext_base64']), aad)

    def call(self, provider):
        return provider.complete('builder', 'private fixture prompt', {}, self.schema)

    def test_default_recorded_transport_refuses_redirect_before_second_request(self):
        # The real urllib handler chain is exercised with an offline HTTPS leaf.
        for code in (301,302,303,307,308):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as d:
                root=Path(d); p,r,ledger,unused=self.setup_provider(root)
                seen=[]; raw=b'private redirect response'
                class OfflineHTTPS(HTTPSHandler):
                    def https_open(self, request):
                        seen.append((request.full_url,request.data))
                        if len(seen)>1:
                            raise AssertionError('redirect sent a second request')
                        headers=Message();headers['Location']='https://other.invalid/target'
                        response=addinfourl(BytesIO(raw),headers,request.full_url,code)
                        response.msg='fixture redirect'
                        return response
                def offline_builder(*handlers):
                    return build_opener(ProxyHandler({}),OfflineHTTPS(),*handlers)
                with patch('lightyear_factory.additional_providers.build_opener',
                           side_effect=offline_builder),patch(
                           'lightyear_factory.additional_providers.urlopen',
                           side_effect=AssertionError('global opener used')):
                    p.provider=FixtureProvider('fixture-2026-10-18',
                        api_key='fixture-credential',input_usd_per_million=1,
                        output_usd_per_million=1,max_output_tokens=8,
                        transport_recorder=r)
                    with self.assertRaises(TransportError):self.call(p)
                self.assertEqual(1,len(seen));self.assertEqual([],unused)
                self.assertEqual(1,len(p.calls));self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
                ref=p.calls[0]['transport_record'];self.assertEqual('http-error',ref['status'])
                self.assertEqual(seen[0][1],self.decrypt(root,ref['request']))
                self.assertEqual(raw,self.decrypt(root,ref['response']))
                self.assertTrue(ref['response_complete']);self.assertTrue(ledger.verify())
                self.assertEqual(2,len(ledger.events));self.assertNotIn(raw.decode(),ledger.path.read_text())
                self.assertNotIn('fixture-credential',ledger.path.read_text())

    def test_exact_wire_bytes_and_measured_accounting_join_the_same_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p,r,ledger,calls=self.setup_provider(root)
            result=self.call(p); ref=result.evidence['transport_record']
            self.assertEqual(calls[0],self.decrypt(root,ref['request']))
            self.assertEqual(self.good,self.decrypt(root,ref['response']))
            self.assertTrue(ref['response_complete']); self.assertEqual(1,ref['attempt'])
            self.assertEqual('fixture-2026-10-18',ref['configured_model_version'])
            self.assertEqual(7,p.input_tokens); self.assertEqual(3,p.output_tokens)
            self.assertEqual(ref,p.calls[0]['transport_record']); self.assertTrue(ledger.verify())
            self.assertEqual(2,len(ledger.events)); self.assertNotIn('private fixture prompt',ledger.path.read_text())
            self.assertNotIn('fixture-credential',ledger.path.read_text())

    def test_http_error_and_malformed_response_retained_before_reserved_failure(self):
        cases=[(b'private rejected response',True),(b'not JSON at all',False)]
        for raw,http_error in cases:
            with self.subTest(http_error=http_error),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                failure=HTTPError('https://fixture.invalid',429,'fixture',{},BytesIO(raw)) if http_error else None
                p,r,ledger,calls=self.setup_provider(root,raw=raw,failure=failure)
                with self.assertRaises((TransportError,ContractError)): self.call(p)
                self.assertEqual(1,len(calls)); self.assertEqual(1,len(p.calls))
                self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
                ref=p.calls[0]['transport_record']; self.assertEqual(raw,self.decrypt(root,ref['response']))
                self.assertTrue(ref['response_complete']); self.assertTrue(ledger.verify())
                self.assertNotIn(raw.decode(),ledger.path.read_text())

    def test_partial_response_is_explicitly_incomplete_and_cannot_claim_full_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p,r,ledger,calls=self.setup_provider(root,failure=IncompleteRead(b'prefix',5))
            with self.assertRaises(TransportError): self.call(p)
            ref=p.calls[0]['transport_record']; self.assertFalse(ref['response_complete'])
            self.assertEqual(b'prefix',self.decrypt(root,ref['response']))

    def test_recorder_failure_stops_before_network_and_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as d:
            p,r,ledger,calls=self.setup_provider(Path(d))
            with patch.object(r.store,'write_encrypted',side_effect=OSError('fixture')):
                with self.assertRaises(ContractError): self.call(p)
            with self.assertRaises(ContractError): self.call(p)
            self.assertEqual([],calls); self.assertEqual([],ledger.events)

    def test_response_persistence_failure_is_accounted_and_poisoned(self):
        with tempfile.TemporaryDirectory() as d:
            p,r,ledger,calls=self.setup_provider(Path(d)); real=r.store.write_encrypted
            def write(kind,*args,**kwargs):
                if kind=='model-response':raise OSError('fixture')
                return real(kind,*args,**kwargs)
            with patch.object(r.store,'write_encrypted',side_effect=write):
                with self.assertRaises(ContractError): self.call(p)
            self.assertEqual(1,len(calls)); self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
            self.assertEqual('started',p.calls[0]['transport_record']['status'])
            with self.assertRaises(ContractError): self.call(p)
            self.assertEqual(1,len(calls))

    def test_cap_stops_before_transport_or_record_and_retries_count_separately(self):
        with tempfile.TemporaryDirectory() as d:
            p,r,ledger,calls=self.setup_provider(Path(d)); p.order.max_model_tokens=1
            with self.assertRaises(ContractError):self.call(p)
            self.assertEqual([],calls);self.assertEqual([],ledger.events)
            p.order.max_model_tokens=100000
            self.call(p);self.call(p)
            self.assertEqual(2,len(calls));self.assertEqual(2,len(p.calls))
            self.assertNotEqual(p.calls[0]['transport_record']['start_event_sha256'],
                                p.calls[1]['transport_record']['start_event_sha256'])

    def test_request_failure_after_success_cannot_reuse_previous_wire_record(self):
        with tempfile.TemporaryDirectory() as d:
            p,r,ledger,calls=self.setup_provider(Path(d))
            self.call(p)
            prior=p.calls[0]['transport_record']
            # The wrapper builds once for admission; fail the actual transport build.
            admitted=p.provider.request('private fixture prompt',{},self.schema)
            with patch.object(p.provider,'request',side_effect=[admitted,ContractError('fixture request failure')]):
                with self.assertRaises(ContractError):self.call(p)
            self.assertEqual(1,len(calls));self.assertEqual(2,len(ledger.events))
            self.assertEqual(prior,p.calls[0]['transport_record'])
            self.assertEqual('reserved-upper-bound',p.calls[1]['usage'])
            self.assertNotIn('transport_record',p.calls[1])
            self.assertIsNone(p.provider.last_transport_record)

    def test_later_read_failure_retains_all_received_chunks_without_retry(self):
        for error in (OSError('private transport detail'), IncompleteRead(b'tail', 9)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as d:
                root=Path(d); p,r,ledger,calls=self.setup_provider(root)
                class PartialResponse:
                    def __init__(self): self.parts=iter([b'first', b'second'])
                    def read(self, size):
                        try: return next(self.parts)
                        except StopIteration: raise error
                @contextmanager
                def opener(request, **kwargs):
                    calls.append(request.data)
                    yield PartialResponse()
                p.provider.opener=opener
                with self.assertRaises(TransportError): self.call(p)
                self.assertEqual(1,len(calls)); self.assertEqual(1,len(p.calls))
                ref=p.calls[0]['transport_record']
                expected=b'firstsecond'+(b'tail' if isinstance(error,IncompleteRead) else b'')
                self.assertEqual(expected,self.decrypt(root,ref['response']))
                self.assertFalse(ref['response_complete'])
                self.assertEqual('transport-error',ref['status'])
                self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
                self.assertNotIn('private transport detail',ledger.path.read_text())
                self.assertTrue(ledger.verify())

    def test_close_failure_retains_completed_body_and_reserved_accounting(self):
        for raw in (self.good, b''):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as d:
                root=Path(d); p,r,ledger,calls=self.setup_provider(root)
                @contextmanager
                def opener(request, **kwargs):
                    calls.append(request.data)
                    with BytesIO(raw) as response:
                        yield response
                    raise OSError('private close detail')
                p.provider.opener=opener
                with self.assertRaises(TransportError): self.call(p)
                self.assertEqual(1,len(calls)); self.assertEqual(1,len(p.calls))
                ref=p.calls[0]['transport_record']
                self.assertEqual(raw,self.decrypt(root,ref['response']))
                self.assertTrue(ref['response_complete'])
                self.assertEqual('transport-error',ref['status'])
                self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
                self.assertNotIn('private close detail',ledger.path.read_text())
                self.assertTrue(ledger.verify())

    def test_http_close_failure_keeps_complete_or_partial_body_and_accounting(self):
        for close_error in (OSError, TimeoutError, URLError):
            for raw, partial in ((b'private rejected body', False), (b'', False),
                                 (b'private partial body', True)):
                with self.subTest(close_error=close_error.__name__, partial=partial, raw=raw), tempfile.TemporaryDirectory() as d:
                    root=Path(d)
                    failure=HTTPError('https://fixture.invalid',429,'fixture',{},BytesIO(raw))
                    p,r,ledger,calls=self.setup_provider(root,failure=failure)
                    with patch.object(failure,'close',side_effect=close_error('private close detail')) as close:
                        if partial:
                            with patch.object(failure,'read',side_effect=IncompleteRead(raw,9)):
                                with self.assertRaises(TransportError) as caught:self.call(p)
                        else:
                            with self.assertRaises(TransportError) as caught:self.call(p)
                    self.assertEqual(1,close.call_count)
                    self.assertEqual(1,len(calls));self.assertEqual(1,len(p.calls))
                    ref=p.calls[0]['transport_record']
                    self.assertEqual(raw,self.decrypt(root,ref['response']))
                    self.assertEqual(not partial,ref['response_complete'])
                    self.assertEqual('http-error',ref['status'])
                    self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
                    self.assertEqual(429,caught.exception.safe_dict()['status_code'])
                    self.assertIsNone(r.pending);self.assertFalse(r.failed)
                    self.assertEqual(2,len(ledger.events));self.assertTrue(ledger.verify())
                    public=ledger.path.read_text()+str(caught.exception)
                    self.assertNotIn('private close detail',public)
                    self.assertNotIn('private rejected body',public)
                    self.assertNotIn('private partial body',public)

    def test_http_close_failure_cannot_mask_poisoned_response_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            failure=HTTPError('https://fixture.invalid',429,'fixture',{},BytesIO(b'private body'))
            p,r,ledger,calls=self.setup_provider(root,failure=failure)
            real=r.store.write_encrypted
            def write(kind,*args,**kwargs):
                if kind=='model-response':raise OSError('private persistence detail')
                return real(kind,*args,**kwargs)
            with patch.object(failure,'close',side_effect=OSError('private close detail')) as close:
                with patch.object(r.store,'write_encrypted',side_effect=write):
                    with self.assertRaisesRegex(ContractError,'transport-record-persistence-failed') as caught:
                        self.call(p)
            self.assertEqual(1,close.call_count);self.assertTrue(r.failed)
            self.assertEqual(1,len(calls));self.assertEqual(1,len(p.calls))
            self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
            self.assertEqual('started',p.calls[0]['transport_record']['status'])
            self.assertEqual(1,len(ledger.events));self.assertTrue(ledger.verify())
            self.assertNotIn('private',str(caught.exception))
            with self.assertRaises(ContractError):self.call(p)
            self.assertEqual(1,len(calls))

    def test_valid_json_with_invalid_envelope_or_usage_is_retained_and_accounted(self):
        cases = [(FixtureProvider, value) for value in (None, [], [1], 7, True, "private shape marker")]
        for usage in (None, [], 7, True, "private shape marker"):
            cases.append((AnthropicMessagesProvider, dict(model='fixture-2026-10-18',
                stop_reason='end_turn', content=[dict(type='text',text='{"ok":true}')], usage=usage)))
            cases.append((GeminiProvider, dict(modelVersion='fixture-2026-10-18',
                candidates=[dict(finishReason='STOP',content=dict(parts=[dict(text='{"ok":true}')]))],
                usageMetadata=usage)))
        for provider_type, value in cases:
            with self.subTest(provider=provider_type.__name__, value=value), tempfile.TemporaryDirectory() as d:
                root=Path(d); raw=json.dumps(value).encode()
                p,r,ledger,calls=self.setup_provider(root,raw=raw)
                p.provider=provider_type('fixture-2026-10-18',api_key='fixture-credential',
                    input_usd_per_million=1,output_usd_per_million=1,max_output_tokens=8,
                    opener=p.provider.opener,transport_recorder=r)
                with self.assertRaisesRegex(ContractError,'invalid provider structured result or usage') as caught:
                    self.call(p)
                self.assertEqual(1,len(calls));self.assertEqual(1,len(p.calls))
                self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
                ref=p.calls[0]['transport_record']
                self.assertEqual(raw,self.decrypt(root,ref['response']))
                self.assertTrue(ref['response_complete']);self.assertEqual('response',ref['status'])
                self.assertIsNone(r.pending);self.assertFalse(r.failed)
                self.assertEqual(2,len(ledger.events));self.assertTrue(ledger.verify())
                self.assertNotIn('private shape marker',ledger.path.read_text()+str(caught.exception))

    def test_adapter_usage_mapping_contract_is_refused_inside_accounted_boundary(self):
        for usage in (None, [], {}, {'input_tokens':7}, {'output_tokens':3}):
            with self.subTest(usage=usage),tempfile.TemporaryDirectory() as d:
                root=Path(d);p,r,ledger,calls=self.setup_provider(root)
                with patch.object(p.provider,'parse',return_value=({'ok':True},usage)):
                    with self.assertRaisesRegex(ContractError,'invalid provider structured result or usage'):
                        self.call(p)
                self.assertEqual(1,len(calls));self.assertEqual(1,len(p.calls))
                self.assertEqual('reserved-upper-bound',p.calls[0]['usage'])
                ref=p.calls[0]['transport_record']
                self.assertEqual(self.good,self.decrypt(root,ref['response']))
                self.assertTrue(ref['response_complete']);self.assertTrue(ledger.verify())
