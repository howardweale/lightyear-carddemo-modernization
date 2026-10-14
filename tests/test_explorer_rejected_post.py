import io
import unittest
from http import HTTPStatus
from unittest.mock import Mock
from lightyear_knowledge_graph.explorer import ExplorerRequestHandler


class RejectedPostTests(unittest.TestCase):
    def handler(self, body, length=None):
        h = ExplorerRequestHandler.__new__(ExplorerRequestHandler)
        h.path = '/api/workflow/execution'
        h.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(body) if length is None else length)}
        h.rfile = io.BytesIO(body)
        h._json = Mock()
        return h

    def test_unknown_post_consumes_body_but_never_dispatches(self):
        h = self.handler(b'{}')
        h.do_POST()
        self.assertEqual(h.rfile.tell(), 2)
        self.assertEqual(h._json.call_args.args[1], HTTPStatus.NOT_FOUND)

    def test_unknown_oversized_body_is_not_drained_unboundedly(self):
        h = self.handler(b'{}', 65537)
        h.do_POST()
        self.assertEqual(h.rfile.tell(), 0)
        self.assertEqual(h._json.call_args.args[1], HTTPStatus.BAD_REQUEST)
