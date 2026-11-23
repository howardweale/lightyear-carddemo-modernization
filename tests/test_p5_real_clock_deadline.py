"""CI-only real-clock observations; no signature, admission or qualification."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest

from lightyear_factory.contracts import canonical_hash
from tools.ci.p5_real_clock_deadline import observe, validate


class RealClockDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_real_clock_clean_and_expired_native_receipts(self):
        for expired in (False, True):
            with self.subTest(expired=expired):
                row = observe(self.root/str(expired), expired)
                self.assertTrue(validate(row))
                receipt = json.loads(row['receipt_utf8'])
                self.assertEqual(receipt['status'], 'blocked' if expired else 'passed')
                self.assertFalse(row['clock_substituted'])
                self.assertFalse(row['production_controller_receipt'])
                self.assertEqual(row['scripted_roles'], ['planner'])
                self.assertEqual(row['error'], 'Factory exceeded max_elapsed_seconds' if expired else None)
                self.assertEqual(len(row['gate_reports']), 1)
                gate = row['gate_reports'][0]['gates'][0]
                self.assertEqual(gate['status'], 'passed')
                self.assertEqual(gate['exit_code'], 0)
                self.assertIs(gate['timed_out'], False)

    def test_wrong_reason_clock_claim_interval_and_receipt_substitution_refuse(self):
        row = observe(self.root/'expired', True)
        self.assertTrue(validate(row))
        for field, value in (('error', 'unrelated refusal'), ('clock_substituted', True),
                              ('elapsed_seconds', 0), ('wall_seconds', True),
                              ('monotonic_finished', float('nan'))):
            changed = deepcopy(row); changed[field] = value
            with self.subTest(field=field): self.assertFalse(validate(changed))
        changed = deepcopy(row); changed['intervals'][0]['released'] = row['monotonic_started']
        self.assertFalse(validate(changed))
        changed = deepcopy(row); receipt = json.loads(changed['receipt_utf8'])
        receipt['status'] = 'passed'
        receipt['content_sha256'] = canonical_hash(receipt, {'content_sha256'})
        changed['receipt_utf8'] = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
        changed['receipt_sha256'] = sha256(changed['receipt_utf8'].encode()).hexdigest()
        self.assertFalse(validate(changed))


    def test_gate_already_expired_before_observer_wait_cannot_pass(self):
        row = observe(self.root/'late-gate', True)
        self.assertTrue(validate(row))
        deadline = row['monotonic_started'] + row['wall_seconds']
        self.assertLess(row['intervals'][0]['gate_returned'], deadline)
        self.assertGreaterEqual(row['intervals'][0]['released'], deadline)
        for gate_time in (deadline, deadline + 0.01):
            changed = deepcopy(row)
            changed['intervals'][0]['gate_returned'] = gate_time
            with self.subTest(gate_time=gate_time):
                self.assertFalse(validate(changed))
        self.assertTrue(validate(row))


if __name__ == '__main__': unittest.main()
