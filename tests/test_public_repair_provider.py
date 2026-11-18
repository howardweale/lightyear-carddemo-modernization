"""Synthetic CI tests only: no credentials, network, model, or private material."""
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

from lightyear_factory import public_repair_controller as c
from lightyear_factory import public_repair_provider as p


def synthetic_owner(pipe):
    """CI-only spawned worker: no key prompt and no network implementation."""
    try:
        pipe.send_bytes(b'READY')
        pipe.recv_bytes(1048576)
        pipe.send_bytes(b'\x00\xc8{"object":"response.input_tokens","input_tokens":10}')
        pipe.recv_bytes(1048576)
    except (EOFError, OSError):
        pass
    finally:
        pipe.close()


def request(role='planner'):
    source = 'class Main {}'
    feedback = dict(schema='public-repair-feedback/1', candidate_sha256=c.sha(source.encode()),
        public_suite_sha256='1'*64, kind='PUBLIC_DIVERGENCE', divergences=[], diagnostics=[], truncated=False)
    return c.projection(role, {'public.txt': 'public material'}, 'plan', source, 'analysis', [], feedback)


def reply(key='text', text='synthetic'):
    # Retained structure fixture is public and synthetic, never a private response.
    path = Path(__file__).parent/'fixtures/intcalc-preview/provider-envelope.json'
    row = json.loads(path.read_bytes())
    row.update(status='completed', incomplete_details=None, error=None, model=c.MODEL,
               service_tier='flex', temperature=1.0, top_p=0.98, frequency_penalty=0.0, presence_penalty=0.0)
    row['usage'] = dict(input_tokens=10, output_tokens=20, total_tokens=30,
        output_tokens_details={'reasoning_tokens': 5}, input_tokens_details={'cached_tokens': 0,
        'cache_write_tokens': 0, 'cache_write_tokens_details': {'ttl_12h_tokens': 0, 'ttl_30m_tokens': 0}})
    row['output'] = [dict(type='reasoning', content=[]), dict(type='message', status='completed',
        role='assistant', content=[dict(type='output_text', text=json.dumps({key:text}))])]
    return json.dumps(row).encode()


class Evidence:
    def __init__(self):
        self.rows = {}; self.private = {}

    def record(self, name, row):
        if name in self.rows:
            raise ValueError('exclusive')
        c.canonical(row)
        self.rows[name] = row

    def retain_response(self, index, raw):
        self.private[index] = raw
        return c.sha(raw)


