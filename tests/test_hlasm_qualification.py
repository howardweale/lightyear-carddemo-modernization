from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_readiness.hlasm_qualification import (
    GRAPH_MINIMUMS,
    build_hlasm_conformance,
    build_hlasm_ledger,
    build_hlasm_qualification,
    execute_conformance_case,
    validate_hlasm_conformance,
    validate_hlasm_graph,
    validate_hlasm_ledger,
    validate_hlasm_qualification,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH = json.loads((ROOT / "knowledge/graph.receipt.json").read_text())
CASES = json.loads((ROOT / "readiness/asm-date/conformance/cases.json").read_text())


class HlasmQualificationTests(unittest.TestCase):
    def test_inventory_is_bound_to_meaningful_native_graph_entities(self) -> None:
        result = build_hlasm_qualification(ROOT)
        inventory = result["inventory"]
        self.assertGreaterEqual(inventory["assembler_programs"], 2)
        self.assertGreaterEqual(inventory["assembler_instructions"], 41)
        self.assertGreaterEqual(inventory["assembler_symbols"], 23)
        self.assertGreaterEqual(inventory["assembler_dsects"], 1)
        self.assertGreaterEqual(inventory["assembler_fields"], 5)
        self.assertGreaterEqual(inventory["assembler_macros"], 1)
        self.assertEqual(GRAPH["content_sha256"], result["bindings"]["graph_content_sha256"])

    def test_each_required_graph_kind_and_relation_is_a_holdout_gate(self) -> None:
        self.assertEqual([], validate_hlasm_graph(GRAPH))
        for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
            for name, minimum in GRAPH_MINIMUMS[group].items():
                held_out = copy.deepcopy(GRAPH)
                held_out["statistics"][field][name] = minimum - 1
                self.assertIn(
                    f"hlasm-graph-{group}-{name}-below-minimum",
                    validate_hlasm_graph(held_out),
                    msg=f"missing graph holdout for {group}.{name}",
                )

    def test_corpus_is_deterministic_broad_and_fail_closed(self) -> None:
        first = build_hlasm_conformance(ROOT)
        self.assertEqual(first, build_hlasm_conformance(ROOT))
        self.assertEqual(40, first["corpus"]["case_count"])
        self.assertEqual(4, first["corpus"]["positive_case_count"])
        self.assertEqual(32, first["corpus"]["targeted_boundary_case_count"])
        self.assertEqual(4, first["corpus"]["mutation_case_count"])
        self.assertEqual(36, first["corpus"]["passed_case_count"])
        self.assertEqual(4, first["corpus"]["blocked_case_count"])
        self.assertGreaterEqual(first["coverage"]["observed_feature_count"], 100)
        self.assertEqual(["COBDATFT", "MVSWAIT"], first["coverage"]["programs"])
        self.assertEqual(GRAPH["content_sha256"], first["graph_content_sha256"])

    def test_date_dsect_instruction_register_and_macro_vectors_execute(self) -> None:
        observed = {case["id"]: execute_conformance_case(case) for case in CASES["cases"]}
        self.assertEqual("SUCCESS", observed["01-compact-to-hyphenated"]["response"])
        self.assertEqual("INVALID_INPUT", observed["08-compact-separator-rejected"]["response"])
        self.assertEqual(5, observed["12-dsect-total-layout"]["result_count"])
        self.assertEqual("ADDRESSING_ERROR", observed["16-mvc-range-error"]["response"])
        self.assertEqual(0, observed["18-cli-equal"]["condition_code"])
        self.assertEqual("BRANCH_NOT_TAKEN", observed["23-be-not-taken"]["response"])
        self.assertEqual(15, observed["26-stm-wrap-register-range"]["mutation_count"])
        self.assertEqual(0, observed["31-sr-zero-register"]["register_changes"]["R15"])
        self.assertEqual("MODELED", observed["35-asmwait-macro-expansion"]["response"])
        self.assertIn("stimer-not-invoked", observed["03-mvswait-interval-handoff"]["diagnostics"])

    def test_unsupported_vectors_are_diagnostic_and_never_passed(self) -> None:
        for case in CASES["cases"][-4:]:
            result = execute_conformance_case(case)
            self.assertEqual("blocked", result["status"])
            self.assertEqual("UNSUPPORTED", result["response"])
            self.assertEqual(0, result["mutation_count"])
            self.assertEqual(1, len(result["diagnostics"]))

    def test_manifest_requires_exact_case_identity_and_expectations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "readiness/asm-date/conformance").mkdir(parents=True)
            (root / "knowledge").mkdir()
            (root / "knowledge/graph.receipt.json").write_text(json.dumps(GRAPH), encoding="utf-8")
            tampered = copy.deepcopy(CASES)
            tampered["cases"].pop()
            (root / "readiness/asm-date/conformance/cases.json").write_text(
                json.dumps(seal(tampered)), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "exact 40-case set"):
                build_hlasm_conformance(root)

        mutated = copy.deepcopy(CASES["cases"][0])
        mutated["expected_response"] = "INVALID_INPUT"
        self.assertNotEqual(mutated["expected_response"], execute_conformance_case(mutated)["response"])

    def test_eleven_gates_keep_native_build_linkage_and_runtime_claims_blocked(self) -> None:
        result = build_hlasm_qualification(ROOT)
        statuses = {item["gate"]: item["status"] for item in result["qualification_gates"]}
        self.assertEqual(11, len(statuses))
        self.assertEqual("passed-static", statuses["estate-graph-inventory"])
        self.assertEqual("policy-decision-required", statuses["register-addressing-save-area-and-linkage"])
        self.assertEqual("excluded-unqualified", statuses["macro-stimer-amode-rmode-and-binder"])
        self.assertEqual("blocked-no-authorized-zos-evidence", statuses["authorized-native-hlasm-build-and-execution"])
        self.assertTrue(result["qualification_mechanism_ready"])
        self.assertTrue(result["development_ready"])
        for name in (
            "native_hlasm_qualified", "assembler_qualified", "binder_qualified", "le_linkage_qualified",
            "system_services_qualified", "runtime_equivalent", "mainframe_equivalent", "production_ready",
        ):
            self.assertFalse(result[name])

    def test_ledger_uses_all_five_classes_without_silent_promotion(self) -> None:
        ledger = build_hlasm_ledger(GRAPH)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual(28, len(ledger["entries"]))
        self.assertEqual([], validate_hlasm_ledger(ledger))
        for name in COMPATIBILITY_CLASSES:
            self.assertGreater(ledger["statistics"][name], 0)

        policy = copy.deepcopy(ledger)
        next(item for item in policy["entries"] if item["classification"] == "policy-decision-required")["decision"] = "accepted-by-default"
        self.assertIn("hlasm-ledger-policy-auto-accepted", validate_hlasm_ledger(seal(policy)))
        unsupported = copy.deepcopy(ledger)
        next(item for item in unsupported["entries"] if item["classification"] == "unsupported")["decision"] = "migrated"
        self.assertIn("hlasm-ledger-unsupported-not-excluded", validate_hlasm_ledger(seal(unsupported)))

    def test_rehashed_overclaims_and_content_tampering_are_rejected(self) -> None:
        qualification = copy.deepcopy(build_hlasm_qualification(ROOT))
        qualification["native_hlasm_qualified"] = True
        qualification["mainframe_equivalent"] = True
        errors = validate_hlasm_qualification(ROOT, seal(qualification))
        self.assertIn("hlasm-qualification-drift", errors)
        self.assertIn("hlasm-qualification-overclaims-readiness", errors)

        receipt = copy.deepcopy(build_hlasm_conformance(ROOT))
        receipt["claim_boundary"]["runtime_equivalent"] = True
        errors = validate_hlasm_conformance(ROOT, seal(receipt))
        self.assertIn("hlasm-conformance-drift", errors)
        self.assertIn("hlasm-conformance-overclaims-readiness", errors)

    def test_committed_artifacts_are_current_and_schemas_are_frozen(self) -> None:
        conformance = json.loads((ROOT / "readiness/asm-date/conformance.receipt.json").read_text())
        ledger = json.loads((ROOT / "readiness/asm-date/compatibility-ledger.json").read_text())
        qualification = json.loads((ROOT / "readiness/asm-date/qualification.json").read_text())
        self.assertEqual(build_hlasm_conformance(ROOT), conformance)
        self.assertEqual(build_hlasm_ledger(GRAPH), ledger)
        self.assertEqual(build_hlasm_qualification(ROOT), qualification)
        self.assertEqual([], validate_hlasm_conformance(ROOT, conformance))
        self.assertEqual([], validate_hlasm_qualification(ROOT, qualification))
        for name in (
            "hlasm-conformance-receipt.schema.json",
            "hlasm-compatibility-ledger.schema.json",
            "hlasm-qualification.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
