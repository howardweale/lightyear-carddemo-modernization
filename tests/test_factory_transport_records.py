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
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.contracts import ContractError
from lightyear_factory.ledger import RunLedger
from lightyear_factory.model_admission import FactoryModelAdmission
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
        # Component fixtures mock only the approval boundary; these injected
        # transports cannot satisfy real factory admission or qualify a receipt.
        admission = object.__new__(FactoryModelAdmission)
        self.enterContext(patch.object(admission, 'verify', return_value={'fixture': True}))
        return AccountedModelProvider(provider, order, model_admission=admission, runtime_admission=lambda:None), recorder, ledger, calls

    def decrypt(self, root, ref):
        envelope = json.loads((root / ref['path']).read_bytes())
        aad = json.dumps(envelope['context'], sort_keys=True, separators=(',', ':')).encode()
        return AESGCM(self.key).decrypt(base64.b64decode(envelope['nonce_base64']),
            base64.b64decode(envelope['ciphertext_base64']), aad)

    def call(self, provider):
        return provider.complete('builder', 'private fixture prompt', {}, self.schema)

    def test_real_analyst_role_keeps_original_accounting_and_canonical_record_role(self):
        content = dict(summary='fixture diagnosis', failure_codes=['value'],
                       builder_guidance='fixture guidance', risk='low')
        raw = json.dumps(dict(model='fixture-2026-10-18', content=content)).encode()
        for fails in (False, True):
            with self.subTest(fails=fails), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                error = HTTPError('https://fixture.invalid', 429, 'fixture', {},
                                  BytesIO(b'private analyst error')) if fails else None
                p, recorder, ledger, calls = self.setup_provider(root, raw=raw, failure=error)
                agents = ModelAgentSet(p.provider)
                order = SimpleNamespace(to_dict=lambda: {'fixture': True})
                # Use the existing role path and real accounted wrapper; only
                # work-order binding is supplied by this component fixture.
                with patch.object(agents, '_provider_for', return_value=p):
                    if fails:
                        with self.assertRaises(TransportError):
                            agents.analyze_failure(order, {'category': 'value'}, 1)
                    else:
                        self.assertEqual(content, agents.analyze_failure(
                            order, {'category': 'value'}, 1))
                self.assertEqual(1, len(calls)); self.assertEqual(1, len(p.calls))
                call = p.calls[0]; record = call['transport_record']
                self.assertEqual('failure_analyst', call['role'])
                self.assertEqual('analyst', record['role'])
                self.assertEqual('failure_analyst', record['requested_role'])
                self.assertEqual(1, record['attempt'])
                self.assertEqual('http-error' if fails else 'response', record['status'])
                self.assertEqual(calls[0], self.decrypt(root, record['request']))
                self.assertEqual(b'private analyst error' if fails else raw,
                                 self.decrypt(root, record['response']))
                self.assertEqual([call], agents.drain_evidence())
                self.assertEqual([], agents.drain_evidence())
                self.assertTrue(ledger.verify()); self.assertEqual(2, len(ledger.events))
                self.assertIsNone(recorder.pending); self.assertFalse(recorder.failed)
                if fails:
                    self.assertEqual('reserved-upper-bound', call['usage'])
                else:
                    self.assertEqual(7, p.input_tokens); self.assertEqual(3, p.output_tokens)
                self.assertNotIn('private analyst error', ledger.path.read_text())

    def test_unrecognized_or_case_changed_roles_refused_before_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            p, recorder, ledger, calls = self.setup_provider(Path(d))
            with patch.object(recorder.store, 'write_encrypted') as write:
                for role in ('reviewer', 'Analyst', 'failure-analyst', '', None):
                    with self.subTest(role=role), self.assertRaisesRegex(
                            ContractError, 'transport-record-role'):
                        recorder.begin(role, 'fixture-offline', 'fixture-2026-10-18', b'{}')
                write.assert_not_called()
            self.assertEqual([], calls); self.assertEqual([], ledger.events)
            self.assertIsNone(recorder.pending); self.assertFalse(recorder.failed)

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

    def test_wire_request_scan_refuses_before_network_and_encrypting(self):
        with tempfile.TemporaryDirectory() as d:
            p, recorder, ledger, calls = self.setup_provider(Path(d))
            seen = []
            def refuse(surface, raw):
                seen.append((surface, raw))
                raise ContractError('private scanner detail')
            recorder.isolation_scan = refuse
            with patch.object(recorder.store, 'write_encrypted') as write:
                with self.assertRaisesRegex(ContractError, 'transport-isolation-refused') as caught:
                    self.call(p)
                write.assert_not_called()
            self.assertEqual([], calls)
            self.assertEqual('builder-wire-request', seen[0][0])
            self.assertIn(b'private fixture prompt', seen[0][1])
            self.assertTrue(recorder.failed)
            self.assertNotIn('private scanner detail', str(caught.exception))
            self.assertEqual([], ledger.events)
            with self.assertRaises(ContractError): self.call(p)
            self.assertEqual([], calls)

    def test_raw_response_scan_includes_unparsed_fields_before_return(self):
        from lightyear_factory.isolation_scan import scan
        canaries = {name: name + '-' + 'x' * 40 for name in
                    ('expected-state', 'reference-output', 'session-answer')}
        raw = json.dumps(dict(model='fixture-2026-10-18', content={'ok': True},
                              ignored=canaries['reference-output'])).encode()
        with tempfile.TemporaryDirectory() as d:
            p, recorder, ledger, calls = self.setup_provider(Path(d), raw=raw)
            seen = []
            def inspect(surface, data):
                seen.append((surface, data))
                scan([(surface, data)], canaries, ())
            recorder.isolation_scan = inspect
            with self.assertRaisesRegex(ContractError, 'transport-isolation-refused'):
                self.call(p)
            self.assertEqual(1, len(calls))
            self.assertEqual(('builder-wire-response', raw), seen[-1])
            self.assertTrue(recorder.failed)
            self.assertFalse(any(e['kind'] == 'model-transport-finished' for e in ledger.events))
            self.assertNotIn(canaries['reference-output'], ledger.path.read_text())

    def test_error_and_partial_wire_bytes_are_scanned_and_poison_on_refusal(self):
        from unittest.mock import Mock
        for status, complete in [('http-error', True), ('http-error', False),
                                 ('transport-error', False), ('response', False)]:
            with self.subTest(status=status, complete=complete):
                store, ledger, inspect = Mock(), Mock(), Mock()
                store.run_id = 'fixture-scan'
                ledger.append.return_value = {'event_sha256': 'a' * 64}
                recorder = ModelTransportRecorder(store, ledger, key=b'x' * 32,
                    key_id='unused', attempt=1, isolation_scan=inspect)
                started = recorder.begin('failure_analyst', 'fixture-offline',
                                         'fixture-2026-10-18', b'safe request')
                inspect.side_effect = ValueError('private failure body')
                with self.assertRaisesRegex(ContractError, 'transport-isolation-refused') as caught:
                    recorder.finish(started, b'partial private wire', status=status, complete=complete)
                inspect.assert_called_with('analyst-wire-' + status, b'partial private wire')
                self.assertTrue(recorder.failed)
                self.assertEqual(1, store.write_encrypted.call_count)
                self.assertEqual(1, ledger.append.call_count)
                self.assertNotIn('private failure body', str(caught.exception))

    def test_strict_transport_requires_single_use_same_run_concrete_admission(self):
        from unittest.mock import Mock
        from lightyear_factory.contracts import canonical_hash
        with tempfile.TemporaryDirectory() as d:
            ledger=RunLedger(Path(d)/'events.jsonl')
            store=Mock(run_id='fixture-run')
            store.write_encrypted.return_value={'path':'fixture','sha256':'a'*64}
            def recorder():
                return ModelTransportRecorder(store,ledger,key=b'x'*32,key_id='fixture',attempt=1,
                    isolation_scan=lambda name,raw:None,work_order_sha256='a'*64,require_model_admission=True)
            approval=dict(schema='factory-model-admission/1',plan_sha256='b'*64,
                decision_sha256='c'*64,trusted_journal_head='d'*64,executable_commit='e'*40,
                work_order_sha256='a'*64,provider='fixture',model='fixture-2026-10-18',
                role='analyst',provider_verified=True)
            runtime=dict(approval,provider=None,model=None,role=None,provider_verified=False,
                         workspace_read_manifest={})
            r=recorder()
            with self.assertRaisesRegex(ContractError,'transport-model-admission-required'):
                r.begin('failure_analyst','fixture','fixture-2026-10-18',b'{}')
            store.write_encrypted.assert_not_called()
            r=recorder();r.bind_model_admission(runtime,approval,'failure_analyst','fixture','fixture-2026-10-18')
            start=r.begin('failure_analyst','fixture','fixture-2026-10-18',b'{}')
            event=next(e for e in ledger.events if e['event_sha256']==start['admission_event_sha256'])
            self.assertEqual(canonical_hash(runtime),event['payload']['runtime_sha256'])
            self.assertEqual('analyst',event['payload']['role'])
            r.finish(start,b'{}',status='response',complete=True)
            with self.assertRaisesRegex(ContractError,'transport-model-admission-required'):
                r.begin('failure_analyst','fixture','fixture-2026-10-18',b'{}')
            for field,value in [('work_order_sha256','f'*64),('provider','wrong'),('provider_verified',False)]:
                bad=dict(approval);bad[field]=value;r=recorder()
                with self.subTest(field=field),self.assertRaisesRegex(ContractError,'^transport-model-admission-refused$'):
                    r.bind_model_admission(runtime,bad,'failure_analyst','fixture','fixture-2026-10-18')
                self.assertTrue(r.failed)

    def test_accounted_provider_passes_actual_verifier_receipts_before_transport(self):
        from unittest.mock import Mock
        from lightyear_factory.providers import BoundedModelProvider
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,recorder,ledger,calls=self.setup_provider(root)
            recorder.require_model_admission=True
            runtime={'fixture':'runtime'};approval={'fixture':'approval'}
            p.runtime_admission=Mock(return_value=runtime)
            p.model_admission.verify.return_value=approval
            with patch.object(recorder,'bind_model_admission',side_effect=ContractError('fixture-refusal')) as bind:
                with self.assertRaisesRegex(ContractError,'fixture-refusal'):
                    self.call(p)
                bind.assert_called_once_with(runtime,approval,'builder',p.provider.provider_id,p.provider.model)
            self.assertEqual([],calls)