class Owner:
    def __init__(self):
        self.calls = []; self.closed = False; self.generation = reply(); self.status = 200

    def post(self, path, body, deadline):
        if self.closed:
            raise AssertionError('send after close')
        self.calls.append((path, body, deadline))
        if path == p.COUNT:
            return 200, b'{"object":"response.input_tokens","input_tokens":10}'
        return self.status, self.generation

    def close(self, deadline):
        self.closed = True


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner(); self.evidence = Evidence()
        self.ports = p.ProviderPorts(self.owner, self.evidence, 2000, clock=lambda: 0)

    def test_envelope_floats_and_nested_details(self):
        row = p.response(reply(), request(), 100000, 'text')
        self.assertEqual(row['artifact'], {'text':'synthetic'})
        self.assertEqual(row['output_tokens'], 20)
        c.canonical(row)

    def test_nonfinite_duplicate_and_overflow(self):
        for raw, expected in [(b'{"a":1,"a":2}', 'provider-duplicate'),
                (b'{"a":NaN}', 'provider-nonfinite'), (b'{"a":Infinity}', 'provider-nonfinite'),
                (b'{"a":-Infinity}', 'provider-nonfinite'), (b'{"a":1e9999}', 'provider-nonfinite')]:
            with self.subTest(raw=raw), self.assertRaisesRegex(p.Refused, expected):
                p.parse(raw)

    def test_artifacts_stay_strict(self):
        with self.assertRaisesRegex(p.Refused, 'provider-nonfinite'):
            p.parse(b'{"text":1.0}', artifact=True)
        with self.assertRaisesRegex(p.Refused, 'provider-json'):
            p.parse(b'\xff')

    def test_wire_projection_and_bound_all_roles(self):
        for role in c.CAPS:
            with self.subTest(role=role):
                r = request(role); count, generation, bound, key = p.requests(r)
                self.assertLessEqual(max(len(count), len(generation)), bound)
                self.assertEqual(bound, len(c.canonical(r))+4096)
                a,b = json.loads(count),json.loads(generation)
                for field in ('input','model','instructions','text'):
                    self.assertEqual(a[field],b[field])
                self.assertEqual(key, 'source' if role in ('builder','repair') else 'text')
                self.assertFalse(b['store']); self.assertFalse(b['stream'])
                self.assertEqual(b['tools'], [])

    def test_many_context_members_refuse_framing_before_send(self):
        r = request(); r['public_context'] = {str(n):'' for n in range(1000)}
        with self.assertRaisesRegex(p.Refused, 'provider-wire-bound'):
            self.ports.count(r, 120)
        self.assertFalse(self.owner.calls)

    def test_unknown_field_model_instruction_refused(self):
        for name, value in [('tools',[]),('model','other'),('instructions','different')]:
            r=request();r[name]=value
            with self.subTest(name=name),self.assertRaisesRegex(p.Refused,'provider-request'):
                p.requests(r)

    def test_count_and_generation_receipts_are_content_free(self):
        r=request(); counted=self.ports.count(r,120);result=self.ports.generate(r,1000)
        self.assertEqual(counted['request_sha256'],c.digest(r))
        self.assertEqual(result['artifact'],{'text':'synthetic'})
        self.assertEqual(len(self.owner.calls),2)
        self.assertNotIn('synthetic',json.dumps(self.evidence.rows))
        self.assertFalse(self.evidence.private)

    def test_duplicate_count_is_terminal(self):
        r=request();self.ports.count(r,120)
        with self.assertRaisesRegex(p.Refused,'provider-state'):
            self.ports.count(r,120)
        self.assertTrue(self.owner.closed);self.assertEqual(len(self.owner.calls),1)

    def test_generate_requires_matching_completed_count(self):
        r=request();self.ports.count(r,120);r['public_context']['public.txt']='altered'
        with self.assertRaisesRegex(p.Refused,'provider-state'):
            self.ports.generate(r,1000)
        self.assertEqual(len(self.owner.calls),1)

    def test_uncertain_count_never_generates(self):
        self.owner.post=Mock(side_effect=p.Refused('provider-uncertain'))
        with self.assertRaisesRegex(p.Refused,'provider-uncertain'):
            self.ports.count(request(),120)
        with self.assertRaisesRegex(p.Refused,'provider-state'):
            self.ports.generate(request(),1000)
        self.assertEqual(self.owner.post.call_count,1)

    def test_failed_generation_retains_raw_privately(self):
        self.ports.count(request(),120);self.owner.generation=b'{"private":"diagnostic sentinel","bad":NaN}'
        with self.assertRaisesRegex(p.Refused,'provider-nonfinite'):
            self.ports.generate(request(),1000)
        self.assertEqual(self.evidence.private[0],self.owner.generation)
        record=self.evidence.rows['provider-0-failed']
        self.assertEqual(record['refusal_code'],'provider-nonfinite')
        self.assertEqual(record['private_response'],'RETAINED_PRIVATE')
        self.assertNotIn('diagnostic sentinel',json.dumps(self.evidence.rows))

    def test_http_failure_retains_generation_and_no_retry(self):
        self.ports.count(request(),120);self.owner.status=429
        with self.assertRaisesRegex(p.Refused,'provider-http'):
            self.ports.generate(request(),1000)
        self.assertEqual(len(self.owner.calls),2);self.assertIn(0,self.evidence.private)

    def test_retention_failure_preserves_original(self):
        self.ports.count(request(),120);self.owner.generation=b'bad'
        self.evidence.retain_response=Mock(side_effect=OSError('private path'))
        with self.assertRaisesRegex(p.Refused,'provider-json'):
            self.ports.generate(request(),1000)
        self.assertEqual(self.evidence.rows['provider-0-failed']['private_response'],'RETENTION_FAILED')

    def test_usage_rejects_bool_wrong_total_and_reasoning(self):
        for field,value in [('input_tokens',True),('total_tokens',31),('output_tokens',32001),
                            ('output_tokens_details',{'reasoning_tokens':21})]:
            row=json.loads(reply());row['usage'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(p.Refused,'provider-usage'):
                p.response(json.dumps(row).encode(),request(),100000,'text')

    def test_non_artifact_or_incomplete_outputs(self):
        for updates in ({'status':'incomplete'},{'service_tier':'default'},
                        {'output':[{'type':'function_call'}]}, {'output':[]}):
            row=json.loads(reply());row.update(updates)
            with self.subTest(updates=updates),self.assertRaises(p.Refused):
                p.response(json.dumps(row).encode(),request(),100000,'text')

    def test_c0_and_utf8_byte_caps(self):
        for text in ('bad\x00','x'*8193,'é'*4097):
            with self.subTest(size=len(text)),self.assertRaises(c.Refused):
                p.response(reply(text=text),request(),100000,'text')

    def test_close_prevents_all_future_sends(self):
        self.ports.close_models();self.ports.close_models()
        self.assertTrue(self.evidence.rows['provider-closed']['key_process_reaped'])
        with self.assertRaisesRegex(p.Refused,'provider-state'):
            self.ports.count(request(),120)
        self.assertFalse(self.owner.calls)

    def test_cleanup_failure_cannot_be_retried_into_success(self):
        self.owner.close=Mock(side_effect=p.Refused('provider-cleanup'))
        with self.assertRaisesRegex(p.Refused,'provider-cleanup'):
            self.ports.close_models()
        with self.assertRaisesRegex(p.Refused,'provider-state'):
            self.ports.close_models()
        self.assertNotIn('provider-closed',self.evidence.rows)

    def test_deadline_and_wrong_sequence(self):
        for r,end in ((request(),0),(request('builder'),120)):
            obj=p.ProviderPorts(Owner(),Evidence(),2000,clock=lambda:0)
            with self.subTest(end=end),self.assertRaises(p.Refused):
                obj.count(r,end)

    def test_no_implicit_http_retry_or_redirect(self):
        connection=Mock();connection.getresponse.return_value.status=302
        connection.getresponse.return_value.read.return_value=b'public'
        with patch.object(p.http.client,'HTTPSConnection',return_value=connection) as factory:
            self.assertEqual(p.https_once(p.COUNT,b'{}','synthetic-test-token',10),(302,b'public'))
        factory.assert_called_once_with('api.openai.com',timeout=10)
        self.assertEqual(connection.request.call_count,1);connection.close.assert_called_once()

    def test_key_owner_startup_is_key_free_and_close_reaps(self):
        ctx=Mock();parent=Mock();child=Mock();worker=Mock()
        ctx.Pipe.return_value=(parent,child);ctx.Process.return_value=worker
        worker.is_alive.side_effect=[True,False]
        parent.recv_bytes.return_value=b'READY';parent.poll.return_value=True
        owner=p.KeyOwner(30,clock=lambda:0,context=ctx)
        self.assertEqual(ctx.Process.call_args.kwargs['args'],(child,))
        owner.close(5);worker.kill.assert_called_once();worker.join.assert_called_once_with(timeout=5)
        self.assertTrue(owner.closed)

    def test_owner_timeout_is_closed_not_reused(self):
        ctx=Mock();parent=Mock();child=Mock();worker=Mock()
        ctx.Pipe.return_value=(parent,child);ctx.Process.return_value=worker
        parent.poll.return_value=False;worker.is_alive.return_value=False
        with self.assertRaisesRegex(p.Refused,'provider-deadline'):
            p.KeyOwner(30,clock=lambda:0,context=ctx)
        worker.join.assert_called_once();parent.close.assert_called()

    def test_private_sink_uses_p3_exclusive_operation(self):
        sink=object.__new__(p.ProviderEvidence)
        sink._operation=lambda f:f();sink._write=Mock(return_value=c.sha(b'raw'))
        self.assertEqual(sink.retain_response(0,b'raw'),c.sha(b'raw'))
        sink._write.assert_called_once_with('provider-0-response.private',b'raw')

    def test_real_spawned_synthetic_owner_is_reaped(self):
        owner=p.KeyOwner(time.monotonic()+30,target=synthetic_owner)
        try:
            status,raw=owner.post(p.COUNT,b'{}',time.monotonic()+20)
            self.assertEqual(status,200)
            self.assertEqual(p.parse(raw)['input_tokens'],10)
        finally:
            owner.close(time.monotonic()+5)
        self.assertTrue(owner.closed)

    def test_all_twelve_slots_and_early_close(self):
        for index,role in enumerate(p.SEQUENCE):
            r=request(role);key='source' if role in ('builder','repair') else 'text'
            self.owner.generation=reply(key=key)
            self.ports.count(r,120);self.ports.generate(r,1000)
            self.assertEqual(self.ports.index,index+1)
        self.ports.close_models();self.assertEqual(len(self.owner.calls),24)

    def test_controller_four_roles_repair_then_close_before_hidden(self):
        evidence=self.evidence;owner=self.owner;provider=self.ports
        original_post=owner.post
        def post(path,body,deadline):
            if path==p.GENERATE:
                key=json.loads(body)['text']['format']['schema']['required'][0]
                owner.generation=reply(key=key)
            return original_post(path,body,deadline)
        owner.post=post
        class Ports:
            count=provider.count
            generate=provider.generate
            close_models=provider.close_models
            record=staticmethod(evidence.record)
            def admit(self,raw,deadline):
                return dict(binding_sha256=c.sha(raw),receipt_sha256='2'*64)
            def retain_artifact(self,slot,key,text):
                return c.sha(text.encode())
            def build(self,source,round_no,deadline):
                self.round=round_no
                return dict(status='BUILT',artifact_sha256=c.sha(source.encode()),
                    build_receipt_sha256='3'*64,cleanup=True,feedback=None)
            def evaluate_public(self,built,suite,deadline):
                feedback=dict(schema='public-repair-feedback/1',candidate_sha256=built['artifact_sha256'],
                    public_suite_sha256=suite,kind='PUBLIC_DIVERGENCE',divergences=[],diagnostics=[],truncated=False)
                return dict(suite_sha256=suite,artifact_sha256=built['artifact_sha256'],
                    build_receipt_sha256=built['build_receipt_sha256'],match=int(self.round>0),
                    different=int(self.round==0),total=1,complete=True,cleanup=True,
                    receipt_sha256='4'*64,feedback=feedback)
            def evaluate_hidden(self,selected,commitment,deadline):
                if not owner.closed:
                    raise AssertionError('key owner alive at hidden boundary')
                return dict(status='PASS',receipt_sha256='5'*64,cleanup=True)
        context={'public.txt':'public material'}
        binding=dict(schema='public-repair-binding/1',graph_mode='off',max_repairs=5,
            window_seconds=c.WINDOW,cap_microdollars=c.CEILING,model=c.MODEL,
            service_tier='flex',output_cap=32000,retries=0,authority_sha256='1'*64,
            implementation_sha256='1'*64,public_context_sha256=c.digest(context),
            public_suite_sha256='1'*64,heldout_commitment_sha256='1'*64,
            runtime_profile_sha256='1'*64,role_instructions_sha256=c.ROLE_HASH,
            public_case_count=1,feedback_contract_sha256=c.FEEDBACK_HASH)
        result=c.Controller(Ports(),binding,context,clock=lambda:0).run()
        self.assertEqual(result['status'],'CANDIDATE_PASS')
        self.assertEqual(provider.index,4);self.assertEqual(len(owner.calls),8)


if __name__ == '__main__':
    unittest.main()
