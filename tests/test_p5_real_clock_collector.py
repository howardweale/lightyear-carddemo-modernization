"""CI-only collector evidence; no signatures or admission fixtures."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.ci import p5_real_clock_collector as collector


ROOT = Path(__file__).resolve().parents[1]


class RealClockCollectorTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_actual_clock_observations_retain_original_receipt_and_ledger(self):
        retained = []
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'collected'
            report = collector.collect(ROOT, output)
            self.assertTrue(report['complete'])
            self.assertEqual([row['id'] for row in report['cases']], ['clean', 'expired'])
            self.assertEqual(json.loads((output/'report.json').read_bytes()), report)
            for name, digest in report['source_sha256'].items():
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), digest)
            for row in report['cases']:
                self.assertTrue(row['expectation_met'])
                self.assertNotIn('harness_error', row)
                ref = row['observation']; raw = (output/ref['path']).read_bytes()
                self.assertEqual(len(raw), ref['bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
                observed = json.loads(raw)
                original = output/row['id']/'runs/p5-terminal-deadline'
                self.assertEqual(observed['receipt_utf8'].encode(), (original/'receipt.json').read_bytes())
                self.assertEqual(observed['ledger_utf8'].encode(), (original/'events.jsonl').read_bytes())
                self.assertEqual(observed['wall_seconds'], 30)
                retained.append(observed)
            for field in ('production_controller_receipt', 'strict_qualified', 'admission_verified', 'signing'):
                self.assertIs(report[field], False)
            self.assertEqual(report['real_model_calls'], 0)
            self.assertTrue(report['gaps'])
        for observed in retained:
            self.assertTrue(collector.probe.validate(observed))

    def test_failed_cases_are_retained_and_later_case_is_attempted(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'failed'
            with patch.object(collector.probe, 'observe', side_effect=[RuntimeError('public first failure'), RuntimeError('public second failure')]) as observed:
                report = collector.collect(ROOT, output)
            self.assertEqual(observed.call_count, 2)
            self.assertFalse(report['complete'])
            self.assertEqual([row['id'] for row in report['cases']], ['clean', 'expired'])
            self.assertTrue(all(row['expectation_met'] is False for row in report['cases']))
            self.assertTrue(all('harness_error' in row for row in report['cases']))
            self.assertEqual(json.loads((output/'report.json').read_bytes()), report)

    def test_non_ci_and_existing_output_refuse_before_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'uncreated'
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}), patch.object(collector.probe, 'observe') as observed:
                with self.assertRaisesRegex(ValueError, 'ci-exclusive-output'):
                    collector.collect(ROOT, output)
                observed.assert_not_called()
            self.assertFalse(output.exists())
            output.mkdir(); marker = output/'original'; marker.write_bytes(b'preserve')
            with patch.object(collector.probe, 'observe') as observed:
                with self.assertRaisesRegex(ValueError, 'ci-exclusive-output'):
                    collector.collect(ROOT, output)
                observed.assert_not_called()
            self.assertEqual(marker.read_bytes(), b'preserve')

    def test_invalid_returned_observations_survive_without_expectation_pass(self):
        invalid = [dict(schema='public-invalid-fixture', case='clean'),
                   dict(schema='public-invalid-fixture', case='expired')]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'invalid'
            with patch.object(collector.probe, 'observe', side_effect=invalid) as observed:
                report = collector.collect(ROOT, output)
            self.assertEqual(observed.call_count, 2)
            self.assertFalse(report['complete'])
            for row, original in zip(report['cases'], invalid):
                self.assertIs(row['expectation_met'], False)
                ref = row['observation']; raw = (output/ref['path']).read_bytes()
                self.assertEqual(json.loads(raw), original)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
                self.assertEqual(len(raw), ref['bytes'])
            self.assertFalse(report['strict_qualified'])
            self.assertEqual(json.loads((output/'report.json').read_bytes()), report)

    def test_valid_clean_observation_cannot_stand_in_for_expired_case(self):
        with tempfile.TemporaryDirectory() as temp:
            clean = collector.probe.observe(Path(temp)/'original-clean', False)
            self.assertTrue(collector.probe.validate(clean))
            output = Path(temp)/'substituted'
            with patch.object(collector.probe, 'observe', side_effect=[clean, clean]) as observed:
                report = collector.collect(ROOT, output)
            self.assertEqual(observed.call_count, 2)
            self.assertEqual([row['id'] for row in report['cases']], ['clean', 'expired'])
            self.assertIs(report['cases'][0]['expectation_met'], True)
            self.assertIs(report['cases'][1]['expectation_met'], False)
            self.assertIs(report['complete'], False)
            self.assertIs(report['strict_qualified'], False)
            for row in report['cases']:
                self.assertNotIn('harness_error', row)
                ref = row['observation']; raw = (output/ref['path']).read_bytes()
                self.assertEqual(json.loads(raw), clean)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
                self.assertEqual(len(raw), ref['bytes'])
            self.assertEqual(json.loads((output/'report.json').read_bytes()), report)
