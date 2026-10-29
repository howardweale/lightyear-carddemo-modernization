"""Original configured component records; no authority, signature or model calls."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import canonical_hash
from tools.ci import p5_configured_exit_retention as probe

ROOT = Path(__file__).resolve().parents[1]


class ConfiguredExitRetentionTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_all_five_configured_exit_records_replay_after_original_directory_is_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            records = [probe.observe(ROOT, Path(temp)/mode, mode) for mode in probe.MODES]
            for value in records:
                for name, row in value['documents'].items():
                    self.assertEqual(base64.b64decode(row['base64']), (Path(temp)/value['mode']/name).read_bytes())
        for value in records:
            self.assertTrue(probe.validate(value))
            self.assertFalse(value['admission_verified'])
            self.assertFalse(value['production_controller_receipt'])
            self.assertFalse(value['strict_qualified'])

    def test_rehashed_send_mutation_replay_change_and_false_authority_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            value = probe.observe(ROOT, Path(temp)/'normal', 'normal')
        for field in ('admission_verified', 'production_controller_receipt', 'strict_qualified', 'signing'):
            wrong = copy.deepcopy(value); wrong[field] = True
            wrong['content_sha256'] = canonical_hash(wrong, {'content_sha256'})
            with self.assertRaises(ValueError): probe.validate(wrong)
        for change in ('tier', 'policy', 'unknown-field'):
            wrong = copy.deepcopy(value)
            config = json.loads(base64.b64decode(wrong['documents']['models.json']['base64']))
            model = config['models']['public-fixture']
            if change == 'tier': model['service_tier'] = 'standard'
            elif change == 'policy': model['billing_policy'] = {}
            else: model['unreviewed_option'] = True
            raw = json.dumps(config).encode()
            wrong['documents']['models.json'] = dict(base64=base64.b64encode(raw).decode(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            wrong['content_sha256'] = canonical_hash(wrong, {'content_sha256'})
            with self.assertRaises(ValueError): probe.validate(wrong)
        wrong = copy.deepcopy(value)
        wrong['replayed_accounting']['billing_final'] = True
        wrong['content_sha256'] = canonical_hash(wrong, {'content_sha256'})
        with self.assertRaises(ValueError): probe.validate(wrong)
        wrong = copy.deepcopy(value)
        rows = [json.loads(line) for line in base64.b64decode(wrong['documents']['stub-sends.jsonl']['base64']).splitlines()]
        rows[1]['request_sha256'] = '0'*64
        raw = ''.join(json.dumps(row)+'\n' for row in rows).encode()
        wrong['documents']['stub-sends.jsonl'] = dict(base64=base64.b64encode(raw).decode(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        wrong['content_sha256'] = canonical_hash(wrong, {'content_sha256'})
        with self.assertRaises(ValueError): probe.validate(wrong)

    def test_timeout_diagnostics_survive_and_existing_output_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'failed'
            error = subprocess.TimeoutExpired('public-component', 60, output=b'public-stdout', stderr=b'public-stderr')
            with patch.object(probe.subprocess, 'run', side_effect=error):
                with self.assertRaisesRegex(ValueError, 'configured-exit-retention-timeout'):
                    probe.observe(ROOT, output, 'normal')
            original = (output/'child-result.json').read_bytes()
            value = json.loads(original)
            self.assertEqual(value['status'], 'timed-out')
            self.assertEqual(base64.b64decode(value['stdout']['base64']), b'public-stdout')
            self.assertEqual(base64.b64decode(value['stderr']['base64']), b'public-stderr')
            with self.assertRaisesRegex(ValueError, 'exclusive-output'):
                probe.observe(ROOT, output, 'normal')
            self.assertEqual((output/'child-result.json').read_bytes(), original)
