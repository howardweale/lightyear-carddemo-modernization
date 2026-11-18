"""Graph-off provider ports; no retired route, CLI, admission or hidden access.

The launcher authenticates authority before starting the key-owner process.
Only that process prompts for and holds the key. Tests use a synthetic owner.
"""
import getpass
import http.client
import json
import math
import multiprocessing
import os
import threading
import time

from lightyear_factory import public_repair_controller as c
from lightyear_factory.public_repair_durable import DurablePorts

MAX_RESPONSE = 524288
COUNT = '/v1/responses/input_tokens'
GENERATE = '/v1/responses'
SEQUENCE = ('planner', 'builder') + ('analysis', 'repair') * 5
CODES = frozenset(('provider-state', 'provider-request', 'provider-wire-bound',
    'provider-deadline', 'provider-owner', 'provider-cleanup', 'provider-uncertain',
    'provider-http', 'provider-size', 'provider-json', 'provider-duplicate',
    'provider-nonfinite', 'provider-count', 'provider-response', 'provider-usage',
    'provider-artifact', 'provider-retention', 'provider-unexpected'))


class Refused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Refused(code)


def code(error):
    return str(error) if isinstance(error, Refused) and str(error) in CODES else 'provider-unexpected'


def parse(raw, *, artifact=False):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'provider-duplicate')
            result[key] = value
        return result

    def number(text):
        value = float(text)
        require(not artifact and math.isfinite(value), 'provider-nonfinite')
        return value

    def reject(_):
        raise Refused('provider-nonfinite')

    require(type(raw) is bytes and len(raw) <= MAX_RESPONSE, 'provider-size')
    try:
        return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                          parse_float=number, parse_constant=reject)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError):
        raise Refused('provider-json') from None


def integer(value, cap):
    require(type(value) is int and 0 <= value <= cap, 'provider-usage')
    return value


def requests(request):
    """No JSON-in-JSON payload: context/plan/source are separate text messages.

    Actual count and generation encodings must each fit the controller's existing
    canonical projection + 4096 bound. maxLength cannot enforce a UTF-8 byte cap.
    """
    require(type(request) is dict and request.get('role') in c.CAPS, 'provider-request')
    role = request['role']
    keys = {'schema', 'role', 'model', 'service_tier', 'max_output_tokens',
            'truncation', 'instructions', 'public_context'}
    if role != 'planner':
        keys.add('plan')
    if role in ('analysis', 'repair'):
        keys.update(('source', 'score_history', 'feedback'))
    if role == 'repair':
        keys.add('analysis')
    require(set(request) == keys and request['schema'] == 'public-repair-request/1'
            and request['model'] == c.MODEL and request['service_tier'] == 'flex'
            and type(request['max_output_tokens']) is int and request['max_output_tokens'] == 32000
            and request['truncation'] == 'disabled' and request['instructions'] == c.INSTRUCTIONS[role],
            'provider-request')
    raw = c.canonical(request)
    bound = len(raw) + 4096
    require(bound <= c.CAPS[role], 'provider-wire-bound')
    context = request['public_context']
    require(type(context) is dict and bool(context)
            and all(type(k) is str and type(v) is str for k, v in context.items()), 'provider-request')
    parts = []
    for name, text in sorted(context.items()):
        parts.extend(({'type': 'input_text', 'text': 'Public context member: ' + name},
                      {'type': 'input_text', 'text': text}))
    for name in ('plan', 'source', 'analysis', 'score_history', 'feedback'):
        if name in request:
            value = request[name]
            if name in ('plan', 'source', 'analysis'):
                c.text_ok(value, 65536 if name == 'source' else 8192,
                          73728 if name == 'source' else 16384)
            else:
                value = c.canonical(value).decode('ascii')
            parts.extend(({'type': 'input_text', 'text': name},
                          {'type': 'input_text', 'text': value}))
    key = 'source' if role in ('builder', 'repair') else 'text'
    common = dict(model=c.MODEL, instructions=request['instructions'],
        input=[{'role': 'user', 'content': parts}],
        text={'format': {'type': 'json_schema', 'name': 'public_repair_artifact',
              'strict': True, 'schema': {'type': 'object', 'properties': {key: {'type': 'string'}},
              'required': [key], 'additionalProperties': False}}})
    generation = dict(common, service_tier='flex', store=False, max_output_tokens=32000,
        reasoning={'effort': 'medium'}, tools=[], background=False, stream=False,
        previous_response_id=None, truncation='disabled')
    counted, generated = c.canonical(common), c.canonical(generation)
    require(max(len(counted), len(generated)) <= bound, 'provider-wire-bound')
    return counted, generated, bound, key


