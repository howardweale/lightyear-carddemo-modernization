from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_knowledge_graph.model import load_graph

from lightyear_extensions.pli_proof import build_proof, validate_development_receipt


ROOT = Path(__file__).resolve().parents[2]


class PliModernizationProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_graph(ROOT / "knowledge/graph.snapshot.json.gz")
        cls.fragment = json.loads(
            (ROOT / "extensions/pli/pli.fragment.json").read_text(encoding="utf-8")
        )

    def test_committed_proof_is_deterministic_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            receipt = build_proof(ROOT, self.graph, self.fragment, generated)
            canonical = ROOT / "extensions/pli/modernization"
            for expected in canonical.glob("*.json"):
                self.assertEqual(expected.read_bytes(), (generated / expected.name).read_bytes())
            self.assertEqual([], validate_development_receipt(receipt, ROOT, self.graph, self.fragment))
            self.assertTrue(receipt["development_ready"])
            self.assertFalse(receipt["mainframe_equivalent"])
            self.assertFalse(receipt["production_ready"])

    def test_every_behavior_case_matches_and_every_mutation_is_detected(self) -> None:
        comparison = json.loads(
            (ROOT / "extensions/pli/modernization/comparison.json").read_text(encoding="utf-8")
        )
        self.assertEqual(7, len(comparison["case_results"]))
        self.assertTrue(all(item["equivalent"] for item in comparison["case_results"]))
        self.assertEqual(9, len(comparison["mutation_results"]))
        self.assertTrue(all(item["detected"] for item in comparison["mutation_results"]))

    def test_source_pins_decimal_and_cobol_calling_semantics(self) -> None:
        source = (ROOT / "extensions/pli/reference/ACCTPL1.pli").read_text(encoding="utf-8")
        self.assertIn("ENTRY OPTIONS(COBOL)", source)
        self.assertIn("CALL CBACT04C(EXTERNAL_PARMS)", source)
        self.assertIn("DIVIDE(AMOUNT, 100, 5, 2)", source)
        self.assertIn("PARM_LENGTH FIXED BINARY(15) INIT(10)", source)

    def test_receipt_tamper_and_live_overclaim_are_rejected(self) -> None:
        receipt = json.loads(
            (ROOT / "extensions/pli/modernization/development.receipt.json").read_text(encoding="utf-8")
        )
        for key, value in (
            ("mainframe_equivalent", True),
            ("production_ready", True),
        ):
            with self.subTest(key=key):
                changed = copy.deepcopy(receipt)
                changed[key] = value
                self.assertTrue(validate_development_receipt(changed, ROOT, self.graph, self.fragment))
        changed = copy.deepcopy(receipt)
        changed["bindings"]["canonical_graph_sha256"] = "0" * 64
        self.assertTrue(validate_development_receipt(changed, ROOT, self.graph, self.fragment))

    def test_java_candidate_is_independent_and_ci_tested(self) -> None:
        source = (ROOT / "candidate-java/src/main/java/ai/lightyear/carddemo/service/MixedPliAuthorizationService.java").read_text(encoding="utf-8")
        test = (ROOT / "candidate-java/src/test/java/ai/lightyear/carddemo/service/MixedPliAuthorizationServiceTest.java").read_text(encoding="utf-8")
        self.assertIn("RoundingMode.DOWN", source)
        self.assertIn('COBOL_PROGRAM = "CBACT04C"', source)
        self.assertIn("SQL_NOT_FOUND", source)
        self.assertIn("overwritesSelectedFieldsCalculatesRiskAndInvokesCobolOnce", test)
        self.assertIn("invalidAndMissingRowsFailBeforeTheCobolBoundaryOrWrite", test)


if __name__ == "__main__":
    unittest.main()
