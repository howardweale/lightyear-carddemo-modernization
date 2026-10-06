import concurrent.futures
import http.client
import json
from pathlib import Path
import tempfile
import time
import unittest
import importlib.util

from tools.ms94_b06_http_broker import Broker, Session, replay, verify_delivery
from tools.ms94_b06_http_transport import arguments, login_arguments, CREDENTIAL_STORE


class Backend:
    def __init__(self): self.calls = []
    def call(self, name, args):
        self.calls.append((name, args))
        return {'status': 'offline-fixture', 'tool': name}


class HttpBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backend = Backend()
        self.session = Session(self.backend, Path(self.temp.name)/'journal',
            dict(campaign='test', journey='J1', trial='1', invocation='1', account_sid_sha256='a'*64),
            deadline=time.monotonic()+5000, maximum_compilations=1)
        self.broker = Broker(self.session).__enter__()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.broker.__exit__())

    def send(self, method='POST', value=None, *, auth=True, **headers):
        base = {'Content-Type': 'application/json'}
        if auth: base['Authorization'] = 'Bearer '+self.session.token
        if self.session.initialized:
            base.update({'Mcp-Session-Id': self.session.id, 'MCP-Protocol-Version': self.session.protocol})
        base.update(headers)
        client = http.client.HTTPConnection(self.broker.host, timeout=5)
        try:
            client.request(method, '/mcp', json.dumps(value) if value is not None else None, base)
            response = client.getresponse(); data = response.read()
            return response.status, json.loads(data) if data else None
        finally: client.close()

    def initialize(self):
        self.assertEqual(self.send(value={'jsonrpc':'2.0', 'id':0, 'method':'initialize',
            'params':{'protocolVersion':'2025-06-18', 'capabilities':{}, 'clientInfo':{'name':'offline','version':'1'}}})[0], 200)

    def call(self, identity=1, name='compile', args=None):
        return {'jsonrpc':'2.0','id':identity,'method':'tools/call',
                'params':{'name':name,'arguments':{'source':'public fixture'} if args is None else args}}

    def test_protocol_closed_tools_and_replay(self):
        self.initialize()
        status, result = self.send(value={'jsonrpc':'2.0','id':1,'method':'tools/list'})
        self.assertEqual(status, 200); self.assertEqual(len(result['result']['tools']), 5)
        self.assertEqual(self.send(value=self.call(2))[0], 200)
        rows = replay(self.session.directory)
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['tool'], 'compile')
        self.assertNotIn(self.session.token, (self.session.directory/'000001.json').read_text())
        self.assertEqual(self.send('GET')[0],405)
        self.assertEqual(self.send('DELETE')[0],204)
        self.assertEqual(self.send(value=self.call(3))[0],401)

    def test_authentication_every_method_and_cross_session(self):
        for method in ('POST','GET','DELETE','OPTIONS','PUT','PATCH','HEAD','TRACE','CONNECT','BOGUS'):
            self.assertEqual(self.send(method, auth=False)[0],401,method)
        self.assertEqual(self.send(value={}, Origin='https://untrusted.example')[0],403)
        self.assertEqual(self.send(value={}, Host='untrusted.example')[0],403)
        self.assertEqual(self.send(value={}, Authorization='Bearer wrong')[0],401)
        self.initialize()
        self.assertEqual(self.send(value=self.call(), **{'Mcp-Session-Id':'another'})[0],409)
        self.assertEqual(self.backend.calls,[])

    def test_concurrent_reconnection_compiles_once(self):
        self.initialize()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: self.send(value=self.call()), range(8)))
        self.assertTrue(all(v == values[0] and v[0] == 200 for v in values))
        self.assertEqual(len(self.backend.calls),1)
        self.assertEqual(self.send(value=self.call(args={'source':'changed'}))[0],400)
        self.assertEqual(self.send(value=self.call(2))[0],400)

    def test_schema_deadline_and_budget_before_backend(self):
        self.initialize()
        for name,args in [('shell',{}),('compile',{'source':'x','path':'tools/x'}),
                          ('compile',{'source':'x'*60001}),('public_api',{'class_name':'../../secret'})]:
            self.assertEqual(self.send(value=self.call(name=name,args=args))[0],400)
        self.assertEqual(self.session.compilations,0)
        self.session.deadline = time.monotonic()+1200
        self.assertEqual(self.send(value=self.call())[0],400)
        self.assertEqual(self.backend.calls,[])

    def test_failure_revokes_and_never_returns_exception_text(self):
        self.initialize()
        def bad(*_): raise RuntimeError('private-detail-secret')
        self.backend.call = bad
        status, response = self.send(value=self.call())
        self.assertEqual(status,400); self.assertNotIn('private-detail',json.dumps(response))
        self.assertEqual(replay(self.session.directory)[0]['status'],'equipment-failure')
        self.assertEqual(self.send(value=self.call())[0],401)

    def test_replay_tamper_and_gap(self):
        self.initialize(); self.send(value=self.call())
        path = self.session.directory/'000001.json'
        path.rename(path.with_name('000002.json'))
        with self.assertRaises(ValueError): replay(self.session.directory)

    def test_file_store_pinned_in_login_and_exec(self):
        self.assertIn(CREDENTIAL_STORE, arguments(49152,r'C:\empty')['argv'])
        for status in (True,False): self.assertIn(CREDENTIAL_STORE,login_arguments(status=status))
        self.assertFalse(arguments(49152,r'C:\empty')['model_calls_authorized'])

    def test_cli_delivery_matches_actual_output_and_bound_head(self):
        self.initialize(); _, response = self.send(value=self.call())
        rows = replay(self.session.directory)
        event = {'type':'item.completed','item':{'id':'tool-1','type':'mcp_tool_call',
            'server':'qualified_journey_public','tool':'compile','arguments':{'source':'public fixture'},
            'result':response['result']}}
        binding = dict(expected_head=rows[-1]['content_sha256'], expected_count=1)
        self.assertTrue(verify_delivery(self.session.directory,[event],**binding)['verified'])
        with self.assertRaises(ValueError): verify_delivery(self.session.directory,[],**binding)
        with self.assertRaises(ValueError): verify_delivery(self.session.directory,[event],expected_head='0'*64,expected_count=1)

    def test_expiry_and_backend_overrun_revoke(self):
        self.initialize()
        ticks = [100.0]
        self.session.clock = lambda: ticks[0]
        self.session.deadline = 5000
        def overrun(*_):
            ticks[0] += 661
            return {'status':'too-late'}
        self.backend.call = overrun
        self.assertEqual(self.send(value=self.call())[0],400)
        self.assertTrue(self.session.revoked)
        self.assertEqual(replay(self.session.directory)[0]['status'],'equipment-failure')

    @unittest.skipUnless(importlib.util.find_spec('mcp') and importlib.util.find_spec('httpx2'), 'MCP v2 SDK required')
    def test_real_sdk_streamable_client_without_model_or_native_backend(self):
        import asyncio
        import httpx2
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        async def exercise():
            async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+self.session.token},trust_env=False) as http:
                async with streamable_http_client('http://'+self.broker.host+'/mcp',http_client=http) as streams:
                    async with ClientSession(*streams) as client:
                        await client.initialize()
                        listing = await client.list_tools()
                        self.assertEqual(len(listing.tools),5)
                        output = await client.call_tool('check_structure',{'source':'public fixture'})
                        self.assertFalse(output.is_error)
        asyncio.run(exercise())
        self.assertTrue(self.session.revoked)
        self.assertEqual(len(self.backend.calls),1)


if __name__ == '__main__': unittest.main()
