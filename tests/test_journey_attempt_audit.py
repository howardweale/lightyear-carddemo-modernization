"""Published original plans make the unchanged-judge claim independently checkable."""
from pathlib import Path
import json
import shutil
import tempfile
import unittest
from tools.audit_journey_attempts import verify_audit

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'docs/calibration/idempiere-partial-invoicing/attempt-audit'


class AttemptAuditTests(unittest.TestCase):
    def test_original_attempts_bind_the_same_judge_and_expectations(self):
        result=verify_audit(AUDIT)
        self.assertEqual(4,result['native_attempts'])
        self.assertTrue(result['unchanged_expectations'])
        self.assertTrue(result['unchanged_acceptance'])

    def test_altering_a_published_judge_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'audit';shutil.copytree(AUDIT,folder)
            path=folder/'build-03/plan.json';value=json.loads(path.read_text())
            value['implementation_sha256']['src/lightyear_calibration/partial_invoicing.py']='f'*64
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):verify_audit(folder)


if __name__=='__main__':unittest.main()
