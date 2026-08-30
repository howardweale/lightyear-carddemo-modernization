from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_readiness.pli import build_pli_ledger, build_pli_qualification, validate_pli_ledger, validate_pli_qualification


ROOT = Path(__file__).resolve().parents[1]
GRAPH = json.loads((ROOT / "knowledge/graph.receipt.json").read_text())


class PliQualificationTests(unittest.TestCase):
    def test_inventory_is_meaningful_but_explicitly_bounded(self) -> None:
        result = build_pli_qualification(ROOT)
        inventory = result["inventory"]
        self.assertEqual(52, inventory["corpus_cases"])
        self.assertEqual(22, inventory["supported_construct_categories"])
        self.assertEqual(25, inventory["targeted_boundary_cases"])
        self.assertGreaterEqual(inventory["mutation_cases"], 7)
        self.assertGreaterEqual(inventory["blocked_cases"], 16)
        self.assertFalse(inventory["customer_source"])

    def test_ten_gates_separate_subset_candidate_and_native_claims(self) -> None:
        result = build_pli_qualification(ROOT)
        statuses = {item["gate"]: item["status"] for item in result["qualification_gates"]}
        self.assertEqual(10, len(statuses))
        self.assertEqual("passed-bounded-synthetic", statuses["corpus-and-provenance"])
        self.assertEqual("passed-candidate-only", statuses["reproducible-candidate-build"])
        self.assertEqual("blocked-no-authorized-zos-evidence", statuses["ibm-compile-link-execute-and-equivalence"])

    def test_development_proof_does_not_promote_enterprise_pli(self) -> None:
        result = build_pli_qualification(ROOT)
        self.assertTrue(result["qualification_mechanism_ready"])
        self.assertTrue(result["development_ready"])
        for name in ("enterprise_pli_qualified", "native_compiler_qualified", "runtime_equivalent", "mainframe_equivalent", "production_ready"):
            self.assertFalse(result[name])

    def test_ledger_uses_all_five_governing_classes(self) -> None:
        ledger = build_pli_ledger(GRAPH)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual([], validate_pli_ledger(ledger))
        for name in COMPATIBILITY_CLASSES:
            self.assertGreater(ledger["statistics"][name], 0)

    def test_ledger_fails_closed_on_silent_policy_acceptance(self) -> None:
        changed = copy.deepcopy(build_pli_ledger(GRAPH))
        item = next(entry for entry in changed["entries"] if entry["classification"] == "policy-decision-required")
        item["decision"] = "accepted-by-default"
        self.assertIn("pli-ledger-policy-auto-accepted", validate_pli_ledger(seal(changed)))

    def test_rehashed_enterprise_overclaim_is_rejected(self) -> None:
        changed = copy.deepcopy(build_pli_qualification(ROOT))
        changed["enterprise_pli_qualified"] = True
        changed["production_ready"] = True
        errors = validate_pli_qualification(ROOT, seal(changed))
        self.assertIn("pli-qualification-drift", errors)
        self.assertIn("pli-qualification-overclaims-readiness", errors)

    def test_committed_artifacts_are_current(self) -> None:
        ledger = json.loads((ROOT / "readiness/pli/compatibility-ledger.json").read_text())
        qualification = json.loads((ROOT / "readiness/pli/qualification.json").read_text())
        self.assertEqual(build_pli_ledger(GRAPH), ledger)
        self.assertEqual(build_pli_qualification(ROOT), qualification)
        self.assertEqual([], validate_pli_qualification(ROOT, qualification))

    def test_schemas_are_frozen(self) -> None:
        for name in ("pli-compatibility-ledger.schema.json", "pli-qualification.schema.json"):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
