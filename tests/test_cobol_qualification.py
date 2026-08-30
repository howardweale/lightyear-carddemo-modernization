from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_readiness.cobol import (
    build_cobol_ledger,
    build_cobol_qualification,
    validate_cobol_ledger,
    validate_cobol_qualification,
)


ROOT = Path(__file__).resolve().parents[1]
GRAPH_RECEIPT = json.loads((ROOT / "knowledge/graph.receipt.json").read_text())


class CobolQualificationTests(unittest.TestCase):
    def test_inventory_is_bound_to_the_canonical_graph(self) -> None:
        result = build_cobol_qualification(ROOT)
        inventory = result["inventory"]
        self.assertGreaterEqual(inventory["programs"], 50)
        self.assertGreaterEqual(inventory["paragraphs"], 900)
        self.assertGreaterEqual(inventory["copybooks"], 70)
        self.assertGreaterEqual(inventory["fields"], 7000)
        self.assertEqual(GRAPH_RECEIPT["content_sha256"], result["bindings"]["graph_content_sha256"])

    def test_nine_gates_separate_static_development_and_native_claims(self) -> None:
        result = build_cobol_qualification(ROOT)
        statuses = {item["gate"]: item["status"] for item in result["qualification_gates"]}
        self.assertEqual(9, len(statuses))
        self.assertEqual("passed-static", statuses["estate-inventory"])
        self.assertEqual("passed-bounded-development", statuses["data-layout-and-numeric-semantics"])
        self.assertEqual("blocked-no-authorized-zos-evidence", statuses["native-compile-link-execute"])

    def test_planning_scope_does_not_promote_native_or_runtime_equivalence(self) -> None:
        result = build_cobol_qualification(ROOT)
        self.assertTrue(result["qualification_mechanism_ready"])
        self.assertTrue(result["development_ready"])
        self.assertFalse(result["native_compiler_qualified"])
        self.assertFalse(result["runtime_equivalent"])
        self.assertFalse(result["mainframe_equivalent"])
        self.assertFalse(result["production_ready"])

    def test_ledger_uses_exactly_the_five_governing_classes(self) -> None:
        ledger = build_cobol_ledger(GRAPH_RECEIPT)
        self.assertEqual(set(COMPATIBILITY_CLASSES), set(ledger["classifications"]))
        self.assertEqual([], validate_cobol_ledger(ledger))
        self.assertGreater(ledger["statistics"]["normalized-equivalent"], 0)
        self.assertGreater(ledger["statistics"]["policy-decision-required"], 0)
        self.assertGreater(ledger["statistics"]["unsupported"], 0)
        self.assertTrue(ledger["qualification_blocked"])

    def test_ledger_rejects_silent_policy_acceptance(self) -> None:
        changed = copy.deepcopy(build_cobol_ledger(GRAPH_RECEIPT))
        item = next(entry for entry in changed["entries"] if entry["classification"] == "policy-decision-required")
        item["decision"] = "accepted-by-default"
        changed = seal(changed)
        self.assertIn("cobol-ledger-policy-auto-accepted", validate_cobol_ledger(changed))

    def test_rehashed_readiness_overclaim_is_rejected(self) -> None:
        changed = copy.deepcopy(build_cobol_qualification(ROOT))
        changed["native_compiler_qualified"] = True
        changed["mainframe_equivalent"] = True
        changed = seal(changed)
        errors = validate_cobol_qualification(ROOT, changed)
        self.assertIn("cobol-qualification-drift", errors)
        self.assertIn("cobol-qualification-overclaims-readiness", errors)

    def test_committed_artifacts_are_current(self) -> None:
        ledger = json.loads((ROOT / "readiness/cobol/compatibility-ledger.json").read_text())
        qualification = json.loads((ROOT / "readiness/cobol/qualification.json").read_text())
        self.assertEqual(build_cobol_ledger(GRAPH_RECEIPT), ledger)
        self.assertEqual(build_cobol_qualification(ROOT), qualification)
        self.assertEqual([], validate_cobol_qualification(ROOT, qualification))

    def test_schemas_are_frozen(self) -> None:
        for name in ("cobol-compatibility-ledger.schema.json", "cobol-qualification.schema.json"):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
