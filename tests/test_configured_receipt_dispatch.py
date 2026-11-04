"""CI-only dispatch boundary refusals; no main admission or signing."""
import os,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from lightyear_factory.contracts import ContractError
from lightyear_factory.cli import build_parser
from lightyear_execution.configured_receipt_dispatch import _prepare,_dispatch_paths

class ConfiguredReceiptDispatchTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def test_non_ci_refuses_before_input_or_signer_read(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            with self.assertRaisesRegex(ContractError,'ci-only'):_prepare(object())
    def test_onedrive_evidence_refused_before_signer_read(self):
        bundle={'admission':SimpleNamespace(root=Path('/independent/source'))}
        with self.assertRaisesRegex(ContractError,'onedrive-evidence'):
            _dispatch_paths(SimpleNamespace(runs_root=Path('/OneDrive/receipt')),bundle)
    def test_receipt_execution_requires_external_signer_arguments(self):
        parser=build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(['human-configured-receipt-execute','--source-root','source'])
    def test_old_public_entry_does_not_accept_receipt_key_flags(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(['human-configured-execute','--candidate-signing-key','unused'])
