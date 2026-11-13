"""Synthetic report-policy tests; real signatures are checked by the CI drill job."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_control_tower.decisions import canonical
from tools.ci import p5_drills as drills


class P5ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = []
        for name in drills.DRILLS:
            body = dict(id=name, expected=drills.EXPECTED[name], expectation_met=True, gaps=[], production_controller_receipt=True)
            raw = canonical(body)
            (self.root / (name + '.json')).write_bytes(raw)
            (self.root / (name + '.public.pem')).write_bytes(b'synthetic-report-fixture-not-a-key')
            self.rows.append(dict(id=name, expectation_met=True, gaps=[], harness_error=False,
                                 receipt_sha256=hashlib.sha256(raw).hexdigest()))
        self.save()

    def save(self):
        (self.root / 'summary.json').write_bytes(canonical(dict(schema='p5-drills/1', complete=True, drills=self.rows)))

    def test_exact_inventory_and_missing_duplicate_extra_refusal(self):
        self.assertTrue(drills.inventory_ok(self.rows))
        self.assertFalse(drills.inventory_ok(self.rows[:-1]))
        self.assertFalse(drills.inventory_ok(self.rows + [self.rows[0]]))
        rows = copy.deepcopy(self.rows)
        rows[-1]['id'] = rows[0]['id']
        self.assertFalse(drills.inventory_ok(rows))
        rows[-1]['id'] = '../../outside'
        self.assertFalse(drills.inventory_ok(rows))

    def test_policy_positive_fixture_checks_every_signature(self):
        with patch.object(drills, 'verify_envelope', return_value=True) as verifier:
            self.assertTrue(drills.qualify(self.root))
        self.assertEqual(8, verifier.call_count)

    def test_invalid_signature_blocks_qualification(self):
        with patch.object(drills, 'verify_envelope', return_value=False):
            self.assertFalse(drills.qualify(self.root))

    def test_receipt_bytes_cannot_change_after_measurement(self):
        path = self.root / (drills.DRILLS[0] + '.json')
        path.write_bytes(path.read_bytes() + b' ')
        with patch.object(drills, 'verify_envelope', return_value=True):
            self.assertFalse(drills.qualify(self.root))

    def test_summary_cannot_conceal_a_signed_gap(self):
        name = drills.DRILLS[0]
        path = self.root / (name + '.json')
        body = json.loads(path.read_bytes())
        body['gaps'] = ['missing controller receipt']
        raw = canonical(body)
        path.write_bytes(raw)
        self.rows[0]['receipt_sha256'] = hashlib.sha256(raw).hexdigest()
        self.save()
        with patch.object(drills, 'verify_envelope', return_value=True):
            self.assertFalse(drills.qualify(self.root))

    def test_observer_receipt_is_not_a_controller_receipt(self):
        path = self.root / (drills.DRILLS[0] + '.json')
        body = json.loads(path.read_bytes())
        body['production_controller_receipt'] = False
        raw = canonical(body)
        path.write_bytes(raw)
        self.rows[0]['receipt_sha256'] = hashlib.sha256(raw).hexdigest()
        self.save()
        with patch.object(drills, 'verify_envelope', return_value=True):
            self.assertFalse(drills.qualify(self.root))

    def test_harness_error_and_failed_expectation_block(self):
        self.rows[0]['harness_error'] = True
        self.save()
        with patch.object(drills, 'verify_envelope', return_value=True):
            self.assertFalse(drills.qualify(self.root))
        self.rows[0]['harness_error'] = False
        self.rows[0]['expectation_met'] = False
        self.save()
        with patch.object(drills, 'verify_envelope', return_value=True):
            self.assertFalse(drills.qualify(self.root))

    def test_non_ci_collection_refuses_before_output_creation(self):
        target = self.root / 'must-not-exist'
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaisesRegex(ValueError, 'p5-ci-or-exclusive-output'):
                drills.collect(self.root, target)
        self.assertFalse(target.exists())