def response(raw, request, bound, key):
    row = parse(raw)
    require(type(row) is dict and row.get('status') == 'completed'
            and row.get('incomplete_details') is None and row.get('error') is None
            and row.get('model') == c.MODEL and row.get('service_tier') == 'flex',
            'provider-response')
    usage = row.get('usage')
    require(type(usage) is dict, 'provider-usage')
    inp = integer(usage.get('input_tokens'), bound)
    out = integer(usage.get('output_tokens'), 32000)
    require(integer(usage.get('total_tokens'), bound + 32000) == inp + out, 'provider-usage')
    details = usage.get('output_tokens_details')
    require(type(details) is dict, 'provider-usage')
    integer(details.get('reasoning_tokens'), out)
    require(type(row.get('output')) is list, 'provider-response')
    texts = []
    for item in row['output']:
        require(type(item) is dict, 'provider-response')
        if item.get('type') == 'reasoning':
            require(item.get('status', 'completed') == 'completed', 'provider-response')
            continue
        require(item.get('type') == 'message' and item.get('status') == 'completed'
                and item.get('role') == 'assistant' and type(item.get('content')) is list,
                'provider-response')
        for part in item['content']:
            require(type(part) is dict and part.get('type') == 'output_text'
                    and type(part.get('text')) is str, 'provider-response')
            texts.append(part['text'])
    require(len(texts) == 1, 'provider-artifact')
    artifact = parse(texts[0].encode('utf-8'), artifact=True)
    require(type(artifact) is dict and set(artifact) == {key}, 'provider-artifact')
    c.text_ok(artifact[key], 65536 if key == 'source' else 8192,
              73728 if key == 'source' else 16384)
    return dict(artifact=artifact, input_tokens=inp, output_tokens=out, model=c.MODEL,
                service_tier='flex', request_sha256=c.digest(request), receipt_sha256=c.sha(raw))


def https_once(path, body, key, timeout):
    require(path in (COUNT, GENERATE), 'provider-request')
    connection = http.client.HTTPSConnection('api.openai.com', timeout=timeout)
    try:
        connection.request('POST', path, body=body, headers={'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json', 'Accept': 'application/json', 'Connection': 'close'})
        reply = connection.getresponse()
        raw = reply.read(MAX_RESPONSE + 1)
        require(len(raw) <= MAX_RESPONSE, 'provider-size')
        return reply.status, raw
    finally:
        connection.close()


def key_owner(pipe):
    """Howard-only entry: no key argument, environment, file, log or parent reply."""
    try:
        require(os.name == 'posix', 'provider-owner')
        os.environ.clear()
        with open('/dev/tty', 'r+', encoding='utf-8') as terminal:
            require(terminal.isatty(), 'provider-owner')
            # getpass must not fall back to echoed input if a terminal is unavailable.
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                key = getpass.getpass('API key (hidden): ', stream=terminal)
        require(type(key) is str and 0 < len(key) <= 512
                and not any(c.isspace() for c in key), 'provider-owner')
        pipe.send_bytes(b'READY')
        while True:
            message = parse(pipe.recv_bytes(1048576), artifact=True)
            require(type(message) is dict and set(message) == {'path', 'body', 'timeout_ms'}, 'provider-request')
            timeout = integer(message['timeout_ms'], 900000) / 1000
            require(timeout > 0 and type(message['body']) is str, 'provider-deadline')
            status, raw = https_once(message['path'], message['body'].encode('ascii'), key, timeout)
            pipe.send_bytes(status.to_bytes(2, 'big') + raw)
    except BaseException:
        try:
            pipe.send_bytes(b'FAULT')
        except BaseException:
            pass
    finally:
        pipe.close()


class KeyOwner:
    """Spawned key process, killed/reaped on close or any uncertain exchange.

    No child-of-child is created. IPC and HTTP are bounded by the same watchdog.
    OS process termination is the boundary; Python-memory erasure is not claimed.
    Caller must authenticate admission before constructing this capability.
    """
    def __init__(self, deadline, *, clock=time.monotonic, context=None, target=key_owner):
        self.clock, self.closed = clock, False
        self.pid = os.getpid()
        ctx = context or multiprocessing.get_context('spawn')
        self.pipe, child = ctx.Pipe(duplex=True)
        self.worker = ctx.Process(target=target, args=(child,), daemon=True)
        self.started = False
        try:
            self.worker.start()
            self.started = True
            child.close()
            require(self.exchange(None, deadline) == b'READY', 'provider-owner')
        except BaseException:
            child.close()
            self.close(deadline)
            raise

    def exchange(self, payload, deadline):
        require(not self.closed and os.getpid() == self.pid, 'provider-state')
        require(deadline - self.clock() > 5, 'provider-deadline')
        def abort():
            try:
                if self.worker.is_alive():
                    self.worker.kill()
            except (OSError, ValueError):
                pass  # a concurrent close may already have reaped the process
        timer = threading.Timer(deadline - self.clock() - 5, abort)
        timer.daemon = True
        timer.start()
        try:
            if payload is not None:
                self.pipe.send_bytes(payload)
            require(self.pipe.poll(max(0, deadline - self.clock() - 5)), 'provider-deadline')
            raw = self.pipe.recv_bytes(MAX_RESPONSE + 2)
            require(self.clock() < deadline - 5 and raw != b'FAULT', 'provider-uncertain')
            return raw
        except BaseException:
            self.close(deadline)
            raise
        finally:
            timer.cancel()
            timer.join()

    def post(self, path, body, deadline):
        payload = c.canonical(dict(path=path, body=body.decode('ascii'),
                                   timeout_ms=max(0, int((deadline-self.clock()-5)*1000))))
        raw = self.exchange(payload, deadline)
        require(len(raw) >= 2, 'provider-uncertain')
        return int.from_bytes(raw[:2], 'big'), raw[2:]

    def close(self, deadline):
        if self.closed:
            return
        self.closed = True
        self.pipe.close()
        if self.started:
            if self.worker.is_alive():
                self.worker.kill()
            self.worker.join(timeout=max(0, deadline-self.clock()))
            require(not self.worker.is_alive(), 'provider-cleanup')
            self.worker.close()
        require(self.clock() <= deadline, 'provider-deadline')


