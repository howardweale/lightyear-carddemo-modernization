"""Real disposable controller evidence and synthetic corruption controls, CI only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import canonical_hash
from tools.ci.p5_controller_evidence import validate
from tools.ci.p5_controller_outage import observe
from tools.ci import p5_drills as drills


class ControllerEvidenceTests(unittest.TestCase):
    def test_real_outage_retention_and_corruption_refusals(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        with tempfile.TemporaryDirectory(prefix='p5-retention-ci-') as temp:
            row = observe(Path(temp)/'controller', Path(__file__).resolve().parents[1])
            evidence = row['retained_controller_evidence']
            original = (Path(temp)/'controller/runs'/evidence['run_id']/'receipt.json').read_bytes()
            self.assertEqual(evidence['receipt_utf8'].encode('utf-8'), original)
            self.assertEqual(evidence['receipt_sha256'], row['receipt_bytes_sha256'])
        # Verification survives destruction of the disposable run directory.
        args = dict(run_id=evidence['run_id'], work_order_sha256=evidence['work_order_sha256'])
        self.assertTrue(validate(evidence, **args))
        for name in ('receipt_utf8', 'identity_utf8', 'nonce_after_sha256',
                     'attempt_files_after', 'duplicate_transport_calls'):
            bad = copy.deepcopy(evidence)
            if name.endswith('_utf8'):
                bad[name] += ' '
            elif name == 'attempt_files_after':
                bad[name]['receipt.json'] = '0'*64
            elif name == 'duplicate_transport_calls':
                bad[name] = 1
            else:
                bad[name] = '0'*64
            with self.subTest(field=name), self.assertRaises(ValueError):
                validate(bad, **args)
        for field in ('attempt_id', 'work_order_sha256', 'consumed_nonce_sha256'):
            bad = copy.deepcopy(evidence)
            identity = json.loads(bad['identity_utf8'])
            identity[field] = 'another-attempt' if field == 'attempt_id' else '0'*64
            identity['content_sha256'] = canonical_hash(identity, {'content_sha256'})
            bad['identity_utf8'] = json.dumps(identity, sort_keys=True)
            digest = hashlib.sha256(bad['identity_utf8'].encode()).hexdigest()
            bad['identity_sha256'] = digest
            for name in ('attempt_files_before', 'attempt_files_after'):
                bad[name]['attempt-identity.json'] = digest
            with self.subTest(swapped=field), self.assertRaises(ValueError):
                validate(bad, **args)

    def test_collector_retains_nested_controller_evidence_without_qualification(self):
        # Wiring control only. The separate integration test above uses the real controller.
        class FakeFixture:
            def __init__(self, parent, repository):
                self.envelope = {'signature': {'value': 'fixture'}}
                self.service = type('Service', (), {'public_key': b'fixture-not-a-key'})()
            def verify_order(self, envelope):
                raise drills.ExecutionContractError('synthetic corrupt signature')
            def signed_observation(self, body): return body
            def close(self): pass
        retained = {'receipt_utf8': 'exact synthetic bytes\n', 'identity_utf8': 'identity bytes\n'}
        def measured(fixture):
            return {'controller_outage': {'retained_controller_evidence': retained}}, True, ['unmeasured append recovery']
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}):
            root = Path(temp)/'output'
            with patch.object(drills, 'Fixture', FakeFixture), patch.object(drills, 'FUNCTIONS',
                    {name: measured for name in drills.DRILLS}):
                self.assertTrue(drills.collect(Path(__file__).resolve().parents[1], root))
            for name in drills.DRILLS:
                receipt = json.loads((root/(name+'.json')).read_bytes())
                self.assertEqual(receipt['observed']['controller_outage']['retained_controller_evidence'], retained)
                self.assertFalse(receipt['production_controller_receipt'])
                self.assertEqual(receipt['gaps'], ['unmeasured append recovery'])
                self.assertIn('tools/ci/p5_controller_outage.py', receipt['source_sha256'])
            with patch.object(drills, 'verify_envelope', return_value=True):
                self.assertFalse(drills.qualify(root))
