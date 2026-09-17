"""Verify published native evidence offline; never provision or run a database."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from lightyear_control_tower.decisions import verify_envelope
from lightyear_data.contracts import content_hash
from lightyear_workflow.campaign_engine import checked_authorization, project

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / 'docs/receipts/oracle26ai-alloydb-number-20260917'


class PublishedCampaignTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('cryptography'), 'Dedicated signing CI installs .[control-tower]')
    def test_export_signatures_chain_and_comparator_replay(self):
        manifest = json.loads((EXPORT / 'manifest.json').read_text())
        key = (EXPORT / 'public-key.pem').read_bytes()
        self.assertEqual(hashlib.sha256(key).hexdigest(), '36fdf4766568b1880c1bddef92f450c6a41279d01ff11c0abd6f78e2215c6552')
        for name, expected in manifest['files'].items():
            path = (EXPORT / name).resolve()
            self.assertTrue(path.is_relative_to(EXPORT.resolve()))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, name)
        passed = []
        for name in manifest['files']:
            if not name.endswith('/authorization.json'):
                continue
            directory = EXPORT / Path(name).parent
            auth = json.loads((directory / 'authorization.json').read_text())
            checked_authorization(auth, key)
            events = json.loads((directory / 'journal.json').read_text())['events']
            previous = None
            for sequence, event in enumerate(events, 1):
                self.assertEqual(event['sequence'], sequence)
                self.assertEqual(event['previous_sha256'], previous)
                self.assertEqual(event['content_sha256'], content_hash(event))
                payload = event['payload']
                self.assertTrue(verify_envelope(payload, key))
                self.assertEqual(payload['run_id'], auth['run_id'])
                self.assertEqual(payload['plan_sha256'], auth['plan']['plan_sha256'])
                self.assertEqual(payload['previous_event_sha256'], previous)
                self.assertEqual(payload['event_type'], event['type'])
                previous = event['content_sha256']
            result = project(ROOT, auth, events)
            terminal = json.loads((directory / 'summary.json').read_text())
            self.assertTrue(verify_envelope(terminal, key))
            self.assertEqual(terminal['authorization_sha256'], auth['content_sha256'])
            self.assertEqual(terminal['journal_head_sha256'], previous)
            for field in ('status', 'source_completed', 'target_completed', 'matched', 'cleanup', 'evidence_class'):
                self.assertEqual(terminal[field], result[field])
            recovery = directory / 'recovery.json'
            effective = terminal
            if recovery.exists():
                effective = json.loads(recovery.read_text())
                self.assertTrue(verify_envelope(effective, key))
                self.assertEqual(effective['authorization_sha256'], auth['content_sha256'])
                self.assertEqual(effective['run_id'], auth['run_id'])
            self.assertTrue(effective['cleanup']['complete'])
            if result['status'] == 'passed-bounded-native':
                self.assertEqual(result['source_completed'], 20)
                self.assertEqual(result['target_completed'], 20)
                self.assertEqual(result['comparisons_completed'], 20)
                self.assertEqual(result['matched'], 20)
                passed.append(auth['run_id'])
        self.assertEqual(passed, [manifest['successful_run_id']])


if __name__ == '__main__':
    unittest.main()
