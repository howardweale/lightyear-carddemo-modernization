"""CI-only count body buffering using original HTTP parser; no admission/send."""
from io import BytesIO
import os,unittest
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_human_wire import LIMIT,bounded_count_response
from test_configured_human_http_framing import original_response

class CountResponseBoundTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_complete_native_count_body_preserves_bytes_and_headers(self):
        raw=b'{ "input_tokens": 123 }'
        with original_response(raw,'Content-Length: '+str(len(raw))+'\r\n') as response:
            with bounded_count_response(response) as buffered:
                self.assertEqual(buffered.read(),raw)
                self.assertIs(buffered.headers,response.headers)
            self.assertTrue(buffered.closed)

    def test_truncated_valid_count_json_never_reaches_parser(self):
        with original_response(b'{"input_tokens":1}','Content-Length: 100\r\n') as response:
            with self.assertRaisesRegex(ContractError,'incomplete-count-response'):
                with bounded_count_response(response):self.fail('incomplete body yielded')

    def test_complete_native_chunked_count(self):
        raw=b'{"input_tokens":1}'
        body=hex(len(raw))[2:].encode()+b'\r\n'+raw+b'\r\n0\r\n\r\n'
        with original_response(body,'Transfer-Encoding: chunked\r\n') as response:
            with bounded_count_response(response) as buffered:self.assertEqual(buffered.read(),raw)

    def test_missing_terminal_chunk_refuses_even_valid_json(self):
        raw=b'{"input_tokens":1}'
        body=hex(len(raw))[2:].encode()+b'\r\n'+raw+b'\r\n'
        with original_response(body,'Transfer-Encoding: chunked\r\n') as response:
            with self.assertRaisesRegex(ContractError,'incomplete-count-response'):
                with bounded_count_response(response):self.fail('incomplete chunking yielded')

    def test_oversized_byte_stream_never_yields(self):
        with BytesIO(b'x'*(LIMIT+1)) as response:
            with self.assertRaisesRegex(ContractError,'incomplete-count-response'):
                with bounded_count_response(response):self.fail('oversized body yielded')

    def test_buffer_is_closed_when_downstream_parser_refuses(self):
        with original_response(b'not-json','Content-Length: 8\r\n') as response:
            with self.assertRaisesRegex(ValueError,'downstream refusal'):
                with bounded_count_response(response) as buffered:
                    self.assertEqual(buffered.read(),b'not-json')
                    raise ValueError('downstream refusal')
            self.assertTrue(buffered.closed)

    def test_missing_declared_body_cannot_become_empty_count(self):
        with original_response(b'','Content-Length: 20\r\n') as response:
            with self.assertRaisesRegex(ContractError,'incomplete-count-response'):
                with bounded_count_response(response):self.fail('missing body yielded')
