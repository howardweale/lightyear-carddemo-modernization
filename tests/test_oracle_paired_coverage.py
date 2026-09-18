"""Coverage admission tests. Fabricated observations exist only in temporary tests."""
import copy
import importlib.util
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from lightyear_data import oracle_paired_coverage as coverage
from lightyear_workflow import campaign_engine as engine, paired_types as suite
from tests import test_paired_core100 as core

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('cryptography'), 'Dedicated signing CI installs .[control-tower]')
class PairedCoverageTests(unittest.TestCase):
    def test_published_native_pilot_is_admitted_without_local_authority(self):
        # Do not consume ignored local lab state in a repository test.
        with patch.object(engine, 'records', return_value=[]):
            entries = coverage.evidence(ROOT)
        value = coverage.project(ROOT, [row for row in entries if row[0]['campaign_id'] == engine.CAMPAIGN])
        self.assertEqual(value['oracle26ai_executed_case_count'], 20)
        self.assertEqual(value['alloydb_equivalent_case_count'], 20)
        self.assertEqual(value['oracle26ai_verified_behavior_count'], 5)
        self.assertEqual(value['bounded_model_verified_behavior_count'], 500)
        self.assertFalse(value['platform_qualification_established_by_this_campaign'])
        self.assertNotIn('alloydb_platform_qualified', value)
        auth, events, terminal, key = next(row for row in entries if row[0]['campaign_id'] == engine.CAMPAIGN and row[2]['status'] == 'passed-bounded-native')
        broken = copy.deepcopy(events)
        broken[0]['payload']['message'] = 'tampered'
        with self.assertRaises(ValueError):
            coverage.admitted(ROOT, auth, broken, terminal, key)
        wrong_binding = copy.deepcopy(auth)
        wrong_binding['plan']['cases'][0]['oracle_sql_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            coverage.admitted(ROOT, wrong_binding, events, terminal, key)

    def fixture(self):
        fixture = core.Core100Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        path = fixture.root / coverage.BASELINE
        path.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / coverage.BASELINE, path)
        return fixture

    def test_simulation_is_excluded_and_missing_journal_is_unknown(self):
        fixture = self.fixture()
        run, _ = fixture.run_suite()
        value = coverage.report(fixture.root)
        self.assertEqual(value['oracle26ai_executed_case_count'], 0)
        self.assertEqual(value['alloydb_equivalent_case_count'], 0)
        self.assertEqual(value['excluded_simulated_or_unclassified_runs'], 1)
        path = engine.run_path(fixture.root, run) / 'families/char/events.sqlite3'
        path.unlink()
        invalid = coverage.report(fixture.root)
        self.assertEqual(invalid['status'], 'unavailable')
        self.assertIsNone(invalid['oracle26ai_executed_case_count'])

    def test_deduplication_and_latest_failure_override(self):
        # Exercise aggregation separately from admission: fabricated results are
        # deliberately never signed, stored or presented as native observations.
        cases = suite.cases(ROOT)
        def result(selected, fail=False):
            rows = []
            for c in selected:
                source, target = suite.expected(c, 'oracle'), suite.expected(c, 'alloydb')
                if fail and c['id'] == cases[0]['id']:
                    source = {**source, 'canonical': 'deliberate failure'}
                rows.append({'case_id': c['id'], 'oracle': source, 'alloydb': target,
                             'comparison': suite.compare(c, source, target)})
            return {'case_results': rows}
        old = {'run_id': 'old', 'campaign_id': engine.CAMPAIGN, 'authorized_at': '2026-01-01T00:00:00+00:00'}
        new = {'run_id': 'new', 'campaign_id': suite.CAMPAIGN, 'authorized_at': '2026-01-02T00:00:00+00:00'}
        entries = [(old, [], {}, b''), (new, [], {}, b'')]
        with patch.object(coverage, 'admitted', side_effect=[result(cases[:20]), result(cases)]):
            value = coverage.project(ROOT, entries)
        self.assertEqual(value['oracle26ai_executed_case_count'], 100)
        self.assertEqual(value['alloydb_equivalent_case_count'], 100)
        self.assertEqual(value['alloydb_equivalent_behavior_count'], 25)
        with patch.object(coverage, 'admitted', side_effect=[result(cases[:20]), result(cases, fail=True)]):
            value = coverage.project(ROOT, entries)
        self.assertEqual(value['oracle26ai_executed_case_count'], 100)
        self.assertEqual(value['oracle26ai_verified_case_count'], 99)
        self.assertEqual(value['alloydb_equivalent_case_count'], 99)
        self.assertEqual(value['alloydb_equivalent_behavior_count'], 24)

    def test_100_plus_260_are_260_and_later_simulation_cannot_replace_native(self):
        from lightyear_workflow import paired_types260 as expanded
        def result(selected):
            return {'case_results': [dict(case_id=c['id'], oracle=expanded.expected(c, 'oracle'),
                                         alloydb=expanded.expected(c, 'alloydb'),
                                         comparison=expanded.compare(c, expanded.expected(c, 'oracle'), expanded.expected(c, 'alloydb')))
                                    for c in selected]}
        entries = [({'run_id': name, 'campaign_id': campaign, 'authorized_at': f'2026-01-0{day}T00:00:00+00:00'}, [], {}, b'')
                   for day, name, campaign in ((1, 'old', suite.CAMPAIGN), (2, 'expanded', expanded.CAMPAIGN), (3, 'simulation', expanded.CAMPAIGN))]
        # Aggregation-only fixtures: no fabricated native signatures or receipts.
        with patch.object(coverage, 'admitted', side_effect=[result(suite.cases(ROOT)), result(expanded.cases(ROOT)), None]):
            value = coverage.project(ROOT, entries)
        self.assertEqual(value['oracle26ai_executed_case_count'], 260)
        self.assertEqual(value['alloydb_equivalent_case_count'], 260)
        self.assertEqual(value['alloydb_equivalent_behavior_count'], 65)
        self.assertEqual(value['excluded_simulated_or_unclassified_runs'], 1)


if __name__ == '__main__':
    unittest.main()
