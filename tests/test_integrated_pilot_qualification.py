from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_pilot.integrated_qualification import (
    GRAPH_MINIMUMS,
    REQUIRED_DEPENDENCIES,
    REQUIRED_SOURCE_FILES,
    REQUIRED_TECHNOLOGIES,
    build_evidence_matrix,
    build_integrated_conformance,
    build_integrated_ledger,
    build_integrated_qualification,
    execute_integrated_case,
    validate_evidence_matrix,
    validate_integrated_conformance,
    validate_integrated_graph,
    validate_integrated_ledger,
    validate_integrated_manifest,
    validate_integrated_qualification,
    validate_integrated_scope,
)
from lightyear_pilot.pilot import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "pilot/reference-output"
SELECTION = json.loads((PILOT_ROOT / "pilot-selection.json").read_text())
PACKAGE = json.loads((PILOT_ROOT / "pilot-work-package.json").read_text())
CASES = json.loads((ROOT / "pilot/integrated-qualification/conformance/cases.json").read_text())


def _graph() -> dict:
    import gzip

    with gzip.open(PILOT_ROOT / "source-estate.snapshot.json.gz", "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _seal(payload: dict) -> dict:
    payload["content_sha256"] = canonical_hash(payload, {"content_sha256"})
    return payload


class IntegratedPilotQualificationTests(unittest.TestCase):
    def test_exact_selected_scope_is_bound_to_five_cells_and_six_files(self) -> None:
        self.assertEqual([], validate_integrated_scope(SELECTION, PACKAGE, _graph()))
        self.assertEqual(REQUIRED_TECHNOLOGIES, tuple(SELECTION["selected_cluster"]["technologies"]))
        self.assertEqual(REQUIRED_SOURCE_FILES, tuple(SELECTION["selected_cluster"]["source_files"]))
        self.assertEqual(5, len(PACKAGE["cells"]))
        self.assertEqual(5, sum(len(item["coordination_dependencies"]) for item in PACKAGE["cells"]))

    def test_each_required_graph_kind_and_relation_is_a_holdout(self) -> None:
        graph = _graph()
        self.assertEqual([], validate_integrated_graph(graph))
        for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
            for name, minimum in GRAPH_MINIMUMS[group].items():
                held_out = copy.deepcopy(graph)
                held_out["statistics"][field][name] = minimum - 1
                self.assertIn(
                    f"integrated-pilot-graph-{group}-{name}-below-minimum",
                    validate_integrated_graph(held_out),
                    msg=f"missing graph holdout for {group}.{name}",
                )

    def test_each_cell_dependency_set_is_exact_and_drift_fails(self) -> None:
        by_id = {item["cell_id"]: item for item in PACKAGE["cells"]}
        by_technology = {item["technology"]: item for item in PACKAGE["cells"]}
        for technology, targets in REQUIRED_DEPENDENCIES.items():
            actual = {
                by_id[item]["technology"]
                for item in by_technology[technology]["coordination_dependencies"]
            }
            self.assertEqual(targets, actual)

        changed = copy.deepcopy(PACKAGE)
        next(item for item in changed["cells"] if item["technology"] == "JCL")["coordination_dependencies"].pop()
        self.assertTrue(any("dependencies-invalid" in item for item in validate_integrated_scope(SELECTION, changed, _graph())))

    def test_corpus_is_deterministic_broad_and_fail_closed(self) -> None:
        first = build_integrated_conformance(ROOT)
        self.assertEqual(first, build_integrated_conformance(ROOT))
        self.assertEqual(40, first["corpus"]["case_count"])
        self.assertEqual(5, first["corpus"]["positive_case_count"])
        self.assertEqual(31, first["corpus"]["targeted_boundary_case_count"])
        self.assertEqual(4, first["corpus"]["mutation_case_count"])
        self.assertEqual(36, first["corpus"]["passed_case_count"])
        self.assertEqual(4, first["corpus"]["blocked_case_count"])
        self.assertGreaterEqual(first["coverage"]["observed_feature_count"], 100)
        self.assertEqual(list(REQUIRED_TECHNOLOGIES), first["coverage"]["technologies"])

    def test_integrated_paths_preserve_source_sql_and_call_quirks(self) -> None:
        observed = {item["id"]: execute_integrated_case(item) for item in CASES["cases"]}
        self.assertEqual("SUCCESS", observed["01-batch-integrated-success"]["response"])
        self.assertEqual(1, observed["01-batch-integrated-success"]["external_call_count"])
        self.assertEqual(8, observed["06-batch-null-pointer-return-eight"]["return_code"])
        self.assertEqual("SQL_NOT_FOUND", observed["07-batch-no-db2-row"]["response"])
        self.assertEqual("SQL_MULTIPLE_ROWS", observed["08-batch-multiple-db2-rows"]["response"])
        self.assertEqual(12345678901, observed["13-lookup-overwrites-request"]["selected_auth_id"])
        self.assertIn("CBACT04C-external-behavior-not-modeled", observed["02-online-integrated-success"]["diagnostics"])

    def test_layout_schema_jcl_hlasm_and_call_boundaries_execute(self) -> None:
        observed = {item["id"]: execute_integrated_case(item) for item in CASES["cases"]}
        self.assertEqual(12, observed["21-copybook-layout-exact"]["result_count"])
        self.assertEqual("DATA_ERROR", observed["18-schema-duplicate-primary-key"]["response"])
        self.assertEqual("INDEX_MISMATCH", observed["25-db2-index-reversed"]["response"])
        self.assertEqual("SEQUENCE_ERROR", observed["27-jcl-reversed-step-order"]["response"])
        self.assertEqual("ALLOCATION_MISMATCH", observed["31-dataset-binding-drift"]["response"])
        self.assertEqual(8, observed["32-hlasm-null-pointer"]["return_code"])
        self.assertEqual("CALL_CONTRACT_MISMATCH", observed["36-pli-call-convention-mismatch"]["response"])

    def test_unsupported_native_vectors_are_diagnostic_and_blocked(self) -> None:
        for case in CASES["cases"][-4:]:
            result = execute_integrated_case(case)
            self.assertEqual("blocked", result["status"])
            self.assertEqual("UNSUPPORTED", result["response"])
            self.assertEqual(0, result["mutation_count"])
            self.assertEqual(1, len(result["diagnostics"]))

    def test_manifest_requires_exact_case_set_and_expectations(self) -> None:
        tampered = copy.deepcopy(CASES)
        tampered["cases"].pop()
        errors = validate_integrated_manifest(_seal(tampered))
        self.assertIn("integrated-pilot-corpus-frozen-content-drift", errors)
        self.assertIn("integrated-pilot-corpus-must-bind-exact-40-case-set", errors)

        changed = copy.deepcopy(CASES["cases"][0])
        changed["expected_response"] = "SQL_NOT_FOUND"
        self.assertNotEqual(changed["expected_response"], execute_integrated_case(changed)["response"])

    def test_evidence_matrix_covers_every_cell_and_keeps_live_evidence_blocked(self) -> None:
        matrix = build_evidence_matrix(ROOT)
        self.assertEqual([], validate_evidence_matrix(ROOT, matrix))
        self.assertEqual(set(REQUIRED_TECHNOLOGIES), {item["technology"] for item in matrix["cells"]})
        self.assertEqual(15, matrix["statistics"]["deliverable_count"])
        self.assertEqual(10, matrix["statistics"]["acceptance_evidence_count"])
        self.assertEqual(15, matrix["statistics"]["blocked_live_evidence_count"])
        self.assertTrue(matrix["wave_2_integrated_development_ready"])
        self.assertTrue(all(item["integrated_development_evidence_passed"] for item in matrix["cells"]))
        self.assertTrue(all(not item["native_evidence_passed"] and not item["dispatch_ready"] for item in matrix["cells"]))
        self.assertTrue(all(not item["qualification_mechanism"]["exact_source_acceptance_implied"] for item in matrix["cells"]))

    def test_ledger_uses_all_five_classes_without_silent_promotion(self) -> None:
        ledger = build_integrated_ledger(ROOT)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual(30, len(ledger["entries"]))
        self.assertEqual([], validate_integrated_ledger(ledger))
        for name in COMPATIBILITY_CLASSES:
            self.assertGreater(ledger["statistics"][name], 0)

        policy = copy.deepcopy(ledger)
        next(item for item in policy["entries"] if item["classification"] == "policy-decision-required")["decision"] = "accepted-by-default"
        self.assertIn("integrated-pilot-ledger-policy-auto-accepted", validate_integrated_ledger(_seal(policy)))
        unsupported = copy.deepcopy(ledger)
        next(item for item in unsupported["entries"] if item["classification"] == "unsupported")["decision"] = "migrated"
        self.assertIn("integrated-pilot-ledger-unsupported-not-excluded", validate_integrated_ledger(_seal(unsupported)))

    def test_twelve_gates_unlock_only_bounded_wave_two(self) -> None:
        result = build_integrated_qualification(ROOT)
        statuses = {item["gate"]: item["status"] for item in result["qualification_gates"]}
        self.assertEqual(12, len(statuses))
        self.assertEqual("passed-mechanism-bound", statuses["technology-qualification-mechanisms"])
        self.assertEqual("passed-bounded-synthetic", statuses["cross-cell-integrated-conformance"])
        self.assertEqual("policy-and-native-evidence-required", statuses["compatibility-policy-and-live-evidence"])
        self.assertEqual("blocked-no-authorized-evidence", statuses["authorized-native-integrated-execution"])
        self.assertTrue(result["wave_2_integrated_development_ready"])
        self.assertTrue(result["development_ready"])
        for name in (
            "factory_dispatch_allowed", "native_execution_observed", "native_runtime_qualified",
            "mainframe_equivalent", "production_release_allowed", "production_ready",
        ):
            self.assertFalse(result[name])

    def test_rehashed_overclaims_and_receipt_drift_are_rejected(self) -> None:
        qualification = copy.deepcopy(build_integrated_qualification(ROOT))
        qualification["factory_dispatch_allowed"] = True
        qualification["production_ready"] = True
        errors = validate_integrated_qualification(ROOT, _seal(qualification))
        self.assertIn("integrated-pilot-qualification-drift", errors)
        self.assertIn("integrated-pilot-qualification-overclaim", errors)

        conformance = copy.deepcopy(build_integrated_conformance(ROOT))
        conformance["claim_boundary"]["external_cobol_behavior_modeled"] = True
        errors = validate_integrated_conformance(ROOT, _seal(conformance))
        self.assertIn("integrated-pilot-conformance-drift", errors)
        self.assertIn("integrated-pilot-conformance-overclaim", errors)

    def test_committed_artifacts_are_current_and_schemas_are_frozen(self) -> None:
        root = ROOT / "pilot/integrated-qualification"
        conformance = json.loads((root / "conformance.receipt.json").read_text())
        matrix = json.loads((root / "evidence-matrix.json").read_text())
        ledger = json.loads((root / "compatibility-ledger.json").read_text())
        qualification = json.loads((root / "qualification.json").read_text())
        self.assertEqual(build_integrated_conformance(ROOT), conformance)
        self.assertEqual(build_evidence_matrix(ROOT), matrix)
        self.assertEqual(build_integrated_ledger(ROOT), ledger)
        self.assertEqual(build_integrated_qualification(ROOT), qualification)
        for name in (
            "integrated-pilot-conformance.schema.json",
            "integrated-pilot-evidence-matrix.schema.json",
            "integrated-pilot-compatibility-ledger.schema.json",
            "integrated-pilot-qualification.schema.json",
        ):
            schema = json.loads((ROOT / "pilot/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
