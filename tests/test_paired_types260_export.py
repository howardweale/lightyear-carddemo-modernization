"""Offline verification of actual published native attempts; no database calls."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_data import oracle_paired_coverage as coverage
from lightyear_workflow import campaign_engine as engine, paired_types260 as suite

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / 'docs/receipts/oracle26ai-alloydb-types260-20260917'


@unittest.skipUnless(importlib.util.find_spec('cryptography'), 'Dedicated signing CI installs .[control-tower]')
class PublishedTypes260Tests(unittest.TestCase):
    def entries(self):
        with patch.object(engine, 'records', return_value=[]):
            return coverage.evidence(ROOT)

    def test_native_260_replays_and_deduplicates_every_prior_campaign(self):
        manifest = json.loads((EXPORT / 'manifest.json').read_text())
        entries = self.entries()
        auth, events, summary, key = next(row for row in entries if row[0]['run_id'] == manifest['successful_run_id'])
        self.assertEqual(auth['campaign_id'], suite.CAMPAIGN)
        result = coverage.admitted(ROOT, auth, events, summary, key)
        self.assertEqual(result['status'], 'passed-bounded-native')
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual([result[k] for k in ('source_completed', 'target_completed', 'comparisons_completed', 'matched')], [260] * 4)
        self.assertEqual([f['matched'] for f in result['families']], [20] * 13)
        self.assertTrue(all(f['mismatched'] == f['blocked'] == f['pending'] == 0 for f in result['families']))
        journals = Counter(e['payload']['journal_id'] for e in events)
        self.assertLess(journals['campaign'], 256)
        self.assertEqual({k: v for k, v in journals.items() if k != 'campaign'}, {f: 60 for f in suite.FAMILIES})
        self.assertEqual(auth['plan']['families'][:2], ['interval-ym', 'interval-ds'])
        aggregate = coverage.project(ROOT, entries)
        self.assertEqual(aggregate['oracle26ai_executed_case_count'], 260)
        self.assertEqual(aggregate['alloydb_equivalent_case_count'], 260)
        self.assertEqual(aggregate['oracle26ai_verified_behavior_count'], 65)
        self.assertEqual(aggregate['alloydb_equivalent_behavior_count'], 65)
        self.assertFalse(aggregate['platform_qualification_established_by_this_campaign'])
        self.assertGreater(manifest['planning_allowance_usd'], 0)
        self.assertLessEqual(manifest['planning_allowance_usd'], manifest['authorized_cumulative_estimated_budget_usd'])

    def test_original_compile_failure_keeps_220_matches_and_40_unexecuted(self):
        auth, events, summary, key = next(row for row in self.entries() if row[0]['plan']['plan_sha256'] == suite.RETIRED_PLAN)
        result = coverage.admitted(ROOT, auth, events, summary, key)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['matched'], 220)
        self.assertEqual(sum(f['blocked'] for f in result['families']), 40)
        self.assertTrue(result['cleanup']['complete'])
        self.assertIn('ORA-00932', result['error'])
        for row in result['case_results']:
            if row['case_id'].startswith(tuple(f'ORA-TYPE-{n:03}-' for n in range(56, 66))):
                self.assertIsNone(row['oracle'])
                self.assertIsNone(row['alloydb'])
                self.assertIsNone(row['comparison'])
        case = next(c for c in suite.cases(ROOT) if c['topic'] == 'interval-ym')
        retired = ROOT / suite.ARTIFACTS / 'retired-v1/oracle' / (case['id'] + '.sql')
        original_read = Path.read_text
        def tamper(path, *args, **kwargs):
            result = original_read(path, *args, **kwargs)
            return result + '-- changed' if path == retired else result
        with patch.object(Path, 'read_text', tamper):
            with self.assertRaisesRegex(ValueError, 'SQL contract'):
                coverage.admitted(ROOT, auth, events, summary, key)


if __name__ == '__main__':
    unittest.main()
