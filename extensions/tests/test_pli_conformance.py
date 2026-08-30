from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_extensions.pli import build_pli_fragment
from lightyear_extensions.pli_conformance import (
    build_conformance_lab,
    validate_conformance_receipt,
)
from lightyear_extensions.pli_frontend import parse_pli_source
from lightyear_knowledge_graph.model import load_graph


ROOT = Path(__file__).resolve().parents[2]
GRAPH = load_graph(ROOT / "knowledge" / "graph.snapshot.json.gz")
LAB = ROOT / "extensions" / "pli" / "conformance"
CORPUS = LAB / "corpus"
MANIFEST = CORPUS / "manifest.json"
MATRIX = LAB / "support-matrix.json"


class PliConformanceTests(unittest.TestCase):
    def build(self):
        return build_conformance_lab(GRAPH, CORPUS, MANIFEST, MATRIX, ROOT)

    def test_52_case_corpus_is_deterministic_and_matches_committed_evidence(self) -> None:
        first_golden, first_receipt = self.build()
        second_golden, second_receipt = self.build()
        self.assertEqual(first_golden, second_golden)
        self.assertEqual(first_receipt, second_receipt)
        self.assertEqual(52, first_receipt["corpus"]["case_count"])
        self.assertEqual(36, first_receipt["corpus"]["positive_case_count"])
        self.assertEqual(16, first_receipt["corpus"]["blocked_case_count"])
        self.assertEqual(22, first_receipt["coverage"]["supported_matrix_construct_count"])
        self.assertEqual("passed", first_receipt["status"])
        self.assertTrue(all(
            all("line" in item and "column" in item for item in result["recognized"])
            for result in first_golden["results"]
        ))
        self.assertEqual(
            first_golden,
            json.loads((LAB / "golden-results.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(
            first_receipt,
            json.loads((LAB / "coverage.receipt.json").read_text(encoding="utf-8")),
        )

    def test_comments_and_strings_cannot_create_false_calls_or_sql(self) -> None:
        source = (CORPUS / "20-comments-strings.pli").read_text(encoding="utf-8")
        parsed = parse_pli_source(source, "20-comments-strings.pli", include_names={"COMMON"})
        self.assertEqual("passed", parsed["status"])
        self.assertFalse(any(item["kind"] in {"call", "sql"} for item in parsed["references"]))

    def test_manifest_rejects_an_undeclared_source_file(self) -> None:
        undeclared = CORPUS / "UNDECLARED.pli"
        undeclared.write_text("UNDECLARED: PROC OPTIONS(MAIN); END UNDECLARED;\n", encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "exact source set"):
                self.build()
        finally:
            undeclared.unlink()

    def test_casing_spacing_and_continuation_lines_preserve_constructs(self) -> None:
        parsed = parse_pli_source(
            (CORPUS / "19-case-spacing-continuation.pli").read_text(encoding="utf-8"),
            "19-case-spacing-continuation.pli",
        )
        kinds = {item["kind"] for item in parsed["constructs"]}
        self.assertEqual("passed", parsed["status"])
        self.assertTrue({"program", "decimal_declaration", "assignment"}.issubset(kinds))
        self.assertEqual("MIXED19", parsed["program"])

    def test_embedded_sql_retains_normalized_lineage_text(self) -> None:
        parsed = parse_pli_source(
            (CORPUS / "09-sql-select.pli").read_text(encoding="utf-8"),
            "09-sql-select.pli",
        )
        sql = next(item for item in parsed["references"] if item["kind"] == "sql")
        self.assertEqual("CARDDEMO", sql["schema"])
        self.assertEqual("AUTHFRDS", sql["target"])
        self.assertIn("SELECT FRD_SCORE", sql["normalized_sql"])

    def test_missing_include_and_shadowed_call_are_explicit_blockers(self) -> None:
        missing = parse_pli_source(
            (CORPUS / "23-missing-include.pli").read_text(encoding="utf-8"),
            "23-missing-include.pli",
            include_names={"COMMON", "NESTED"},
        )
        shadowed = parse_pli_source(
            (CORPUS / "24-shadowed-call.pli").read_text(encoding="utf-8"),
            "24-shadowed-call.pli",
        )
        self.assertEqual(["missing-include"], [item["code"] for item in missing["diagnostics"]])
        self.assertEqual(["ambiguous-shadowed-call"], [item["code"] for item in shadowed["diagnostics"]])
        self.assertEqual("blocked", missing["status"])
        self.assertEqual("blocked", shadowed["status"])

    def test_unsupported_and_malformed_syntax_has_locations(self) -> None:
        for name, code in (
            ("25-unsupported-preprocessor.pli", "unsupported-preprocessor"),
            ("26-unsupported-storage.pli", "unsupported-based-storage"),
            ("27-malformed-comment.pli", "unterminated-comment"),
        ):
            parsed = parse_pli_source((CORPUS / name).read_text(encoding="utf-8"), name)
            self.assertEqual("blocked", parsed["status"])
            diagnostics = {item["code"]: item for item in parsed["diagnostics"]}
            self.assertIn(code, diagnostics)
            diagnostic = diagnostics[code]
            self.assertGreaterEqual(diagnostic["line"], 1)
            self.assertGreaterEqual(diagnostic["column"], 1)

    def test_targeted_semantic_boundaries_are_explicit(self) -> None:
        golden, receipt = self.build()
        targeted = [item for item in golden["results"] if item["classification"] == "boundary"]
        self.assertEqual(25, len(targeted))
        self.assertTrue(all(item["passed"] for item in targeted))
        paths = {item["path"] for item in targeted}
        for prefix in ("30-controlled", "32-pointer", "33-array", "35-picture", "38-on-", "41-preprocessor", "44-aligned", "47-procedure", "49-sql-cursor", "51-cics", "52-ims"):
            self.assertTrue(any(path.startswith(prefix) for path in paths), prefix)
        self.assertGreaterEqual(len(receipt["coverage"]["explicit_gap_codes"]), 10)

    def test_receipt_tamper_graph_drift_and_overclaim_fail_closed(self) -> None:
        golden, receipt = self.build()
        tampered = copy.deepcopy(receipt)
        tampered["coverage"]["supported_matrix_construct_count"] = 999
        self.assertIn(
            "PL/I conformance content_sha256 is invalid",
            validate_conformance_receipt(tampered, golden, GRAPH),
        )
        drifted = copy.deepcopy(GRAPH)
        drifted["content_sha256"] = "f" * 64
        self.assertIn(
            "PL/I conformance targets a different canonical graph",
            validate_conformance_receipt(receipt, golden, drifted),
        )
        overclaim = copy.deepcopy(receipt)
        overclaim["claim_boundary"]["mainframe_equivalent"] = True
        from lightyear_extensions.contracts import canonical_hash
        overclaim["content_sha256"] = canonical_hash(overclaim, {"content_sha256"})
        self.assertIn(
            "PL/I conformance overstates runtime or mainframe equivalence",
            validate_conformance_receipt(overclaim, golden, GRAPH),
        )

    def test_fragment_frontend_fails_closed_on_unsupported_source(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            source_root = Path(temporary)
            (source_root / "BAD.pli").write_text(
                "BAD: PROC OPTIONS(MAIN);\n DCL VALUE BASED(PTR);\n END BAD;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unsupported-based-storage"):
                build_pli_fragment(GRAPH, source_root, ROOT)


if __name__ == "__main__":
    unittest.main()
