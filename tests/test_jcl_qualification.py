from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_readiness.jcl import (
    build_jcl_conformance,
    build_jcl_ledger,
    build_jcl_qualification,
    parse_jcl_source,
    validate_jcl_conformance,
    validate_jcl_ledger,
    validate_jcl_qualification,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH = json.loads((ROOT / "knowledge/graph.receipt.json").read_text())
CORPUS = ROOT / "readiness/jcl/corpus"


class JclQualificationTests(unittest.TestCase):
    def test_inventory_is_bound_to_a_meaningful_canonical_estate(self) -> None:
        result = build_jcl_qualification(ROOT)
        inventory = result["inventory"]
        self.assertGreaterEqual(inventory["jobs"], 40)
        self.assertGreaterEqual(inventory["procedures"], 2)
        self.assertGreaterEqual(inventory["steps"], 100)
        self.assertGreaterEqual(inventory["dd_allocations"], 400)
        self.assertEqual(GRAPH["content_sha256"], result["bindings"]["graph_content_sha256"])

    def test_targeted_corpus_is_deterministic_and_fail_closed(self) -> None:
        receipt = build_jcl_conformance(ROOT)
        self.assertEqual(30, receipt["corpus"]["case_count"])
        self.assertEqual(20, receipt["corpus"]["targeted_boundary_case_count"])
        self.assertEqual(6, receipt["corpus"]["mutation_case_count"])
        self.assertEqual(24, receipt["corpus"]["passed_case_count"])
        self.assertEqual(6, receipt["corpus"]["blocked_case_count"])
        self.assertGreaterEqual(receipt["coverage"]["observed_feature_count"], 30)
        self.assertTrue(all(item["passed"] for item in receipt["results"]))
        self.assertEqual(GRAPH["content_sha256"], receipt["graph_content_sha256"])

    def test_ten_gates_separate_static_policy_and_native_claims(self) -> None:
        result = build_jcl_qualification(ROOT)
        statuses = {item["gate"]: item["status"] for item in result["qualification_gates"]}
        self.assertEqual(10, len(statuses))
        self.assertEqual("passed-static", statuses["estate-inventory"])
        self.assertEqual("policy-decision-required", statuses["condition-codes-restart-and-recovery"])
        self.assertEqual("blocked-no-authorized-zos-evidence", statuses["authorized-jes-catalog-scheduler-execution"])

    def test_static_proof_does_not_promote_jes_scheduler_or_restart(self) -> None:
        result = build_jcl_qualification(ROOT)
        self.assertTrue(result["qualification_mechanism_ready"])
        self.assertTrue(result["development_ready"])
        for name in (
            "native_jcl_qualified", "jes_qualified", "scheduler_qualified", "runtime_equivalent",
            "restart_equivalent", "mainframe_equivalent", "production_ready",
        ):
            self.assertFalse(result[name])

    def test_ledger_uses_all_five_governing_classes(self) -> None:
        ledger = build_jcl_ledger(GRAPH)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual(22, len(ledger["entries"]))
        self.assertEqual([], validate_jcl_ledger(ledger))
        for name in COMPATIBILITY_CLASSES:
            self.assertGreater(ledger["statistics"][name], 0)

    def test_policy_and_unsupported_items_cannot_be_silently_promoted(self) -> None:
        policy = copy.deepcopy(build_jcl_ledger(GRAPH))
        item = next(entry for entry in policy["entries"] if entry["classification"] == "policy-decision-required")
        item["decision"] = "accepted-by-default"
        self.assertIn("jcl-ledger-policy-auto-accepted", validate_jcl_ledger(seal(policy)))

        unsupported = copy.deepcopy(build_jcl_ledger(GRAPH))
        item = next(entry for entry in unsupported["entries"] if entry["classification"] == "unsupported")
        item["decision"] = "migrated"
        self.assertIn("jcl-ledger-unsupported-not-excluded", validate_jcl_ledger(seal(unsupported)))

    def test_comments_instream_data_and_continuations_do_not_create_false_steps(self) -> None:
        comments = parse_jcl_source((CORPUS / "04-comments.jcl").read_text(), "04-comments.jcl")
        self.assertEqual(1, sum(item["operation"] == "EXEC" for item in comments["statements"]))
        instream = parse_jcl_source((CORPUS / "13-instream-data.jcl").read_text(), "13-instream-data.jcl")
        self.assertEqual("passed", instream["status"])
        self.assertIn("instream-data", instream["features"])
        continuation = parse_jcl_source((CORPUS / "15-dcb-space.jcl").read_text(), "15-dcb-space.jcl")
        self.assertTrue({"continued-parameters", "record-layout", "space-allocation"}.issubset(continuation["features"]))

    def test_operational_boundaries_are_discovered_but_not_qualified(self) -> None:
        for name, features in (
            ("18-restart-typrun.jcl", {"restart-control", "typrun-control"}),
            ("23-db2-cics-boundaries.jcl", {"db2-boundary", "cics-boundary"}),
            ("24-ims-output-boundary.jcl", {"ims-boundary", "output-descriptor"}),
        ):
            parsed = parse_jcl_source((CORPUS / name).read_text(), name)
            self.assertEqual("passed", parsed["status"])
            self.assertTrue(features.issubset(parsed["features"]))

    def test_manifest_exact_source_set_and_diagnostics_fail_closed(self) -> None:
        undeclared = CORPUS / "UNDECLARED.jcl"
        undeclared.write_text("//EXTRA JOB\n//RUN EXEC PGM=IEFBR14\n", encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "exact source set"):
                build_jcl_conformance(ROOT)
        finally:
            undeclared.unlink()
        for name, code in (
            ("26-unsupported-operation.jcl", "unsupported-operation"),
            ("27-unterminated-if.jcl", "unterminated-if"),
            ("28-scheduler-directive.jcl", "unsupported-scheduler-directive"),
            ("29-invalid-disposition.jcl", "invalid-disposition"),
            ("30-exec-target-missing.jcl", "exec-target-missing"),
        ):
            parsed = parse_jcl_source((CORPUS / name).read_text(), name)
            self.assertEqual("blocked", parsed["status"])
            diagnostic = next(item for item in parsed["diagnostics"] if item["code"] == code)
            self.assertGreaterEqual(diagnostic["line"], 1)
            self.assertGreaterEqual(diagnostic["column"], 1)

    def test_rehashed_overclaims_and_content_tampering_are_rejected(self) -> None:
        qualification = copy.deepcopy(build_jcl_qualification(ROOT))
        qualification["jes_qualified"] = True
        qualification["mainframe_equivalent"] = True
        errors = validate_jcl_qualification(ROOT, seal(qualification))
        self.assertIn("jcl-qualification-drift", errors)
        self.assertIn("jcl-qualification-overclaims-readiness", errors)

        receipt = copy.deepcopy(build_jcl_conformance(ROOT))
        receipt["claim_boundary"]["restart_equivalent"] = True
        errors = validate_jcl_conformance(ROOT, seal(receipt))
        self.assertIn("jcl-conformance-drift", errors)
        self.assertIn("jcl-conformance-overclaims-readiness", errors)

    def test_committed_artifacts_are_current_and_schemas_are_frozen(self) -> None:
        conformance = json.loads((ROOT / "readiness/jcl/conformance.receipt.json").read_text())
        ledger = json.loads((ROOT / "readiness/jcl/compatibility-ledger.json").read_text())
        qualification = json.loads((ROOT / "readiness/jcl/qualification.json").read_text())
        self.assertEqual(build_jcl_conformance(ROOT), conformance)
        self.assertEqual(build_jcl_ledger(GRAPH), ledger)
        self.assertEqual(build_jcl_qualification(ROOT), qualification)
        self.assertEqual([], validate_jcl_conformance(ROOT, conformance))
        self.assertEqual([], validate_jcl_qualification(ROOT, qualification))
        for name in (
            "jcl-conformance-receipt.schema.json",
            "jcl-compatibility-ledger.schema.json",
            "jcl-qualification.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
