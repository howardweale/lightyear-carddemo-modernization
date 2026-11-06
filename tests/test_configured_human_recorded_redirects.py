"""CI-only request/redirect refusals; no model endpoint, proof or authority."""
from io import BytesIO
import os
import unittest
from urllib.error import HTTPError
from urllib.request import Request
from lightyear_factory.contracts import ContractError
from lightyear_factory.additional_providers import _RecordedNoRedirect
from lightyear_execution.configured_human_recorded_transport import (
    require_recorded_request, recorded_transport_identity, bind_native_recorded_transport)


class ConfiguredRecordedRedirectTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_redirect_codes_never_create_a_second_request(self):
        for code in (301,302,303,307,308):
            with self.subTest(code=code):
                request=Request('https://api.openai.com/v1/responses',data=b'{}',method='POST')
                body=BytesIO(b'synthetic-redirect-body')
                with self.assertRaises(HTTPError) as raised:
                    _RecordedNoRedirect().redirect_request(request,body,code,'redirect',{},'https://example.invalid/')
                self.assertEqual(raised.exception.code,code)
                self.assertIs(raised.exception.fp,body)

    def test_exact_count_and_generation_shapes_do_not_confer_authority(self):
        for suffix in ('responses','responses/input_tokens'):
            request=Request('https://api.openai.com/v1/'+suffix,data=b'{}',method='POST')
            self.assertIsNone(require_recorded_request(request))

    def test_other_origin_query_fragment_or_scheme_refused(self):
        for url in ('http://api.openai.com/v1/responses','https://example.invalid/v1/responses',
                    'https://api.openai.com/v1/responses?extra=1','https://api.openai.com/v1/responses#fragment',
                    'https://api.openai.com:443/v1/responses'):
            with self.assertRaisesRegex(ContractError,'exact-request'):
                require_recorded_request(Request(url,data=b'{}',method='POST'))

    def test_host_override_or_non_post_refused(self):
        for request in (Request('https://api.openai.com/v1/responses',data=b'{}',headers={'Host':'example.invalid'},method='POST'),
                        Request('https://api.openai.com/v1/responses',data=b'{}',method='GET')):
            with self.assertRaisesRegex(ContractError,'exact-request'):require_recorded_request(request)

    def test_forged_provider_cannot_register_or_retrieve_native_transport(self):
        for action in (bind_native_recorded_transport,recorded_transport_identity):
            with self.assertRaises(ContractError):action(object())
