"""Offline diagnostic-tool tests, not native observer qualification."""
import base64
import hashlib
import json
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from lightyear_control_tower.decisions import canonical, digest
from lightyear_calibration.contracts import verify
from tools.ms94_b06_frame_census import binding, checked, generated_kind, required_r10, CANDIDATE


class FrameCensusTests(unittest.TestCase):
    def test_equal_method_does_not_hide_different_constant_pool(self):
        frame = {'class': 'engine.X', 'method': 'execute', 'signature': '()V',
                 'method_sha256': 'a' * 64, 'constant_pool_sha256': 'b' * 64}
        classes = {'engine.X': {'methods': {'execute()V': 'a' * 64}, 'constant_pool_sha256': 'c' * 64}}
        self.assertEqual(binding(frame, classes), 'BOUND-BUT-MISMATCH')
        frame['constant_pool_sha256'] = 'c' * 64
        self.assertEqual(binding(frame, classes), 'BOUND-MATCH')

    def test_unbound_ignored_frame_still_reported(self):
        frame = {'class': 'java.lang.reflect.Method', 'method': 'invoke', 'signature': '()V'}
        self.assertFalse(required_r10(frame['class'], {}))
        self.assertEqual(binding(frame, {}), 'UNBOUND')

    def test_generated_name_is_not_a_byte_binding(self):
        for name in (CANDIDATE + '$$Lambda/0x123', 'org.junit.SomeType$$Lambda/0x456'):
            self.assertEqual(generated_kind(name), 'lambda/hidden-name')
            self.assertTrue(required_r10(name, {}))
            self.assertEqual(binding({'class': name}, {}), 'UNBOUND')

    def test_static_vendor_name_is_not_proof_of_runtime_generation(self):
        for name in ('oracle.jdbc.driver.GeneratedResultSet', 'com.zaxxer.hikari.pool.HikariProxyResultSet'):
            self.assertIsNone(generated_kind(name))
        self.assertEqual(generated_kind('java.lang.invoke.LambdaForm$MH/0x123'), 'hidden-name')
        self.assertEqual(generated_kind('jdk.proxy2.$Proxy19'), 'proxy-name')
        self.assertEqual(generated_kind('jdk.internal.reflect.GeneratedMethodAccessor9'), 'reflection-accessor-name')

    def test_signed_envelope_validates_without_unsigned_hash_rule(self):
        key = Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        body = {'artifact_type': 'test-only', 'passed': False}
        record = {**body, 'content_sha256': digest(body), 'signature': {
            'algorithm': 'Ed25519', 'key_id': hashlib.sha256(public).hexdigest(),
            'value': base64.b64encode(key.sign(canonical(body))).decode('ascii')}}
        self.assertIs(checked(record, public), record)
        record['passed'] = True
        with self.assertRaises(ValueError):
            checked(record, public)

    def test_smoke_draft_cannot_claim_execution_or_reuse_failed_slot(self):
        base = Path(__file__).resolve().parents[1] / 'docs/calibration/idempiere-ms94/stage-b-06/preparation/r10-offline-diagnosis'
        draft = json.loads((base / 'j1-smoke-r11-draft.json').read_text(encoding='utf-8'))
        verify(draft)
        self.assertEqual(draft['artifact_type'], 'ms94-b06-smoke-preparation-draft/1')
        for field in ('docker_authorized', 'measurement_authorized', 'restarts_allowed', 'resume_allowed', 'replacement_slots_allowed'):
            self.assertIs(draft[field], False)
        for field in ('window', 'public_commit', 'snapshot_sha256', 'tower_decision_sha256'):
            self.assertIsNone(draft[field])
        self.assertEqual(len(set(s['native_run_id'] for s in draft['slots'])), 3)
        self.assertTrue(all(s['id'].startswith('j1-smoke-r11-') for s in draft['slots']))
        self.assertEqual(draft['amendment_file_sha256'], hashlib.sha256((base / 'observer-binding-amendment.md').read_bytes()).hexdigest())

    def test_published_inventory_keeps_mismatch_and_all_saved_methods(self):
        base = Path(__file__).resolve().parents[1] / 'docs/calibration/idempiere-ms94/stage-b-06/preparation/r10-offline-diagnosis'
        summary = json.loads((base / 'summary.json').read_text(encoding='utf-8'))
        rows = json.loads((base / 'observed-frames.json').read_text(encoding='utf-8'))
        for name, sha in summary['inventory_file_sha256'].items():
            self.assertEqual(hashlib.sha256((base / name).read_bytes()).hexdigest(), sha)
        for lane in ('oracle', 'postgresql'):
            frames = [r for r in rows if r['lane'] == lane and r['stack_occurrences']]
            self.assertEqual(len({(r['class'],r['method'],r['signature']) for r in frames}), summary['lanes'][lane]['methods'])
            bad = [r for r in frames if r['binding'] == 'BOUND-BUT-MISMATCH']
            self.assertEqual(len(bad), 1)
            self.assertIn('HierarchicalTestEngine', bad[0]['class'])
            self.assertFalse(summary['lanes'][lane]['full_observer_replay_passed'])


if __name__ == '__main__':
    unittest.main()