class ProviderEvidence(DurablePorts):
    """Adds only bounded private raw-response files to the P3 exclusive sink."""
    def retain_response(self, index, raw):
        def write():
            require(type(index) is int and 0 <= index < 12 and type(raw) is bytes
                    and len(raw) <= MAX_RESPONSE, 'provider-retention')
            return self._write('provider-' + str(index) + '-response.private', raw)
        return self._operation(write)


class ProviderPorts:
    """One count then one generation per slot. Failure consumes the capability.

    P3 supplies record()/retain_artifact(); this object never authenticates spend.
    Production launcher must bind/authorize the fixed graph-off policy first.
    """
    def __init__(self, owner, evidence, deadline, *, clock=time.monotonic):
        self.owner, self.evidence = owner, evidence
        self.end, self.clock = deadline, clock
        self.index, self.pending, self.closed, self.failed = 0, None, False, False
        self.pid = os.getpid()
        self.generation_raw = None

    def _before(self, deadline):
        require(not self.closed and not self.failed and os.getpid() == self.pid, 'provider-state')
        require(self.clock() < deadline <= self.end, 'provider-deadline')

    def _fault(self, error, raw=None):
        self.failed = True
        retained = 'NOT_AVAILABLE'
        if raw is not None:
            try:
                require(self.evidence.retain_response(self.index, raw) == c.sha(raw), 'provider-retention')
                retained = 'RETAINED_PRIVATE'
            except BaseException:
                retained = 'RETENTION_FAILED'
        try:
            self.evidence.record('provider-' + str(self.index) + '-failed',
                dict(failure_schema='public-provider-failure/1', refusal_code=code(error),
                     private_response=retained, retries=0, full_hold_retained=True))
        except BaseException:
            pass
        try:
            self.close_models()
        except BaseException:
            pass

    def _post(self, path, body, deadline, phase):
        self._before(deadline)
        name = 'provider-' + str(self.index) + '-' + phase
        self.evidence.record(name + '-send', dict(wire_sha256=c.sha(body), bytes=len(body), retries=0))
        status, raw = self.owner.post(path, body, deadline)
        require(type(status) is int and type(raw) is bytes and len(raw) <= MAX_RESPONSE, 'provider-size')
        if phase == 'generation':
            self.generation_raw = raw
        self.evidence.record(name + '-response', dict(http_status=status, response_sha256=c.sha(raw)))
        self._before(deadline)
        require(status == 200, 'provider-http')
        return raw

    def count(self, request, deadline):
        try:
            self._before(deadline)
            require(self.pending is None and self.index < len(SEQUENCE)
                    and request.get('role') == SEQUENCE[self.index], 'provider-state')
            counted, generated, bound, key = requests(request)
            identity = c.digest(request)
            self.pending = (identity, generated, bound, key)  # consumed before send
            raw = self._post(COUNT, counted, deadline, 'count')
            row = parse(raw)
            require(type(row) is dict and row.get('object') == 'response.input_tokens', 'provider-count')
            count = integer(row.get('input_tokens'), bound)
            return dict(input_tokens=count, request_sha256=identity, receipt_sha256=c.sha(raw))
        except BaseException as error:
            self._fault(error)
            raise

    def generate(self, request, deadline):
        raw = None
        try:
            self._before(deadline)
            require(self.pending is not None and c.digest(request) == self.pending[0], 'provider-state')
            _, generated, bound, key = self.pending
            raw = self._post(GENERATE, generated, deadline, 'generation')
            result = response(raw, request, bound, key)
            self._before(deadline)
            self.pending = None
            self.index += 1
            self.generation_raw = None
            return result
        except BaseException as error:
            self._fault(error, self.generation_raw)
            self.generation_raw = None
            raise

    def close_models(self):
        if self.closed:
            require(not self.failed, 'provider-state')
            return
        self.closed = True  # no future send even if cleanup fails
        try:
            self.owner.close(min(self.end, self.clock()+5))
            self.evidence.record('provider-closed', dict(schema='public-provider-closed/1',
                key_process_reaped=True, further_sends_possible=False, memory_erasure_claimed=False))
        except BaseException:
            self.failed = True
            raise
