"""Bounded controller-side HTTP exchange for the existing N1 replay callable.

No launcher, proxy, browser, authentication or ownership/isolation proof.
Only a reviewed caller may bind the candidate endpoint and original deadline.
No execution entry point. Tests use public synthetic loopback servers in CI.
"""
import ipaddress
import math
import re
import socket
import threading
import time

from lightyear_execution import copau_full_state_contract as contract

REQUEST_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 2 * 1024 * 1024
HEADER_LIMIT = 32768
FIELD = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
MAX_INTERACTIONS = 10000


def remaining(deadline):
    value = deadline - time.monotonic()
    contract.require(value > 0, 'http-original-deadline')
    return value


class _Reader:
    def __init__(self, sock, deadline):
        self.sock, self.deadline = sock, deadline
        self.buffer = bytearray()
        self.total = 0

    def more(self):
        self.sock.settimeout(remaining(self.deadline))
        raw = self.sock.recv(8192)
        contract.require(raw, 'http-truncated-response')
        self.total += len(raw)
        contract.require(self.total <= 4 * RESPONSE_LIMIT, 'http-wire-limit')
        self.buffer.extend(raw)

    def take(self, size):
        while len(self.buffer) < size:
            self.more()
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def until(self, marker, limit):
        while True:
            index = self.buffer.find(marker)
            if index >= 0:
                contract.require(index + len(marker) <= limit, 'http-frame-limit')
                return self.take(index + len(marker))
            contract.require(len(self.buffer) < limit, 'http-frame-limit')
            self.more()


def _response(reader):
    block = reader.until(b'\r\n\r\n', HEADER_LIMIT)
    lines = block[:-4].split(b'\r\n')
    contract.require(re.fullmatch(rb'HTTP/1\.[01] 200(?: [\x20-\x7e]*)?', lines[0]),
                     'http-status-refused')
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(b':')
        contract.require(sep and FIELD.fullmatch(name), 'http-header-refused')
        name = name.lower()
        value = value.strip(b' \t')
        contract.require(name not in headers and
            all(c == 9 or 32 <= c <= 126 for c in value), 'http-header-refused')
        headers[name] = value
    content_type = headers.get(b'content-type', b'').lower()
    contract.require(re.fullmatch(
        rb'application/json(?:;\s*charset=(?:"utf-8"|utf-8))?', content_type),
        'http-content-type-refused')
    contract.require(headers.get(b'content-encoding', b'identity').lower() == b'identity',
                     'http-content-encoding-refused')
    length, transfer = headers.get(b'content-length'), headers.get(b'transfer-encoding')
    contract.require((length is None) != (transfer is None), 'http-framing-refused')
    if length is not None:
        contract.require(re.fullmatch(rb'[0-9]{1,8}', length) and
            0 < int(length) <= RESPONSE_LIMIT, 'http-response-limit')
        return reader.take(int(length))
    contract.require(transfer.lower() == b'chunked', 'http-transfer-refused')
    body = bytearray()
    while True:
        line = reader.until(b'\r\n', 32)[:-2]
        # No extensions or trailers: unsupported framing is an operational fault.
        contract.require(re.fullmatch(rb'[0-9a-fA-F]{1,8}', line), 'http-chunk-refused')
        size = int(line, 16)
        contract.require(len(body) + size <= RESPONSE_LIMIT, 'http-response-limit')
        if size == 0:
            contract.require(reader.take(2) == b'\r\n', 'http-trailer-refused')
            return bytes(body)
        body.extend(reader.take(size))
        contract.require(reader.take(2) == b'\r\n', 'http-chunk-refused')


class Exchange:
    """Callable for replay(exchange=...); the deadline never restarts per row.

    Exactly one connection/POST per call. No DNS, environment proxy, redirect,
    automatic retry or keep-alive reuse. Concurrent/reentrant use is refused.
    A transport fault permanently closes this instance to further exchanges.
    Endpoint/candidate identity is a caller claim, NOT authenticated ownership.
    """
    def __init__(self, host, port, *, candidate_sha256, deadline):
        contract.require(type(host) is str and host == '127.0.0.1' and
                         ipaddress.ip_address(host).is_loopback, 'http-loopback-only')
        contract.require(type(port) is int and 0 < port <= 65535 and port != 8768,
                         'http-port-refused')
        contract.require(type(candidate_sha256) is str and
                         contract.SHA.fullmatch(candidate_sha256), 'http-candidate-binding')
        contract.require(type(deadline) in (int, float) and math.isfinite(deadline)
                         and deadline > time.monotonic(), 'http-original-deadline')
        self._address, self._candidate, self._deadline = (host, port), candidate_sha256, deadline
        self._lock = threading.Lock()
        self._closed, self._count = False, 0

    @property
    def candidate_sha256(self):
        return self._candidate

    def __call__(self, request):
        contract.require(self._lock.acquire(blocking=False), 'http-concurrent-exchange')
        try:
            contract.require(not self._closed, 'http-exchange-closed')
            # Consume the transport call before any send. A failure never retries.
            self._count += 1
            contract.require(self._count <= MAX_INTERACTIONS, 'http-interaction-limit')
            remaining(self._deadline)
            contract.require(type(request) is dict and
                set(request) == {'token', 'aid', 'fields'} and
                (request['token'] is None or type(request['token']) is str) and
                type(request['aid']) is str and type(request['fields']) is dict and
                all(type(k) is str and type(v) is str for k, v in request['fields'].items()),
                'http-request-shape')
            body = contract.encoded(request)
            contract.require(0 < len(body) <= REQUEST_LIMIT, 'http-request-limit')
            host, port = self._address
            head = (f'POST /api/interaction HTTP/1.1\r\nHost: {host}:{port}\r\n'
                    'Content-Type: application/json\r\nAccept: application/json\r\n'
                    'Accept-Encoding: identity\r\nConnection: close\r\n'
                    f'Content-Length: {len(body)}\r\n\r\n').encode('ascii')
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(remaining(self._deadline))
                sock.connect(self._address)
                sock.settimeout(remaining(self._deadline))
                sock.sendall(head + body)
                raw = _response(_Reader(sock, self._deadline))
            remaining(self._deadline)
            try:
                # Explicit UTF-8 only; duplicate keys/nonfinite values are malformed.
                result = contract.decoded(raw.decode('utf-8'))
            except Exception:
                self._closed = True
                # An arrived malformed candidate payload is MISMATCH in replay.
                # Preserve its exact bytes privately; never emit them in a log.
                return {'malformed_http_body_hex': raw.hex()}
            if type(result) is not dict:
                self._closed = True
            return result
        except BaseException:
            self._closed = True
            raise contract.Refused('http-exchange-fault') from None
        finally:
            self._lock.release()
