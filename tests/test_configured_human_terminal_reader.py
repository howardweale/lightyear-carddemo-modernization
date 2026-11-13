"""CI-only diagnostic byte-chain tests; never create or mock live authority."""
import json
import os
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.configured_human_terminal import (
    _ledger_bytes,read_original_configured_terminal)


def event(sequence,previous=None):
    value=dict(sequence=sequence,previous_sha256=previous,state='BLOCKED',
               kind='controller_error',payload={'reason':'public-test'})
    value['event_sha256']=canonical_hash(value)
    return value


class ConfiguredTerminalReaderTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_valid_byte_chain_is_read_without_an_authority_claim(self):
        first=event(1);second=event(2,first['event_sha256'])
        raw=b''.join(json.dumps(row).encode()+b'\n' for row in (first,second))
        self.assertEqual(_ledger_bytes(raw),[first,second])

    def test_truncated_last_row_is_refused(self):
        with self.assertRaisesRegex(ContractError,'incomplete-ledger'):
            _ledger_bytes(json.dumps(event(1)).encode())

    def test_blank_middle_row_is_refused(self):
        with self.assertRaisesRegex(ContractError,'blank-ledger-row'):
            _ledger_bytes(json.dumps(event(1)).encode()+b'\n\n')

    def test_modified_payload_is_refused(self):
        row=event(1);row['payload']['reason']='changed'
        with self.assertRaisesRegex(ContractError,'ledger-chain'):
            _ledger_bytes(json.dumps(row).encode()+b'\n')

    def test_wrong_predecessor_is_refused_even_if_row_rehashed(self):
        first=event(1);second=event(2,'0'*64)
        with self.assertRaisesRegex(ContractError,'ledger-chain'):
            _ledger_bytes(b''.join(json.dumps(x).encode()+b'\n' for x in (first,second)))

    def test_receipt_mapping_is_not_same_process_origin(self):
        with self.assertRaisesRegex(ContractError,'original-controller'):
            read_original_configured_terminal({'status':'passed'})

    def test_new_controller_cannot_reconstruct_origin_or_retry_proof(self):
        from lightyear_factory.orchestrator import FactoryOrchestrator
        controller=object.__new__(FactoryOrchestrator)
        with patch('lightyear_execution.configured_human_context.ConfiguredHumanExecutionContext._live',
                   side_effect=AssertionError('diagnostics cannot retry authority')) as live:
            with self.assertRaisesRegex(ContractError,'same-process-origin'):
                read_original_configured_terminal(controller)
            live.assert_not_called()
