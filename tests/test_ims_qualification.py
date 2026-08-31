from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_readiness.ims_qualification import (
    GRAPH_MINIMUMS,
    build_ims_conformance,
    build_ims_ledger,
    build_ims_qualification,
    execute_conformance_case,
    validate_ims_conformance,
    validate_ims_graph,
    validate_ims_ledger,
    validate_ims_qualification,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH = json.loads((ROOT / "knowledge/graph.receipt.json").read_text())
CASES = json.loads((ROOT / "readiness/ims-expiry/conformance/cases.json").read_text())


class ImsQualificationTests(unittest.TestCase):
    def test_inventory_is_bound_to_meaningful_native_graph_entities(self) -> None:
        result = build_ims_qualification(ROOT)
        inventory = result["inventory"]
        self.assertGreaterEqual(inventory["ims_databases"], 4)
        self.assertGreaterEqual(inventory["ims_dataset_groups"], 4)
        self.assertGreaterEqual(inventory["ims_pcbs"], 6)
        self.assertGreaterEqual(inventory["ims_psbs"], 4)
        self.assertGreaterEqual(inventory["ims_segments"], 3)
        self.assertEqual(GRAPH["content_sha256"], result["bindings"]["graph_content_sha256"])

    def test_each_required_graph_kind_and_relation_is_a_holdout_gate(self) -> None:
        self.assertEqual([], validate_ims_graph(GRAPH))
        for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
            for name, minimum in GRAPH_MINIMUMS[group].items():
                held_out = copy.deepcopy(GRAPH)
                held_out["statistics"][field][name] = minimum - 1
                self.assertIn(
                    f"ims-graph-{group}-{name}-below-minimum",
                    validate_ims_graph(held_out),
                    msg=f"missing graph holdout for {group}.{name}",
                )

    def test_corpus_is_deterministic_broad_and_fail_closed(self) -> None:
        first = build_ims_conformance(ROOT)
        self.assertEqual(first, build_ims_conformance(ROOT))
        self.assertEqual(40, first["corpus"]["case_count"])
        self.assertEqual(4, first["corpus"]["positive_case_count"])
        self.assertEqual(32, first["corpus"]["targeted_boundary_case_count"])
        self.assertEqual(4, first["corpus"]["mutation_case_count"])
        self.assertEqual(36, first["corpus"]["passed_case_count"])
        self.assertEqual(4, first["corpus"]["blocked_case_count"])
        self.assertGreaterEqual(first["coverage"]["observed_feature_count"], 70)
        self.assertEqual(["GSAM", "HIDAM", "INDEX"], first["coverage"]["access_methods"])
        self.assertEqual(GRAPH["content_sha256"], first["graph_content_sha256"])

    def test_navigation_ssa_mutation_checkpoint_and_status_vectors_execute(self) -> None:
        observed = {case["id"]: execute_conformance_case(case) for case in CASES["cases"]}
        self.assertEqual(("SUCCESS", "  "), tuple(observed["01-gu-root-hit"][key] for key in ("response", "ims_status")))
        self.assertEqual("GB", observed["06-gn-end-database"]["ims_status"])
        self.assertEqual("DJ", observed["07-gnp-without-parent"]["ims_status"])
        self.assertTrue(observed["10-ghnp-child-hold"]["held"])
        self.assertEqual(["SSA QUALIFIED PAUTSUM0", "SSA QUALIFIED PAUTDTL1"], observed["14-multi-ssa-path"]["trace"])
        self.assertEqual("II", observed["19-isrt-root-duplicate"]["ims_status"])
        self.assertEqual(1, observed["22-repl-after-hold"]["mutation_count"])
        self.assertEqual(1, observed["24-dlet-child-after-hold"]["mutation_count"])
        self.assertEqual(2, observed["33-checkpoint-commit"]["mutation_count"])
        self.assertEqual(0, observed["35-rollback-discard"]["mutation_count"])

    def test_unsupported_vectors_are_diagnostic_and_never_passed(self) -> None:
        for case in CASES["cases"][-4:]:
            result = execute_conformance_case(case)
            self.assertEqual("blocked", result["status"])
            self.assertEqual("SEQUENCE_ERROR", result["response"])
            self.assertEqual("DJ", result["ims_status"])
            self.assertEqual(1, len(result["diagnostics"]))

    def test_manifest_requires_exact_case_identity_and_expectations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "readiness/ims-expiry/conformance").mkdir(parents=True)
            (root / "knowledge").mkdir()
            (root / "knowledge/graph.receipt.json").write_text(json.dumps(GRAPH), encoding="utf-8")
            tampered = copy.deepcopy(CASES)
            tampered["cases"].pop()
            (root / "readiness/ims-expiry/conformance/cases.json").write_text(json.dumps(seal(tampered)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact 40-case set"):
                build_ims_conformance(root)

        mutated = copy.deepcopy(CASES["cases"][0])
        mutated["expected_response"] = "SEGMENT_NOT_FOUND"
        self.assertNotEqual(mutated["expected_response"], execute_conformance_case(mutated)["response"])

    def test_eleven_gates_keep_native_restart_and_recovery_claims_blocked(self) -> None:
        result = build_ims_qualification(ROOT)
        statuses = {item["gate"]: item["status"] for item in result["qualification_gates"]}
        self.assertEqual(11, len(statuses))
        self.assertEqual("passed-static", statuses["estate-graph-inventory"])
        self.assertEqual("policy-decision-required", statuses["checkpoint-restart-rollback-and-recovery"])
        self.assertEqual("excluded-unqualified", statuses["scheduling-tm-fast-path-and-data-sharing"])
        self.assertEqual("blocked-no-authorized-zos-evidence", statuses["authorized-native-ims-execution"])
        self.assertTrue(result["qualification_mechanism_ready"])
        self.assertTrue(result["development_ready"])
        for name in (
            "native_ims_qualified", "ims_tm_qualified", "fast_path_qualified", "dbrc_recovery_equivalent",
            "restart_equivalent", "ims_runtime_equivalent", "mainframe_equivalent", "production_ready",
        ):
            self.assertFalse(result[name])

    def test_ledger_uses_all_five_classes_without_silent_promotion(self) -> None:
        ledger = build_ims_ledger(GRAPH)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual(28, len(ledger["entries"]))
        self.assertEqual([], validate_ims_ledger(ledger))
        for name in COMPATIBILITY_CLASSES:
            self.assertGreater(ledger["statistics"][name], 0)

        policy = copy.deepcopy(ledger)
        next(item for item in policy["entries"] if item["classification"] == "policy-decision-required")["decision"] = "accepted-by-default"
        self.assertIn("ims-ledger-policy-auto-accepted", validate_ims_ledger(seal(policy)))
        unsupported = copy.deepcopy(ledger)
        next(item for item in unsupported["entries"] if item["classification"] == "unsupported")["decision"] = "migrated"
        self.assertIn("ims-ledger-unsupported-not-excluded", validate_ims_ledger(seal(unsupported)))

    def test_rehashed_overclaims_and_content_tampering_are_rejected(self) -> None:
        qualification = copy.deepcopy(build_ims_qualification(ROOT))
        qualification["native_ims_qualified"] = True
        qualification["mainframe_equivalent"] = True
        errors = validate_ims_qualification(ROOT, seal(qualification))
        self.assertIn("ims-qualification-drift", errors)
        self.assertIn("ims-qualification-overclaims-readiness", errors)

        receipt = copy.deepcopy(build_ims_conformance(ROOT))
        receipt["claim_boundary"]["restart_equivalent"] = True
        errors = validate_ims_conformance(ROOT, seal(receipt))
        self.assertIn("ims-conformance-drift", errors)
        self.assertIn("ims-conformance-overclaims-readiness", errors)

    def test_committed_artifacts_are_current_and_schemas_are_frozen(self) -> None:
        conformance = json.loads((ROOT / "readiness/ims-expiry/conformance.receipt.json").read_text())
        ledger = json.loads((ROOT / "readiness/ims-expiry/compatibility-ledger.json").read_text())
        qualification = json.loads((ROOT / "readiness/ims-expiry/qualification.json").read_text())
        self.assertEqual(build_ims_conformance(ROOT), conformance)
        self.assertEqual(build_ims_ledger(GRAPH), ledger)
        self.assertEqual(build_ims_qualification(ROOT), qualification)
        self.assertEqual([], validate_ims_conformance(ROOT, conformance))
        self.assertEqual([], validate_ims_qualification(ROOT, qualification))
        for name in (
            "ims-conformance-receipt.schema.json",
            "ims-compatibility-ledger.schema.json",
            "ims-qualification.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
