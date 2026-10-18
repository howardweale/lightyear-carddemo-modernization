import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

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

    def test_historical_assessment_does_not_depend_on_current_source_presence(self):
        # Files added by later policy implementation must not rewrite a dated receipt.
        with patch.object(Path, "is_file", side_effect=AssertionError("live source probe")):
            value, _ = build(ROOT, "2026-10-15")
        retained = json.loads((ROOT / "docs/factory/intcalc-releasability-2026-10-15.json").read_bytes())
        self.assertEqual(retained, value)

    def test_acceptance_bytes_are_pinned_before_source_fields_are_trusted(self):
        original=Path.read_bytes
        def changed(path):
            data=original(path)
            return data+b' ' if path.name=='equivalence-operator-acceptance-2026-10-12.json' else data
        with patch.object(Path,'read_bytes',changed),self.assertRaisesRegex(ValueError,'operator-acceptance-file-hash'):
            build(ROOT,'2026-10-15')

    def test_new_assessment_preserves_historical_evidence_and_names_missing_catches(self):
        value,text=build(ROOT,'2026-10-15',prepared_on='2026-10-17')
        self.assertEqual('2026-10-17',value['prepared_on'])
        self.assertEqual('intcalc-releasability-2026-10-15.json',value['supersedes'])
        self.assertEqual(3,len(value['missing_caught_constant_fields']))
        self.assertNotIn('P1 must land',text)
        self.assertIn('7 fields:',text)
        self.assertFalse(value['release_authorized'])
