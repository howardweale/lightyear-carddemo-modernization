"""CI-only original HTTPResponse/socket-pair framing; no provider/admission.

Native OS sockets and the actual stdlib HTTP parser exercise premature EOF.
No external endpoint, TLS, model, key, proof or passed context is fabricated.
HTTPError body completeness is never a successful HTTP result.
"""
from contextlib import contextmanager
from http.client import HTTPResponse
import os,socket,unittest
from urllib.error import HTTPError
from lightyear_execution.configured_human_wire import bounded_response_bytes

@contextmanager
def original_response(body,headers,status='200 OK'):
    reader,writer=socket.socketpair()
    reader.settimeout(3);writer.settimeout(3)
    response=None
    try:
        # All cases are small enough to send synchronously before the read.
        wire=('HTTP/1.1 '+status+'\r\n'+headers+'\r\n').encode('ascii')+body
        if len(wire)>4096:raise AssertionError('small socket-pair fixture only')
        writer.sendall(wire);writer.shutdown(socket.SHUT_WR)
        response=HTTPResponse(reader);response.begin()
        yield response
    finally:
        if response is not None:response.close()
        reader.close();writer.close()

class NativeHTTPFraming(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def test_native_bounded_EOF_does_not_raise_with_declared_bytes_missing(self):
        with original_response(b'{}','Content-Length: 9\r\n') as response:
            self.assertEqual(response.read(100),b'{}')
            self.assertEqual(response.read(100),b'')
            self.assertEqual(response.length,7)
    def test_complete_content_length_preserves_original_bytes(self):
        raw=b'{ "original": true }'
        with original_response(raw,'Content-Length: '+str(len(raw))+'\r\n') as response:
            self.assertEqual(bounded_response_bytes(response),(raw,True))
    def test_valid_json_with_truncated_framing_is_incomplete(self):
        with original_response(b'{}','Content-Length: 9\r\n') as response:
            self.assertEqual(bounded_response_bytes(response),(b'{}',False))
    def test_missing_entire_declared_body_is_incomplete(self):
        with original_response(b'','Content-Length: 9\r\n') as response:
            self.assertEqual(bounded_response_bytes(response),(b'',False))
    def test_original_HTTPError_wrapper_retains_truncation(self):
        with original_response(b'{"error":1}','Content-Length: 30\r\n','429 Too Many Requests') as response:
            error=HTTPError('https://fixture.invalid/',429,'fixture refusal',response.headers,response)
            try:self.assertEqual(bounded_response_bytes(error),(b'{"error":1}',False))
            finally:error.close()
    def test_complete_HTTPError_body_does_not_mean_HTTP_success(self):
        with original_response(b'{}','Content-Length: 2\r\n','503 Service Unavailable') as response:
            error=HTTPError('https://fixture.invalid/',503,'fixture refusal',response.headers,response)
            try:
                self.assertEqual(bounded_response_bytes(error),(b'{}',True))
                self.assertEqual(error.code,503)
            finally:error.close()
    def test_native_complete_chunked_body_preserved(self):
        with original_response(b'2\r\n{}\r\n0\r\n\r\n','Transfer-Encoding: chunked\r\n') as response:
            self.assertEqual(bounded_response_bytes(response),(b'{}',True))
    def test_native_missing_terminal_chunk_is_incomplete(self):
        with original_response(b'2\r\n{}\r\n','Transfer-Encoding: chunked\r\n') as response:
            self.assertEqual(bounded_response_bytes(response),(b'{}',False))
    def test_native_close_delimited_EOF_remains_complete(self):
        with original_response(b'original','Connection: close\r\n') as response:
            self.assertEqual(bounded_response_bytes(response),(b'original',True))
    def test_native_response_closed_before_body_stays_incomplete(self):
        with original_response(b'{}','Content-Length: 2\r\n') as response:
            response.close()
            self.assertEqual(bounded_response_bytes(response),(b'',False))
