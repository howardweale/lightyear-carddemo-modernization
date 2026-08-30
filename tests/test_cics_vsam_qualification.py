from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_readiness.cics_vsam_qualification import (
    GRAPH_MINIMUMS,
    build_cics_vsam_conformance,
    build_cics_vsam_ledger,
    build_cics_vsam_qualification,
    execute_conformance_case,
    validate_cics_vsam_conformance,
    validate_cics_vsam_graph,
    validate_cics_vsam_ledger,
    validate_cics_vsam_qualification,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH = json.loads((ROOT / "knowledge/graph.receipt.json").read_text())
CASES = json.loads((ROOT / "readiness/cics-vsam/conformance/cases.json").read_text())


class CicsVsamQualificationTests(unittest.TestCase):
    def test_inventory_is_bound_to_meaningful_native_graph_entities(self) -> None:
        result = build_cics_vsam_qualification(ROOT)
        inventory = result["inventory"]
        self.assertGreaterEqual(inventory["cics_commands"], 200)
        self.assertGreaterEqual(inventory["cics_file_resources"], 10)
        self.assertGreaterEqual(inventory["cics_transactions"], 20)
        self.assertGreaterEqual(inventory["vsam_clusters"], 10)
        self.assertGreaterEqual(inventory["vsam_alternate_indexes"], 3)
        self.assertGreaterEqual(inventory["vsam_paths"], 3)
        self.assertEqual(GRAPH["content_sha256"], result["bindings"]["graph_content_sha256"])

    def test_each_required_graph_kind_and_relation_is_a_holdout_gate(self) -> None:
        self.assertEqual([], validate_cics_vsam_graph(GRAPH))
        for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
            for name, minimum in GRAPH_MINIMUMS[group].items():
                held_out = copy.deepcopy(GRAPH)
                held_out["statistics"][field][name] = minimum - 1
                self.assertIn(
                    f"cics-vsam-graph-{group}-{name}-below-minimum",
                    validate_cics_vsam_graph(held_out),
                    msg=f"missing graph holdout for {group}.{name}",
                )

    def test_corpus_is_deterministic_broad_and_fail_closed(self) -> None:
        first = build_cics_vsam_conformance(ROOT)
        second = build_cics_vsam_conformance(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(38, first["corpus"]["case_count"])
        self.assertEqual(4, first["corpus"]["positive_case_count"])
        self.assertEqual(30, first["corpus"]["targeted_boundary_case_count"])
        self.assertEqual(4, first["corpus"]["mutation_case_count"])
        self.assertEqual(34, first["corpus"]["passed_case_count"])
        self.assertEqual(4, first["corpus"]["blocked_case_count"])
        self.assertGreaterEqual(first["coverage"]["observed_feature_count"], 50)
        self.assertEqual(["ESDS", "KSDS", "RRDS"], sorted(first["coverage"]["organizations"]))
        self.assertEqual(GRAPH["content_sha256"], first["graph_content_sha256"])

    def test_access_mutation_status_lock_and_program_control_vectors_execute(self) -> None:
        observed = {case["id"]: execute_conformance_case(case) for case in CASES["cases"]}
        self.assertEqual(("NORMAL", "00", 1), tuple(observed["06-ksds-write-new"][key] for key in ("response", "file_status", "mutation_count")))
        self.assertEqual(("DUPREC", "22"), tuple(observed["07-ksds-write-duplicate"][key] for key in ("response", "file_status")))
        self.assertEqual("update-token-required", observed["09-rewrite-without-token"]["diagnostics"][0])
        self.assertEqual(2, observed["17-aix-nonunique-read"]["result_count"])
        self.assertEqual(["STARTBR", "READNEXT", "ENDBR"], observed["21-browse-forward"]["trace"])
        self.assertEqual("LOCKED", observed["25-enq-contention"]["response"])
        self.assertEqual(2, observed["27-syncpoint-commit"]["mutation_count"])
        self.assertEqual(0, observed["28-syncpoint-rollback"]["mutation_count"])
        self.assertEqual(42, observed["30-resp2-preservation"]["resp2"])
        for case_id in ("32-program-link", "33-program-xctl", "34-program-return"):
            self.assertEqual("NORMAL", observed[case_id]["response"])

    def test_unsupported_vectors_are_diagnostic_and_never_passed(self) -> None:
        for case in CASES["cases"][-4:]:
            result = execute_conformance_case(case)
            self.assertEqual("blocked", result["status"])
            self.assertEqual("INVREQ", result["response"])
            self.assertEqual("92", result["file_status"])
            self.assertEqual(1, len(result["diagnostics"]))

    def test_manifest_requires_exact_case_identity_and_expectations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "readiness/cics-vsam/conformance").mkdir(parents=True)
            (root / "knowledge").mkdir()
            (root / "knowledge/graph.receipt.json").write_text(json.dumps(GRAPH), encoding="utf-8")
            tampered = copy.deepcopy(CASES)
            tampered["cases"].pop()
            (root / "readiness/cics-vsam/conformance/cases.json").write_text(
                json.dumps(seal(tampered)), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "exact 38-case set"):
                build_cics_vsam_conformance(root)

        mutated = copy.deepcopy(CASES["cases"][0])
        mutated["expected_response"] = "NOTFND"
        self.assertNotEqual(mutated["expected_response"], execute_conformance_case(mutated)["response"])

    def test_eleven_gates_keep_native_and_recovery_claims_blocked(self) -> None:
        result = build_cics_vsam_qualification(ROOT)
        statuses = {item["gate"]: item["status"] for item in result["qualification_gates"]}
        self.assertEqual(11, len(statuses))
        self.assertEqual("passed-static", statuses["estate-graph-inventory"])
        self.assertEqual("policy-decision-required", statuses["enq-deq-syncpoint-and-recovery"])
        self.assertEqual("excluded-unqualified", statuses["rls-queues-security-and-routing"])
        self.assertEqual("blocked-no-authorized-zos-evidence", statuses["authorized-native-cics-vsam-execution"])
        self.assertTrue(result["qualification_mechanism_ready"])
        self.assertTrue(result["development_ready"])
        for name in (
            "native_vsam_qualified", "native_cics_qualified", "rls_qualified", "recovery_equivalent",
            "cics_runtime_equivalent", "mainframe_equivalent", "production_ready",
        ):
            self.assertFalse(result[name])

    def test_ledger_uses_all_five_classes_without_silent_promotion(self) -> None:
        ledger = build_cics_vsam_ledger(GRAPH)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual(27, len(ledger["entries"]))
        self.assertEqual([], validate_cics_vsam_ledger(ledger))
        for name in COMPATIBILITY_CLASSES:
            self.assertGreater(ledger["statistics"][name], 0)

        policy = copy.deepcopy(ledger)
        next(item for item in policy["entries"] if item["classification"] == "policy-decision-required")["decision"] = "accepted-by-default"
        self.assertIn("cics-vsam-ledger-policy-auto-accepted", validate_cics_vsam_ledger(seal(policy)))
        unsupported = copy.deepcopy(ledger)
        next(item for item in unsupported["entries"] if item["classification"] == "unsupported")["decision"] = "migrated"
        self.assertIn("cics-vsam-ledger-unsupported-not-excluded", validate_cics_vsam_ledger(seal(unsupported)))

    def test_rehashed_overclaims_and_content_tampering_are_rejected(self) -> None:
        qualification = copy.deepcopy(build_cics_vsam_qualification(ROOT))
        qualification["native_cics_qualified"] = True
        qualification["mainframe_equivalent"] = True
        errors = validate_cics_vsam_qualification(ROOT, seal(qualification))
        self.assertIn("cics-vsam-qualification-drift", errors)
        self.assertIn("cics-vsam-qualification-overclaims-readiness", errors)

        receipt = copy.deepcopy(build_cics_vsam_conformance(ROOT))
        receipt["claim_boundary"]["recovery_equivalent"] = True
        errors = validate_cics_vsam_conformance(ROOT, seal(receipt))
        self.assertIn("cics-vsam-conformance-drift", errors)
        self.assertIn("cics-vsam-conformance-overclaims-readiness", errors)

    def test_committed_artifacts_are_current_and_schemas_are_frozen(self) -> None:
        conformance = json.loads((ROOT / "readiness/cics-vsam/conformance.receipt.json").read_text())
        ledger = json.loads((ROOT / "readiness/cics-vsam/compatibility-ledger.json").read_text())
        qualification = json.loads((ROOT / "readiness/cics-vsam/qualification.json").read_text())
        self.assertEqual(build_cics_vsam_conformance(ROOT), conformance)
        self.assertEqual(build_cics_vsam_ledger(GRAPH), ledger)
        self.assertEqual(build_cics_vsam_qualification(ROOT), qualification)
        self.assertEqual([], validate_cics_vsam_conformance(ROOT, conformance))
        self.assertEqual([], validate_cics_vsam_qualification(ROOT, qualification))
        for name in (
            "cics-vsam-conformance-receipt.schema.json",
            "cics-vsam-compatibility-ledger.schema.json",
            "cics-vsam-qualification.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
