"""CI-only synthetic integration and a bare-provider mutation control."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.providers import BoundedModelProvider
from tools.ci.p5_controller_budgets import CASES, observe_case


class ControllerBudgetTests(unittest.TestCase):
    def test_real_controller_budget_receipts_and_failed_call_accounting(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='p5-budget-ci-') as temp:
            for case in CASES:
                with self.subTest(case=case):
                    row = observe_case(Path(temp)/case, repository, case)
                    self.assertEqual(row['wrapper_type'], 'AccountedModelProvider')
                    self.assertEqual(row['controller_receipt']['status'], 'blocked')
                    self.assertEqual(row['real_model_calls'], 0)
                    self.assertEqual(row['actual_spend'], 0)
                    self.assertEqual(row['secondary_stub_calls'], 0)

    def test_bare_provider_controller_regression_is_detected(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        repository = Path(__file__).resolve().parents[1]
        def bare(provider, order, **kwargs):
            return BoundedModelProvider(provider, order)
        with tempfile.TemporaryDirectory(prefix='p5-bare-ci-') as temp:
            with patch('lightyear_factory.orchestrator.AccountedModelProvider', new=bare):
                with self.assertRaisesRegex(ValueError, '^p5-budget-base-provider-path$'):
                    observe_case(Path(temp)/'bare', repository, 'dollar-preflight')


if __name__ == '__main__':
    unittest.main()
