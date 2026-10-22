"""CI-only rejected-body transport regressions; no real backend or model."""
import email.message
import http.client
import io
import unittest
from tests import test_ms94_b06_http_broker as fixtures
from tools.ms94_b06_http_broker import MAX_BODY


class RejectedBodyTests(unittest.TestCase):
    def context(self):
        case = fixtures.HttpBrokerTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_rejected_large_malformed_bodies_deliver_exact_response_without_backend(self):
        case = self.context()
        body = b'not-json:' + b'x' * 65536
        for extra, status in [({'Authorization': 'Bearer wrong'}, 401),
                              ({'Origin': 'https://untrusted.example'}, 403),
                              ({'Host': 'untrusted.example'}, 403)]:
            for attempt in range(4):
                with self.subTest(extra=extra, attempt=attempt):
                    headers = {'Authorization': 'Bearer ' + case.session.token,
                               'Content-Type': 'application/json'}
                    headers.update(extra)
                    client = http.client.HTTPConnection(case.broker.host, timeout=10)
                    try:
                        client.request('POST', '/mcp', body, headers)
                        response = client.getresponse()
                        self.assertEqual(status, response.status)
                        self.assertEqual(b'', response.read())
                    finally:
                        client.close()
        self.assertEqual([], case.backend.calls)
        self.assertEqual(0, case.session.compilations)
        self.assertFalse(case.session.initialized)

    def test_drain_is_bounded_and_never_reconsumes_accepted_or_ambiguous_body(self):
        case = self.context()
        handler_type = case.broker.server.RequestHandlerClass
        for lengths, transfer, consumed, expected in [(['4'], None, False, 4),
                (['4'], None, True, 0), ([], None, False, 0),
                (['4', '4'], None, False, 0), (['4'], 'chunked', False, 0),
                ([str(MAX_BODY+1)], None, False, 0), (['-1'], None, False, 0),
                (['garbage'], None, False, 0), (['9'*100], None, False, 0)]:
            with self.subTest(lengths=lengths, transfer=transfer, consumed=consumed):
                handler = object.__new__(handler_type)
                handler.headers = email.message.Message()
                for length in lengths: handler.headers['Content-Length'] = length
                if transfer: handler.headers['Transfer-Encoding'] = transfer
                handler.body_consumed = consumed
                handler.rfile = io.BytesIO(b'dataMORE')
                handler.drain_rejected_body()
                self.assertEqual(expected, handler.rfile.tell())
                handler.drain_rejected_body()
                self.assertEqual(expected, handler.rfile.tell())
