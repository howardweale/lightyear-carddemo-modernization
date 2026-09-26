"""Check retained native evidence accounting, never manufacture execution claims."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from lightyear_calibration.contracts import read_json, verify
from lightyear_calibration.replay import write_summary

ROOT=Path(__file__).resolve().parents[1]/'docs/calibration/idempiere-runtime'


class NativePublicationTests(unittest.TestCase):
    def test_retained_files_and_counts_agree_with_native_comparisons(self):
        receipt=read_json(ROOT/'receipt.json');verify(receipt)
        for item in receipt['evidence_files']:
            path=ROOT/item['path']
            self.assertTrue(path.resolve().is_relative_to(ROOT.resolve()))
            self.assertEqual(item['sha256'],hashlib.sha256(path.read_bytes()).hexdigest(),item['path'])
        comparisons=[read_json(p) for p in sorted((ROOT/'evidence').glob('case-*/comparison.json'))]
        for comparison in comparisons:
            verify(comparison)
            self.assertFalse(comparison['application_equivalence'])
            self.assertTrue(comparison['registration_effects_retained'])
        stage=receipt['stage_two']
        self.assertEqual(stage['attempted_pairs'],len(comparisons))
        self.assertEqual(stage['native_script_executions'],sum(len(c['execution']) for c in comparisons))
        self.assertEqual(stage['strict_row_effects_differ_pairs'],sum(not c['row_effects_match'] for c in comparisons))
        self.assertEqual(stage['successful_client_pairs'],sum(all(e['returncode']==0 for e in c['execution'].values()) for c in comparisons))
        self.assertEqual(1078,stage['attempted_pairs']+stage['excluded']['already_registered_on_both']+
                         len(stage['excluded']['oracle_only_unregistered'])+len(stage['excluded']['post_migration_maintenance_not_executed']))
        final=read_json(ROOT/'evidence/final-checks.json');verify(final)
        self.assertEqual(stage['oracle_invalid_objects_after_tranche'],len(final['checks']['oracle']['invalid_objects']))

    def test_context_report_does_not_recount_previous_calibration_lift(self):
        measurement=read_json(ROOT/'evidence/stage-one-measurement.json');verify(measurement)
        self.assertEqual(0,measurement['context_lift_units'])
        self.assertEqual(2,measurement['schema_session_inventory']['complete_catalogs'])
        self.assertFalse(measurement['native_migration_execution'])
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);write_summary(measurement,output)
            self.assertIn('Native context lift: 0 additional decided units', (output/'report.md').read_text(encoding='utf-8'))
            html=(output/'index.html').read_text(encoding='utf-8')
            self.assertIn('780 → 780 decided SQL units',html)
            self.assertNotIn('produced 4 additional decisions',html)


if __name__=='__main__':unittest.main()
