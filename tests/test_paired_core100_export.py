"""Offline verification of the published native Core100 run; no database calls."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_data import oracle_paired_coverage as coverage
from lightyear_workflow import campaign_engine as engine, paired_types as suite

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / 'docs/receipts/oracle26ai-alloydb-core100-20260917'


class PublishedCore100Tests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('cryptography'), 'Dedicated signing CI installs .[control-tower]')
    def test_native_family_journals_replay_and_deduplicate_with_pilot(self):
        manifest = json.loads((EXPORT / 'manifest.json').read_text())
        # Published evidence must verify without depending on an operator's lab.
        with patch.object(engine, 'records', return_value=[]):
            entries = coverage.evidence(ROOT)
        auth, events, summary, key = next(row for row in entries if row[0]['run_id'] == manifest['successful_run_id'])
        self.assertEqual(auth['campaign_id'], suite.CAMPAIGN)
        result = coverage.admitted(ROOT, auth, events, summary, key)
        self.assertEqual(result['status'], 'passed-bounded-native')
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual([result[k] for k in ('source_completed', 'target_completed', 'comparisons_completed', 'matched')], [100] * 4)
        self.assertEqual([f['matched'] for f in result['families']], [20] * 5)
        self.assertTrue(all(f['mismatched'] == f['blocked'] == f['pending'] == 0 for f in result['families']))
        journals = Counter(e['payload']['journal_id'] for e in events)
        self.assertLess(journals['campaign'], 256)
        self.assertEqual({k: v for k, v in journals.items() if k != 'campaign'}, {f: 60 for f in suite.FAMILIES})
        aggregate = coverage.project(ROOT, [row for row in entries if row[0]['campaign_id'] in (engine.CAMPAIGN, suite.CAMPAIGN)])
        self.assertEqual(aggregate['oracle26ai_executed_case_count'], 100)
        self.assertEqual(aggregate['alloydb_equivalent_case_count'], 100)
        self.assertEqual(aggregate['oracle26ai_verified_behavior_count'], 25)
        self.assertEqual(aggregate['alloydb_equivalent_behavior_count'], 25)
        self.assertGreater(manifest['planning_allowance_usd'], 0)
        self.assertLessEqual(manifest['planning_allowance_usd'], manifest['authorized_cumulative_estimated_budget_usd'])


if __name__ == '__main__':
    unittest.main()
