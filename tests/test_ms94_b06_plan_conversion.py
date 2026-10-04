"""A signed failed host probe must never turn a draft into an executable plan."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, seal, CalibrationError
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_qualification_plan import convert


class ConversionTests(unittest.TestCase):
    def test_missing_snapshot_and_failed_signed_probe_cannot_promote_draft(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); signer = test_signer(); draft = seal({'journey': 'J1'})
            with self.assertRaises(CalibrationError):
                convert(root, draft, 'missing', '', '', public_key=signer.public, transport={}, probe_binding={})
            (root / 'blocked.json').write_bytes(canonical(signer.sign({
                'artifact_type': 'ms94-b06-os-builder-denial/1', 'status': 'blocked-before-child'})))
            binding = {'path': 'blocked.json', 'sha256': file_hash(root / 'blocked.json')}
            with patch('tools.ms94_b06_qualification_plan.verify_snapshot', return_value={}), self.assertRaisesRegex(
                    ValueError, 'builder-filesystem-denial-not-demonstrated'):
                convert(root, draft, 'snapshot', '', '', public_key=signer.public, transport={}, probe_binding=binding)


if __name__ == '__main__': unittest.main()
