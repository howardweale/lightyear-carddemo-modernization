import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.build_intcalc_releasability import ROOT, build


class ReleasabilityTests(unittest.TestCase):
    def test_report_matches_retained_receipts_and_does_not_waive_constants(self):
        value, text = build(ROOT, "2026-10-15")
        retained = json.loads((ROOT / "docs/factory/intcalc-releasability-2026-10-15.json").read_bytes())
        self.assertEqual(retained, value)
        self.assertEqual(len(value["raw_evidence_gap_ids"]), value["loader_domain"]["assessment_counts"]["resolved-by-valid-comparisons"])
        self.assertEqual([], value["remaining_evidence_gaps"])
        self.assertFalse(value["release_authorized"])
        self.assertEqual("still fails unchanged threshold/2", next(r for r in value["criteria"] if r["name"] == "Output diversity")["after_signatures"])
        self.assertTrue(text.rstrip().splitlines()[-1].startswith("Not releasable:"))

    def test_tampered_receipt_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = "docs/factory/release-evidence-2026-10-15"
            shutil.copytree(ROOT / path, root / path)
            receipt = root / path / "aggregate/INTCALC/threshold-2-by-scope.json"
            receipt.write_text("{}")
            with self.assertRaisesRegex(ValueError, "release-evidence-hash"):
                build(root, "2026-10-15")
