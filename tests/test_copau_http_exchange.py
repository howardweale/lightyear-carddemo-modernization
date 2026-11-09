"""Public synthetic socket peers only; execution belongs to CI."""
import json
import os
import socket
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lightyear_execution import copau_http_exchange as http
from lightyear_execution import copau_full_state_contract as contract
from tools import copau_candidate_replay as replay
from tests.test_copau_full_state_contract import MemoryStore


REQUEST = {'token': None, 'aid': 'INITIAL', 'fields': {'USER': 'public-fixture'}}
RESPONSE = {'screen': {'text': 'public-fixture'}, 'ended': True, 'token': None}


def framed(raw, *, status=b'200 OK', headers=b''):
    return (b'HTTP/1.1 ' + status + b'\r\nContent-Type: application/json\r\n' +
            b'Content-Length: ' + str(len(raw)).encode() + b'\r\n' + headers +
            b'\r\n' + raw)


class Peer:
    def __init__(self, response, *, delay=0, drip=False):
        self.response, self.delay, self.drip = response, delay, drip
        self.received = None
        self.accepted = 0
        self.error = None
        self.done = threading.Event()
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        if self.port == 8768:
            self.sock.close()
            raise AssertionError('forbidden port allocation')
        self.sock.settimeout(3)
        self.sock.listen(1)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            with self.sock.accept()[0] as conn:
                self.accepted += 1
                conn.settimeout(3)
                raw = bytearray()
                while b'\r\n\r\n' not in raw:
                    chunk = conn.recv(8192)
                    if not chunk:
                        return
                    raw.extend(chunk)
                head, body = bytes(raw).split(b'\r\n\r\n', 1)
                length = int(next(row.split(b':', 1)[1] for row in head.split(b'\r\n')
                                  if row.lower().startswith(b'content-length:')))
                while len(body) < length:
                    part = conn.recv(8192)
                    if not part:
                        return
                    body += part
                self.received = (head, json.loads(body))
                if self.delay:
                    time.sleep(self.delay)
                if self.drip:
                    for byte in self.response:
                        conn.sendall(bytes([byte]))
                        time.sleep(0.02)
                else:
                    conn.sendall(self.response)
        except (OSError, TimeoutError):
            pass  # Expected disconnect from refusal/deadline tests.
        except BaseException as exc:
            self.error = type(exc).__name__
        finally:
            self.sock.close()
            self.done.set()

    def close(self):
        self.sock.close()
        self.thread.join(timeout=4)
        if self.thread.is_alive():
            raise AssertionError('fixture peer did not terminate')
        if self.error:
            raise AssertionError(self.error)


class HttpExchangeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def transport(self, response, **kwargs):
        peer = Peer(response, **kwargs)
        self.addCleanup(peer.close)
        exchange = http.Exchange('127.0.0.1', peer.port,
            candidate_sha256='a' * 64, deadline=time.monotonic() + 3)
        return exchange, peer

    def test_real_post_only_request_fields_without_proxy_or_credentials(self):
        exchange, peer = self.transport(framed(contract.encoded(RESPONSE)))
        before = contract.encoded(REQUEST)
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://invalid.example:1',
                                    'OPENAI_API_KEY': 'PUBLIC-NEVER-SEND'}):
            result = exchange(REQUEST)
        self.assertEqual(result, RESPONSE)
        self.assertEqual(before, contract.encoded(REQUEST))
        self.assertTrue(peer.done.wait(3))
        self.assertEqual(peer.received[1], REQUEST)
        self.assertTrue(peer.received[0].startswith(b'POST /api/interaction HTTP/1.1\r\n'))
        self.assertNotIn(b'Authorization', peer.received[0])
        self.assertNotIn(b'PUBLIC-NEVER-SEND', peer.received[0])
        self.assertEqual(exchange.candidate_sha256, 'a' * 64)

    def test_chunked_utf8_response_keeps_all_content(self):
        value = dict(RESPONSE, screen={'text': 'public café'})
        raw = contract.encoded(value)
        chunks = [raw[:7], raw[7:]]
        wire = b'HTTP/1.1 200 OK\r\nContent-Type: application/json;charset=UTF-8\r\nTransfer-Encoding: chunked\r\n\r\n'
        wire += b''.join(hex(len(x))[2:].encode() + b'\r\n' + x + b'\r\n' for x in chunks)
        exchange, _ = self.transport(wire + b'0\r\n\r\n')
        self.assertEqual(exchange(REQUEST), value)

    def test_malformed_arrived_json_is_private_mismatch_evidence(self):
        for raw in (b'{', b'{"screen":{},"screen":{}}', b'NaN', b'\xff'):
            with self.subTest(raw=raw):
                exchange, _ = self.transport(framed(raw))
                actual = exchange(REQUEST)
                self.assertEqual(actual, {'malformed_http_body_hex': raw.hex()})
                with self.assertRaises(contract.Refused):
                    replay.response_shape(actual, {'ended': True})
                with self.assertRaisesRegex(contract.Refused, '^http-exchange-fault$'):
                    exchange(REQUEST)

    def test_valid_nonobject_json_arrives_for_response_shape_mismatch(self):
        exchange, _ = self.transport(framed(b'[]'))
        actual = exchange(REQUEST)
        self.assertEqual(actual, [])
        with self.assertRaises(contract.Refused):
            replay.response_shape(actual, {'ended': True})

    def test_complete_rejected_metadata_is_private_malformed_without_followup(self):
        body = b'PRIVATE RESPONSE SENTINEL'
        wires = [framed(body, status=b'500 Internal Server Error'),
                 framed(body, status=b'302 Found',
                        headers=b'Location: http://example.invalid/private\r\n'),
                 framed(body).replace(b'application/json', b'text/html'),
                 framed(body, headers=b'Content-Encoding: gzip\r\n'),
                 b'HTTP/1.1 500 Error\r\nContent-Type: text/html\r\n'
                 b'Transfer-Encoding: chunked\r\n\r\n19\r\n' + body + b'\r\n0\r\n\r\n']
        for wire in wires:
            with self.subTest(header=wire.split(b'\r\n\r\n')[0]):
                exchange, peer = self.transport(wire)
                actual = exchange(REQUEST)
                lines = wire.split(b'\r\n\r\n')[0].decode('ascii').split('\r\n')
                self.assertEqual(actual, {'malformed_http_response': {
                    'status_line': lines[0], 'headers': lines[1:], 'body_hex': body.hex()}})
                with self.assertRaises(contract.Refused):
                    replay.response_shape(actual, {'ended': True})
                with self.assertRaisesRegex(contract.Refused, '^http-exchange-fault$'):
                    exchange(REQUEST)
                self.assertEqual(peer.accepted, 1)

    def test_replay_complete_500_mismatch_but_truncation_and_cl_te_fault(self):
        body = b'PRIVATE RESPONSE SENTINEL'
        complete = framed(body, status=b'500 Internal Server Error')
        cases = [(complete, 'MISMATCH'),
                 (framed(b'', status=b'500 Internal Server Error'), 'MISMATCH'),
                 (framed(b''), 'MISMATCH'), (complete[:-1], 'FAULT'),
                 (framed(body, status=b'500 Internal Server Error',
                         headers=b'Transfer-Encoding: chunked\r\n'), 'FAULT')]
        for wire, outcome in cases:
            with self.subTest(outcome=outcome, wire=wire):
                store = MemoryStore()
                bindings = {'public-synthetic-producer': 'b' * 64}
                commitment_raw = contract.stage_inputs(store, {},
                    context_sha256='c' * 64, producer_bindings=bindings)
                commitment = contract.decoded(commitment_raw)
                initial = {}
                digest = lambda value: contract.sha(contract.encoded(value))
                initial_sha = contract.put_blob(store, 'n1-initial', contract.encoded(initial))
                oracle = dict(session=contract.SESSION, producer_bindings=bindings,
                    binding={'commitment_sha256': contract.sha(commitment_raw)},
                    initial_sha256=initial_sha, states=[], rows=[dict(
                        case=contract.SESSION, session='public', aid='INITIAL', fields={},
                        before_sha256=digest(initial), expected={'ended': True})])
                oracle_sha = contract.put_blob(store, 'n1-oracle', contract.encoded(oracle))
                store.write('n1-complete.json', contract.encoded(dict(
                    status='ORACLE_CAPTURE_ONLY', oracle_sha256=oracle_sha,
                    commitment_sha256=contract.sha(commitment_raw))))
                store.write('n1-load-complete.json', contract.encoded(dict(
                    status='INITIAL_STATE_ONLY', full_state_sha256=digest(initial),
                    input_sha256=commitment['input_sha256'],
                    commitment_sha256=contract.sha(commitment_raw))))
                exchange, peer = self.transport(wire)
                # Only the producer/DB are public doubles. Exercise the real HTTP
                # peer and replay classification/storage, without oracle execution.
                with patch.object(replay.capture.reference, 'verify_producer',
                        return_value=(SimpleNamespace(digest=digest), None)), \
                     patch.object(replay.capture, 'bindings', return_value=bindings):
                    result = replay.replay(store, Path.cwd(), exchange=exchange,
                        snapshot=lambda: {}, candidate_sha256=exchange.candidate_sha256)
                self.assertEqual(result['outcome'], outcome)
                self.assertEqual(result['failed_check'], 'response-shape' if outcome == 'MISMATCH' else None)
                self.assertEqual(result['interactions'], 0)
                failure = contract.decoded(contract.get_blob(store, 'n1-candidate-failure'))
                if outcome == 'MISMATCH':
                    self.assertEqual(result['failing_index'], 0)
                    if wire == framed(b''):
                        self.assertEqual(failure['response'], {'malformed_http_body_hex': ''})
                    else:
                        expected_hex = body.hex() if wire == complete else ''
                        self.assertEqual(failure['response']['malformed_http_response']['body_hex'], expected_hex)
                    self.assertNotIn(body.hex().encode(), contract.encoded(result))
                else:
                    self.assertIsNone(failure)
                self.assertNotIn(body, contract.encoded(result))
                self.assertFalse(result['qualified'])
                with self.assertRaises(contract.Refused):
                    exchange(REQUEST)
                self.assertEqual(peer.accepted, 1)

    def test_conflicting_duplicate_and_missing_framing_refused(self):
        responses = [
            framed(b'{}', headers=b'Transfer-Encoding: chunked\r\n'),
            framed(b'{}', headers=b'Content-Length: 2\r\n'),
            b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{}',
        ]
        for raw in responses:
            exchange, _ = self.transport(raw)
            with self.assertRaisesRegex(contract.Refused, '^http-exchange-fault$'):
                exchange(REQUEST)

    def test_truncation_bad_chunk_and_trailer_are_faults(self):
        chunk_head = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n'
        for raw in (framed(b'{}')[:-1], chunk_head + b'z\r\n',
                    chunk_head + b'0\r\nX-Extra: value\r\n\r\n'):
            exchange, _ = self.transport(raw)
            with self.assertRaisesRegex(contract.Refused, '^http-exchange-fault$'):
                exchange(REQUEST)

    def test_declared_oversize_refused_without_large_body(self):
        raw = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' +
               str(http.RESPONSE_LIMIT + 1).encode() + b'\r\n\r\n')
        exchange, _ = self.transport(raw)
        with self.assertRaises(contract.Refused):
            exchange(REQUEST)

    def test_slow_drip_headers_cannot_restart_original_deadline(self):
        exchange, peer = self.transport(framed(b'{}'), drip=True)
        exchange._deadline = time.monotonic() + 0.25
        started = time.monotonic()
        with self.assertRaisesRegex(contract.Refused, '^http-exchange-fault$'):
            exchange(REQUEST)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(peer.accepted, 1)

    def test_expired_deadline_and_unapproved_request_never_open_socket(self):
        exchange = http.Exchange('127.0.0.1', 12345,
            candidate_sha256='a' * 64, deadline=time.monotonic() + 3)
        with patch.object(http.socket, 'socket') as connect:
            with self.assertRaises(contract.Refused):
                exchange(dict(REQUEST, expected={'secret': 'PUBLIC-MARKER'}))
            connect.assert_not_called()
        other = http.Exchange('127.0.0.1', 12345,
            candidate_sha256='a' * 64, deadline=time.monotonic() + 3)
        other._deadline = time.monotonic() - 1
        with patch.object(http.socket, 'socket') as connect:
            with self.assertRaises(contract.Refused):
                other(REQUEST)
            connect.assert_not_called()

    def test_refused_endpoint_and_deadline_before_any_socket(self):
        for host, port, deadline in [('localhost', 12345, time.monotonic()+3),
                ('192.0.2.1', 12345, time.monotonic()+3),
                ('127.0.0.1', 8768, time.monotonic()+3),
                ('127.0.0.1', True, time.monotonic()+3),
                ('127.0.0.1', 12345, float('nan'))]:
            with patch.object(http.socket, 'socket') as connect:
                with self.assertRaises(contract.Refused):
                    http.Exchange(host, port, candidate_sha256='a'*64, deadline=deadline)
                connect.assert_not_called()

    def test_reentrant_call_refused_without_a_second_socket(self):
        exchange = http.Exchange('127.0.0.1', 12345,
            candidate_sha256='a'*64, deadline=time.monotonic()+3)
        exchange._lock.acquire()
        try:
            with patch.object(http.socket, 'socket') as connect:
                with self.assertRaisesRegex(contract.Refused, '^http-concurrent-exchange$'):
                    exchange(REQUEST)
                connect.assert_not_called()
        finally:
            exchange._lock.release()
