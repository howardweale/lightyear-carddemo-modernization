"""Offline loopback CI only: no external model, API credential or signing."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading
import time
import unittest

from lightyear_factory.contracts import ContractError
from tools.ci import supervised_flex_exchange as exchange
from tools.ci import supervised_intcalc_boundary as boundary


class SupervisedFlexExchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.candidate = subprocess.check_output(
            ['git', '-C', str(root), 'show', 'HEAD:' + boundary.PATH]).replace(
                b'MONTHS_PERCENT = 1200', b'MONTHS_PERCENT = 100')

    def server(self, mode):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                observed.append((self.path, self.rfile.read(length)))
                self.send_response(302 if mode == 'redirect' else 503 if mode == 'error' else 200)
                self.send_header('Content-Type', 'application/json')
                body = b'{"fixture":true}'
                if mode == 'flood':
                    body = b'x' * (exchange.BODY_LIMIT + 1)
                if mode == 'redirect':
                    self.send_header('Location', '/would-be-third-send')
                if mode == 'too-large':
                    self.send_header('Content-Length', str(exchange.BODY_LIMIT + 1))
                elif mode == 'duplicate-length':
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Content-Length', str(len(body)))
                elif mode == 'compressed':
                    self.send_header('Content-Encoding', 'gzip')
                elif mode == 'chunked':
                    self.send_header('Transfer-Encoding', 'chunked')
                elif mode not in ('no-length', 'flood'):
                    self.send_header('Content-Length', str(len(body) + (10 if mode == 'truncated' else 0)))
                self.end_headers()
                if mode == 'slow':
                    time.sleep(0.2)
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.addCleanup(cleanup)
        return http.client.HTTPConnection('127.0.0.1', server.server_port), observed

    def send(self, connection, seconds=2.0):
        return exchange._exchange_once(connection, self.candidate,
                                       'Bearer offline-fixture', time.monotonic() + seconds)

    def test_exactly_one_post_and_labelled_hashes(self):
        connection, observed = self.server('ok')
        raw, receipt = self.send(connection)
        self.assertEqual(raw, b'{"fixture":true}')
        self.assertEqual(observed, [('/v1/responses', boundary.generation_request(self.candidate))])
        self.assertEqual(receipt['label'], boundary.LABEL)
        self.assertEqual(receipt['physical_requests_attempted'], 1)
        self.assertFalse(receipt['qualification_evidence'])
        self.assertIsNone(connection.sock)

    def test_redirect_is_not_followed(self):
        connection, observed = self.server('redirect')
        with self.assertRaisesRegex(ContractError, 'http-refused'):
            self.send(connection)
        self.assertEqual(len(observed), 1)
        self.assertIsNone(connection.sock)

    def test_server_failure_has_no_retry(self):
        connection, observed = self.server('error')
        with self.assertRaisesRegex(ContractError, 'http-refused'):
            self.send(connection)
        self.assertEqual(len(observed), 1)

    def test_ambiguous_or_encoded_body_refuses(self):
        for mode in ('too-large', 'duplicate-length', 'compressed', 'chunked'):
            with self.subTest(mode=mode):
                connection, observed = self.server(mode)
                with self.assertRaises(ContractError):
                    self.send(connection)
                self.assertEqual(len(observed), 1)

    def test_truncated_body_refuses_without_retry(self):
        connection, observed = self.server('truncated')
        with self.assertRaises(ContractError):
            self.send(connection)
        self.assertEqual(len(observed), 1)

    def test_body_without_length_is_bounded_and_returned(self):
        connection, observed = self.server('no-length')
        raw, receipt = self.send(connection)
        self.assertEqual(raw, b'{"fixture":true}')
        self.assertEqual(receipt['response_bytes'], len(raw))
        self.assertEqual(len(observed), 1)

    def test_timeout_is_unknown_and_never_retried(self):
        connection, observed = self.server('slow')
        with self.assertRaisesRegex(ContractError, 'outcome-unknown|deadline'):
            self.send(connection, 0.05)
        self.assertEqual(len(observed), 1)
        self.assertIsNone(connection.sock)

    def test_expired_deadline_refuses_before_send(self):
        connection, observed = self.server('ok')
        with self.assertRaisesRegex(ContractError, 'deadline'):
            exchange._exchange_once(connection, self.candidate, 'Bearer offline-fixture',
                                     time.monotonic() - 1.0)
        self.assertEqual(observed, [])

    def test_header_injection_refuses_before_send(self):
        connection, observed = self.server('ok')
        with self.assertRaisesRegex(ContractError, 'authorization-format'):
            exchange._exchange_once(connection, self.candidate, 'Bearer bad\r\nX: bad',
                                     time.monotonic() + 2.0)
        self.assertEqual(observed, [])

    def test_changed_candidate_refuses_before_send(self):
        connection, observed = self.server('ok')
        with self.assertRaises(ContractError):
            exchange._exchange_once(connection, self.candidate + b'\n', 'Bearer offline-fixture',
                                     time.monotonic() + 2.0)
        self.assertEqual(observed, [])

    def test_connection_failure_is_redacted_and_not_retried(self):
        # A reserved, then closed local listener avoids selecting an arbitrary port.
        server = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
        port = server.server_port
        server.server_close()
        connection = http.client.HTTPConnection('127.0.0.1', port)
        with self.assertRaisesRegex(ContractError, '^supervised-exchange-outcome-unknown$'):
            self.send(connection)
        self.assertIsNone(connection.sock)

    def test_unannounced_body_overflow_refuses(self):
        connection, observed = self.server('flood')
        with self.assertRaisesRegex(ContractError, 'response-size'):
            self.send(connection)
        self.assertEqual(len(observed), 1)
        self.assertIsNone(connection.sock)
