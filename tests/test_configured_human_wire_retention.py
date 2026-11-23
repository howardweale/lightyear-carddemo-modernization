"""CI-only byte retention/refusal tests; no transport or passed authority."""
from http.client import IncompleteRead
from io import BytesIO
import os
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_human_wire import (
    LIMIT, bounded_response_bytes, require_native_recorder_binding)


class ConfiguredWireRetentionTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_exact_original_json_order_preserved(self):
        raw = b'{"model":"synthetic","input":[],"instructions":"public"}'
        self.assertEqual(bounded_response_bytes(BytesIO(raw)), (raw, True))

    def test_empty_response_is_exact_bytes_not_json_success(self):
        self.assertEqual(bounded_response_bytes(BytesIO(b'')), (b'', True))

    def test_oversize_retains_bounded_prefix_as_incomplete(self):
        raw = b'a' * (LIMIT + 1)
        self.assertEqual(bounded_response_bytes(BytesIO(raw)), (raw[:LIMIT], False))

    def test_exact_limit_requires_eof(self):
        raw = b'a' * LIMIT
        self.assertEqual(bounded_response_bytes(BytesIO(raw)), (raw, True))

    def test_short_reads_are_not_mistaken_for_eof(self):
        class Chunks:
            def __init__(self): self.parts = iter((b'first', b'second', b''))
            def read(self, count): return next(self.parts)
        self.assertEqual(bounded_response_bytes(Chunks()), (b'firstsecond', True))

    def test_partial_response_remains_incomplete(self):
        class Partial:
            def read(self, count): raise IncompleteRead(b'original-prefix', 10)
        self.assertEqual(bounded_response_bytes(Partial()), (b'original-prefix', False))

    def test_partial_after_short_read_preserves_both_prefixes(self):
        class Partial:
            def __init__(self): self.calls = 0
            def read(self, count):
                self.calls += 1
                if self.calls == 1: return b'first-'
                raise IncompleteRead(b'second', 10)
        self.assertEqual(bounded_response_bytes(Partial()), (b'first-second', False))

    def test_non_bytes_cannot_become_transport_evidence(self):
        class Invalid:
            def read(self, count): return 'decoded'
        with self.assertRaisesRegex(ContractError, 'byte-type'):
            bounded_response_bytes(Invalid())

    def test_dictionary_or_callback_cannot_bind_a_recorder(self):
        with patch('urllib.request.urlopen') as transport:
            for provider, recorder in (({}, {}), (object(), lambda: None)):
                with self.assertRaisesRegex(ContractError, 'native-binding'):
                    require_native_recorder_binding(provider, recorder)
            transport.assert_not_called()
