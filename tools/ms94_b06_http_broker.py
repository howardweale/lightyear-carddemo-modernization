"""Host-owned JSON Streamable HTTP MCP transport for the closed B06 boundary.

No model launcher or default backend. The admitted host supplies its backend;
tests use offline fixtures. This does not admit a native or measurement run.
"""
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lightyear_calibration.contracts import canonical, seal, verify
from tools.ms94_b06_builder_boundary import ARGUMENTS, dispatch

PROTOCOLS = ('2025-03-26', '2025-06-18', '2025-11-25')
MAX_BODY = 262144


def tool_list():
    descriptions = {
        'public_contract': 'Read the public scenario contract.',
        'public_api': 'Read public application API documentation.',
        'deterministic_support': 'Read the deterministic public support source.',
        'check_structure': 'Check candidate source structure.',
        'compile': 'Compile candidate source within the admitted budget.',
    }
    return [{'name': name, 'description': descriptions[name], 'inputSchema': {
        'type': 'object', 'properties': {key: {'type': 'string'} for key in sorted(keys)},
        'required': sorted(keys - ({'method'} if name == 'public_api' else set())),
        'additionalProperties': False}} for name, keys in ARGUMENTS.items()]


def replay(directory):
    """Check the local transport journal; no backend dispatch or network."""
    rows = []
    previous = None
    binding = None
    compilations = 0
    for ordinal, path in enumerate(sorted(Path(directory).glob('*.json')), 1):
        row = json.loads(path.read_bytes()); verify(row)
        if path.name != f'{ordinal:06d}.json' or row['ordinal'] != ordinal or row['previous_sha256'] != previous:
            raise ValueError('B06 HTTP journal chain differs')
        if row['tool'] not in ARGUMENTS or row['status'] not in ('completed', 'equipment-failure'):
            raise ValueError('B06 HTTP journal event differs')
        if row['request_sha256'] != hashlib.sha256(canonical(row['request'])).hexdigest():
            raise ValueError('B06 HTTP request binding differs')
        params = row['request']['params']
        if row['request']['method'] != 'tools/call' or params['name'] != row['tool']:
            raise ValueError('B06 HTTP tool binding differs')
        class Validate:
            def call(_, name, args): return args
        dispatch(Validate(), row['tool'], params['arguments'])
        current = (row['binding'], row['session_id'])
        if binding is not None and current != binding:
            raise ValueError('B06 HTTP invocation changed')
        binding = current
        compilations += row['tool'] == 'compile'
        if row['compilations_used'] != compilations:
            raise ValueError('B06 HTTP compilation accounting differs')
        if row['status'] == 'equipment-failure' and row['output'] != {}:
            raise ValueError('B06 HTTP failure disclosed output')
        if rows and rows[-1]['status'] == 'equipment-failure':
            raise ValueError('B06 HTTP dispatch after equipment failure')
        previous = row['content_sha256']; rows.append(row)
    return rows


def verify_delivery(directory, events, *, expected_head, expected_count):
    """Caller must bind the terminal journal head/count in a signed host receipt."""
    from tools.ms94_tool_policy_v5 import verify_events
    rows = replay(directory)
    head = rows[-1]['content_sha256'] if rows else None
    if head != expected_head or len(rows) != expected_count or any(r['status'] != 'completed' for r in rows):
        raise ValueError('B06 HTTP terminal journal binding differs')
    records = []
    for row in rows:
        args = dict(row['request']['params']['arguments'])
        if row['tool'] == 'public_api': args.setdefault('method', '')
        records.append({'invocation': {'tool': row['tool'], 'arguments': args},
                        'result': {'output': row['output']}})
    return verify_events(events, 'builder', records)


