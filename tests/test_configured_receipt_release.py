"""CI-only refusal probes. No forged admitted context or passed authority."""
import os
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_receipt_release import (
    release_closed_receipt_references, require_no_retained_receipt_attempt)

@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'CI-only')
class ReceiptReleaseRefusals(unittest.TestCase):
    def test_untrusted_owner_never_reaches_release(self):
        for value in (None, object(), {}, {'_closed': True, '_pid': os.getpid()}):
            with self.assertRaisesRegex(ContractError, 'closed-original-process'):
                release_closed_receipt_references(value, None)

    def test_diagnostic_requires_absolute_attempt_path(self):
        for value in ('relative/drill-inert', 'drill-inert', '.'):
            with self.assertRaisesRegex(ContractError, 'exact-run-directory'):
                require_no_retained_receipt_attempt(value)
