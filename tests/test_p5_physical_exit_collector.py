"""CI-only collector integration; retained component evidence grants no authority."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import canonical_hash
from tools.ci import p5_physical_exit_collector as collector
from tools.ci import p5_physical_exit_retention as probe


class PhysicalExitCollectorTests(unittest.TestCase):
    def test_seven_real_component_exits_retain_originals_and_source_pins(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'retained'
            self.assertTrue(collector.collect(repository, output))
            report = json.loads((output/'observations.json').read_bytes())
            for name, document in report['original_documents'].items():
                raw = (output/name).read_bytes()
                self.assertEqual(raw, base64.b64decode(document['base64'], validate=True))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), document['sha256'])
                self.assertEqual(len(raw), document['bytes'])
        self.assertEqual([row['mode'] for row in report['cases']], list(probe.MODES))
        self.assertEqual(report['content_sha256'], canonical_hash(report, {'content_sha256'}))
        for name in collector.SOURCES:
            self.assertEqual(report['source_sha256'][name],
                             hashlib.sha256((repository/name).read_bytes()).hexdigest())
        self.assertTrue(report['expectations_met'])
        for field in ('strict_qualified', 'production_controller_receipt', 'admission_verified', 'signing'):
            self.assertIs(report[field], False)
        self.assertEqual(report['real_model_calls'], 0)
        self.assertEqual(len(report['gaps']), 2)
        for row in report['cases']:
            self.assertTrue(row['expectation_met'])
            self.assertTrue(probe.validate(row['observed']))
            for name, retained in row['observed']['documents'].items():
                original = report['original_documents'][row['mode']+'/'+name]
                self.assertEqual(base64.b64decode(original['base64']), retained['utf8'].encode())
                self.assertEqual(original['sha256'], retained['sha256'])

    def test_failed_children_retain_diagnostics_and_do_not_skip_later_modes(self):
        repository = Path(__file__).resolve().parents[1]
        payload = b'{"status":"synthetic failure"}\n'
        def fail(repository, directory, mode):
            directory.mkdir(parents=True)
            (directory/'child-result.json').write_bytes(payload)
            raise ValueError('deliberate-child-failure:'+mode)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), \
                patch.object(probe, 'observe', side_effect=fail) as observed:
            output = Path(temp)/'retained'
            self.assertFalse(collector.collect(repository, output))
            report = json.loads((output/'observations.json').read_bytes())
        self.assertEqual([call.args[2] for call in observed.call_args_list], list(probe.MODES))
        self.assertEqual(len(report['cases']), 7)
        self.assertFalse(report['expectations_met'])
        self.assertFalse(report['strict_qualified'])
        for row in report['cases']:
            self.assertFalse(row['expectation_met'])
            self.assertIn('deliberate-child-failure', row['harness_error'])
            raw = base64.b64decode(report['original_documents'][row['mode']+'/child-result.json']['base64'])
            self.assertEqual(raw, payload)

    def test_non_ci_and_existing_output_refuse_before_child_execution(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(probe, 'observe') as observed:
            output = Path(temp)/'new'
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
                with self.assertRaisesRegex(ValueError, 'ci-exclusive-output'):
                    collector.collect(Path(temp), output)
            self.assertFalse(output.exists())
            output.mkdir()
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}):
                with self.assertRaisesRegex(ValueError, 'ci-exclusive-output'):
                    collector.collect(Path(temp), output)
            observed.assert_not_called()

    def test_normal_originals_cannot_substitute_for_requested_interruption_modes(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            original = probe.observe(repository, Path(temp)/'normal-original', 'normal')
            self.assertTrue(probe.validate(original))
            def substitute(repository, directory, mode):
                directory.mkdir(parents=True)
                for name, document in original['documents'].items():
                    (directory/name).write_bytes(document['utf8'].encode())
                return original
            output = Path(temp)/'substituted'
            with patch.object(probe, 'observe', side_effect=substitute) as observed:
                self.assertFalse(collector.collect(repository, output))
            report = json.loads((output/'observations.json').read_bytes())
            self.assertEqual([call.args[2] for call in observed.call_args_list], list(probe.MODES))
            self.assertEqual([row['mode'] for row in report['cases']], list(probe.MODES))
            self.assertIs(report['expectations_met'], False)
            self.assertIs(report['strict_qualified'], False)
            self.assertEqual(report['content_sha256'], canonical_hash(report, {'content_sha256'}))
            for row in report['cases']:
                self.assertNotIn('harness_error', row)
                self.assertNotIn('retention_errors', row)
                self.assertIs(row['expectation_met'], row['mode'] == 'normal')
                self.assertEqual(row['observed'], original)
                self.assertTrue(probe.validate(row['observed']))
                for name, document in original['documents'].items():
                    raw = document['utf8'].encode()
                    retained = report['original_documents'][row['mode']+'/'+name]
                    self.assertEqual(base64.b64decode(retained['base64'], validate=True), raw)
                    self.assertEqual(retained['sha256'], hashlib.sha256(raw).hexdigest())
                    self.assertEqual(retained['bytes'], len(raw))