class Session:
    def __init__(self, backend, directory, binding, *, deadline, maximum_compilations,
                 tool_seconds=660, reserve_seconds=600, maximum_requests=256, clock=time.monotonic):
        if not all(math.isfinite(x) for x in (deadline, tool_seconds, reserve_seconds)) or tool_seconds <= 0 or reserve_seconds < 0:
            raise ValueError('Invalid transport deadline')
        if type(maximum_compilations) is not int or not 0 <= maximum_compilations <= 3:
            raise ValueError('Invalid compilation limit')
        if type(maximum_requests) is not int or not 1 <= maximum_requests <= 256:
            raise ValueError('Invalid request limit')
        if set(binding) != {'campaign', 'journey', 'trial', 'invocation', 'account_sid_sha256'} or not all(isinstance(v, str) and v for v in binding.values()):
            raise ValueError('Incomplete invocation binding')
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=False)
        self.backend, self.binding, self.clock = backend, dict(binding), clock
        self.deadline, self.tool_seconds, self.reserve = deadline, tool_seconds, reserve_seconds
        self.maximum, self.compilations = maximum_compilations, 0
        self.maximum_requests, self.cache = maximum_requests, {}
        self.token, self.id = secrets.token_urlsafe(32), secrets.token_hex(24)
        self.lock = threading.Lock()
        self.revoked = False; self.initialized = False; self.protocol = None
        self.previous = None; self.ordinal = 0

    def live(self):
        return not self.revoked and self.clock() < self.deadline

    def revoke(self):
        self.revoked = True

    def authenticate(self, token):
        return self.live() and isinstance(token, str) and hmac.compare_digest(token.encode(), ('Bearer ' + self.token).encode())

    def record(self, request, tool, output, status):
        self.ordinal += 1
        row = seal({'artifact_type': 'ms94-b06-http-call/1', 'ordinal': self.ordinal,
                    'previous_sha256': self.previous, 'session_id': self.id, 'binding': self.binding,
                    'request': request, 'request_sha256': hashlib.sha256(canonical(request)).hexdigest(),
                    'tool': tool, 'output': output, 'status': status,
                    'compilations_used': self.compilations})
        with (self.directory / f'{self.ordinal:06d}.json').open('xb') as stream:
            stream.write(canonical(row)); stream.flush(); os.fsync(stream.fileno())
        self.previous = row['content_sha256']

    def rpc(self, request):
        with self.lock:
            if not self.live(): raise ValueError('Session unavailable')
            if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or set(request) - {'jsonrpc', 'method', 'params', 'id'}:
                raise ValueError('Invalid request')
            method, params = request.get('method'), request.get('params', {})
            if not isinstance(params, dict): raise ValueError('Invalid parameters')
            params = dict(params)
            metadata = params.pop('_meta', {})
            if not isinstance(metadata, dict) or set(metadata) - {'progressToken'}:
                raise ValueError('Unsupported request metadata')
            if metadata and type(metadata['progressToken']) not in (str, int):
                raise ValueError('Invalid progress token')
            if method == 'notifications/initialized' and 'id' not in request and self.initialized:
                return None
            identity = request.get('id')
            if type(identity) not in (str, int) or isinstance(identity, str) and len(identity) > 128:
                raise ValueError('Invalid request identity')
            key = (type(identity).__name__, identity)
            fingerprint = hashlib.sha256(canonical(request)).hexdigest()
            if key in self.cache:
                prior, result = self.cache[key]
                if prior != fingerprint: raise ValueError('Request identity reused')
                return result
            if len(self.cache) >= self.maximum_requests: raise ValueError('Request budget exhausted')
            if method == 'initialize':
                version = params.get('protocolVersion')
                if self.initialized or not isinstance(version, str) or not version:
                    raise ValueError('Initialization differs')
                self.protocol = version if version in PROTOCOLS else PROTOCOLS[-1]
                self.initialized = True
                result = {'protocolVersion': self.protocol, 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'B06 closed host broker', 'version': '1.0'}}
            elif not self.initialized:
                raise ValueError('Initialize required')
            elif method == 'ping': result = {}
            elif method == 'tools/list':
                if params: raise ValueError('No tool-list parameters')
                result = {'tools': tool_list()}
            elif method == 'tools/call':
                if set(params) != {'name', 'arguments'} or params['name'] not in ARGUMENTS:
                    raise ValueError('Undeclared capability')
                if self.clock() + self.tool_seconds + self.reserve >= self.deadline:
                    raise ValueError('Tool cannot fit deadline')
                tool = params['name']
                # Validate arguments BEFORE accounting or invoking the real backend.
                class Validate:
                    def call(_, name, args): return args
                args = dispatch(Validate(), tool, params['arguments'])
                if tool == 'compile':
                    if self.compilations >= self.maximum: raise ValueError('Compilation budget exhausted')
                    self.compilations += 1
                before = self.clock()
                try:
                    output = dispatch(self.backend, tool, args)
                    if self.clock() - before > self.tool_seconds or not self.live():
                        raise TimeoutError('Backend exceeded deadline')
                    if not isinstance(output, dict) or len(canonical(output)) > MAX_BODY:
                        raise ValueError('Invalid backend result')
                    self.record(request, tool, output, 'completed')
                except Exception:
                    self.revoke()
                    self.record(request, tool, {}, 'equipment-failure')
                    raise ValueError('Backend unavailable') from None
                result = {'content': [{'type': 'text', 'text': canonical(output).decode()}],
                          'structuredContent': output, 'isError': False}
            else: raise ValueError('Unsupported method')
            response = {'jsonrpc': '2.0', 'id': identity, 'result': result}
            self.cache[key] = (fingerprint, response)
            return response


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


