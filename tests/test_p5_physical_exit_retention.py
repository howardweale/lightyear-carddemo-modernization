"""CI-only original component-journal retention, without admission or signing."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import canonical_hash
from tools.ci import p5_physical_exit_retention as probe


class PhysicalExitRetentionTests(unittest.TestCase):
    def rows(self, modes):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        result = []
        with tempfile.TemporaryDirectory() as temp:
            repository = Path(__file__).resolve().parents[1]
            for mode in modes:
                directory = Path(temp)/mode
                row = probe.observe(repository, directory, mode)
                for name, retained in row['documents'].items():
                    self.assertEqual((directory/name).read_bytes(), retained['utf8'].encode('utf-8'))
                result.append(row)
        return result

    def test_all_component_exit_journals_remain_verifiable_after_directory_removal(self):
        for row in self.rows(probe.MODES):
            with self.subTest(mode=row['mode']):
                self.assertTrue(probe.validate(row))
                self.assertFalse(row['production_controller_receipt'])
                self.assertFalse(row['admission_verified'])
                self.assertFalse(row['signing'])
                self.assertEqual(row['real_model_calls'], 0)

    def test_modified_original_bytes_and_false_authority_claims_are_rejected(self):
        row = self.rows(['generation-send'])[0]
        variants = []
        for field, value in [('exit_code', 0), ('mode', 'normal'), ('synthetic_identity_sha256', 'b'*64),
                             ('production_controller_receipt', True), ('admission_verified', True),
                             ('signing', True), ('real_model_calls', 1)]:
            bad = copy.deepcopy(row); bad[field] = value; variants.append(bad)
        for filename in row['documents']:
            bad = copy.deepcopy(row); bad['documents'][filename]['utf8'] += ' '; variants.append(bad)
        bad = copy.deepcopy(row); bad['documents']['unexpected.json'] = dict(utf8='{}', sha256=hashlib.sha256(b'{}').hexdigest()); variants.append(bad)
        bad = copy.deepcopy(row); bad['replayed_accounting']['billing_final'] = True; variants.append(bad)
        for bad in variants:
            with self.assertRaisesRegex(ValueError, 'p5-physical-retention-invalid'): probe.validate(bad)

    def test_rehashed_send_mismatch_and_duplicate_json_keys_are_rejected(self):
        row = self.rows(['generation-send'])[0]
        variants = []
        bad = copy.deepcopy(row)
        sends = [json.loads(line) for line in bad['documents']['stub-sends.jsonl']['utf8'].splitlines()]
        sends[-1]['request_sha256'] = '0'*64
        raw = ''.join(json.dumps(item)+'\n' for item in sends).encode()
        bad['documents']['stub-sends.jsonl'] = dict(utf8=raw.decode(), sha256=hashlib.sha256(raw).hexdigest()); variants.append(bad)
        bad = copy.deepcopy(row)
        raw = bad['documents']['attempt.jsonl']['utf8'].encode()
        events = raw.splitlines(keepends=True)
        first = json.loads(events[0]); duplicate = ('{"sequence":'+str(first['sequence'])+',').encode()+events[0][1:]
        raw = duplicate+b''.join(events[1:])
        bad['documents']['attempt.jsonl'] = dict(utf8=raw.decode(), sha256=hashlib.sha256(raw).hexdigest()); variants.append(bad)
        bad = copy.deepcopy(row)
        events = [json.loads(line) for line in bad['documents']['attempt.jsonl']['utf8'].splitlines()]
        events[0]['payload']['protocol'] = 4
        previous = None
        for event in events:
            event['previous_sha256'] = previous; event['event_sha256'] = canonical_hash(event, {'event_sha256'}); previous = event['event_sha256']
        raw = ''.join(json.dumps(item)+'\n' for item in events).encode()
        bad['documents']['attempt.jsonl'] = dict(utf8=raw.decode(), sha256=hashlib.sha256(raw).hexdigest()); variants.append(bad)
        for bad in variants:
            with self.assertRaisesRegex(ValueError, 'p5-physical-retention-invalid'): probe.validate(bad)

    def test_non_ci_and_unknown_mode_refuse_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'unused'
            for flag, mode in [('false', 'normal'), ('true', 'unknown')]:
                with patch.dict(os.environ, {'GITHUB_ACTIONS': flag}):
                    with self.assertRaisesRegex(ValueError, 'p5-physical-retention-ci-only'):
                        probe.observe(Path(temp), path, mode)
                self.assertFalse(path.exists())

    def test_child_timeout_and_wrong_exit_retain_diagnostics_without_pass(self):
        import base64
        import subprocess
        from types import SimpleNamespace
        repository = Path(__file__).resolve().parents[1]
        definitions = {'PhysicalCountGenerationExitTests': SimpleNamespace(CHILD='unused')}
        cases = [('timeout', subprocess.TimeoutExpired(['public-child'], 60, output=b'partial', stderr=b'timed'),
                  'p5-physical-retention-child-timeout', None, b'partial', b'timed'),
                 ('wrong-exit', subprocess.CompletedProcess(['public-child'], 3, b'out', b'failed'),
                  'p5-physical-retention-child-exit', 3, b'out', b'failed')]
        with tempfile.TemporaryDirectory() as temp:
            for name, outcome, reason, code, stdout, stderr in cases:
                directory = Path(temp)/name
                option = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
                with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), \
                        patch.object(probe.runpy, 'run_path', return_value=definitions), \
                        patch.object(probe.subprocess, 'run', **option):
                    with self.assertRaisesRegex(ValueError, reason): probe.observe(repository, directory, 'normal')
                diagnostic = json.loads((directory/'child-result.json').read_bytes())
                self.assertEqual(diagnostic['exit_code'], code)
                self.assertEqual(diagnostic['status'], 'timed-out' if name == 'timeout' else 'completed')
                for key, raw in [('stdout', stdout), ('stderr', stderr)]:
                    self.assertEqual(base64.b64decode(diagnostic[key]['base64'], validate=True), raw)
                    self.assertEqual(diagnostic[key]['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertFalse((directory/'attempt.jsonl').exists())

    def test_replayed_accounting_preserves_json_types_after_rehash(self):
        row = self.rows(['normal'])[0]
        original = copy.deepcopy(row)
        self.assertTrue(probe.validate(row))
        fields = ('billing_final', 'calls', 'input_tokens', 'output_tokens', 'duration_ms')
        for field in fields:
            wrong = copy.deepcopy(row)
            old = wrong['replayed_accounting'][field]
            replacement = 0 if field == 'billing_final' else float(old)
            self.assertEqual(old, replacement)
            self.assertIsNot(type(old), type(replacement))
            wrong['replayed_accounting'][field] = replacement
            self.assertEqual(wrong['documents'], row['documents'])
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.validate(wrong)
        self.assertEqual(row, original)
        self.assertTrue(probe.validate(row))
