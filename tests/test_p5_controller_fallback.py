"""Synthetic CI only: signed routing is not permission to change F2 models."""
import os
from pathlib import Path
import tempfile
import unittest
from tools.ci.p5_fallback_probe import observe


class ControllerFallbackTests(unittest.TestCase):
    def test_signed_fallback_shares_budget_and_preserves_model_binding(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory(prefix='p5-fallback-ci-') as temp:
            for changed in (False, True):
                with self.subTest(changed_model=changed):
                    row = observe(Path(temp)/str(changed), Path(__file__).resolve().parents[1],
                                  changed_fallback_model=changed)
                    self.assertTrue(row['routing_approval_verified'])
                    self.assertEqual(row['accounted_calls'], 1 if changed else 2)
                    self.assertEqual(row['secondary_calls'], 0 if changed else 1)
                    self.assertEqual(row['controller_receipt']['status'], 'blocked')
                    self.assertEqual(row['actual_spend'], 0)
                    self.assertEqual(row['real_model_calls'], 0)


if __name__ == '__main__':
    unittest.main()