class Broker:
    """JSON responses only; GET/SSE is deliberately unsupported (authenticated 405).

    A native backend must itself be supervised to its admitted deadline. This
    transport detects overruns and revokes; it cannot kill arbitrary Python calls.
    """
    def __init__(self, session):
        self.session = session
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def setup(self):
                self.request.settimeout(5)
                super().setup()

            def __getattr__(self, name):
                if name.startswith('do_'): return self.handle_request
                raise AttributeError(name)

            def log_message(self, *args): pass

            def reply(self, code, value=None):
                raw = canonical(value) if value is not None else b''
                self.send_response(code)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Connection', 'close')
                if raw: self.send_header('Content-Type', 'application/json')
                if session.initialized and code < 400: self.send_header('Mcp-Session-Id', session.id)
                self.end_headers()
                if raw: self.wfile.write(raw)
                self.close_connection = True

            def handle_request(self):
                self.connection.settimeout(5)
                if (self.client_address[0] != '127.0.0.1' or
                    len(self.headers.get_all('Authorization', [])) != 1 or
                    not session.authenticate(self.headers.get('Authorization'))):
                    return self.reply(401)
                if (self.path != '/mcp' or self.headers.get_all('Host', []) != [owner.host] or
                    self.headers.get('Origin') is not None): return self.reply(403)
                if session.initialized and (self.headers.get_all('Mcp-Session-Id', []) != [session.id] or
                    self.headers.get_all('MCP-Protocol-Version', []) != [session.protocol]): return self.reply(409)
                if self.command == 'DELETE':
                    session.revoke(); return self.reply(204)
                if self.command != 'POST': return self.reply(405)
                if (self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or
                    self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1):
                    return self.reply(400)
                try:
                    size = int(self.headers['Content-Length'])
                    if not 0 < size <= MAX_BODY: return self.reply(413)
                    raw = self.rfile.read(size)
                    if len(raw) != size: return self.reply(400)
                    request = json.loads(raw, object_pairs_hook=_object,
                                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    response = session.rpc(request)
                except (ValueError, TypeError, KeyError, TimeoutError):
                    return self.reply(400, {'error': 'request-rejected'})
                return self.reply(202 if response is None else 200, response)

            do_POST = do_GET = do_DELETE = do_OPTIONS = do_PUT = do_PATCH = do_HEAD = handle_request

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.host = f'127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start(); return self

    def __exit__(self, *_):
        self.session.revoke(); self.server.shutdown(); self.server.server_close(); self.thread.join(5)
        if self.thread.is_alive(): raise RuntimeError('Broker did not stop')
