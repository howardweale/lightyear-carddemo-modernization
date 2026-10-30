"""CI-only native recording boundary refusals. No transport or passed proof."""
import os
import unittest
from unittest.mock import patch
from urllib.request import Request

from lightyear_factory.contracts import ContractError
from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider


def provider(**kwargs):
    return SnapshotOpenAIResponsesProvider(api_key='synthetic-unused',
        model='gpt-5.4-2026-03-05', input_usd_per_million=5.5,
        output_usd_per_million=24.75, max_retries=0, token_preflight=True, **kwargs)


class ConfiguredNativeWireRefusalTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_default_has_no_recorder_or_active_call(self):
        value=provider()
        self.assertIsNone(value.transport_recorder)
        self.assertIsNone(value.last_transport_record)
        self.assertFalse(value._recorded_call_active)

    def test_dictionary_recorder_is_refused_without_transport(self):
        value=provider()
        with patch('urllib.request.urlopen') as opened:
            with self.assertRaisesRegex(ContractError, 'native-binding'):
                value.bind_transport_recorder({'status':'passed'})
            opened.assert_not_called()
        self.assertIsNone(value.transport_recorder)

    def test_started_provider_cannot_late_bind(self):
        value=provider();value._transport_started=True
        with self.assertRaisesRegex(ContractError, 'recorder-reuse'):
            value.bind_transport_recorder(object())

    def test_injected_opener_marker_is_never_cleared(self):
        def forbidden(*args, **kwargs): raise AssertionError('must not open')
        value=provider(opener=forbidden)
        self.assertTrue(value._injected_opener)
        with self.assertRaises(ContractError): value.bind_transport_recorder(object())
        self.assertTrue(value._injected_opener)
        self.assertIs(value._transport_opener, forbidden)

    def test_direct_generation_without_active_admission_is_refused(self):
        value=provider()
        request=Request('https://api.openai.com/v1/responses',data=b'{}',method='POST')
        with self.assertRaisesRegex(ContractError, 'active-call'):
            with value._open_recorded_generation(request): pass

    def test_recorded_call_rejects_forged_recorder_before_base_provider(self):
        value=provider();value.transport_recorder=object()
        with patch('lightyear_factory.providers.OpenAIResponsesProvider.complete') as base:
            with self.assertRaisesRegex(ContractError, 'native-binding'):
                value.complete('planner','synthetic',{}, {})
            base.assert_not_called()
        self.assertFalse(value._recorded_call_active)
