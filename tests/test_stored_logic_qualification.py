from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.contracts import seal
from lightyear_data.stored_logic import (
    OBJECT_KINDS,
    QUALIFICATION_GATES,
    build_stored_logic_qualification,
    validate_stored_logic_qualification,
)


ROOT = Path(__file__).resolve().parents[1]


class StoredLogicQualificationTests(unittest.TestCase):
    def test_inventory_contract_covers_database_and_application_logic(self) -> None:
        result = build_stored_logic_qualification(ROOT)
        self.assertEqual(set(OBJECT_KINDS), set(result["inventory_contract"]["object_kinds"]))
        self.assertEqual(2, result["object_counts"]["application-sql"])
        self.assertFalse(result["inventory_contract"]["live_catalog_observed"])

    def test_all_seven_qualification_gates_are_independent(self) -> None:
        result = build_stored_logic_qualification(ROOT)
        self.assertEqual(list(QUALIFICATION_GATES), [item["gate"] for item in result["qualification_gates"]])
        self.assertEqual("passed-source-only", result["qualification_gates"][1]["status"])
        self.assertEqual("policy-decision-required", result["qualification_gates"][2]["status"])

    def test_application_sql_is_not_silently_declared_translated(self) -> None:
        result = build_stored_logic_qualification(ROOT)
        self.assertEqual({"INSERT", "UPDATE"}, {item["operation"] for item in result["objects"]})
        self.assertTrue(all(item["classification"] == "policy-decision-required" for item in result["objects"]))
        self.assertTrue(all(item["qualification_status"] == "not-qualified" for item in result["objects"]))

    def test_zero_catalog_objects_cannot_become_inventory_complete(self) -> None:
        result = build_stored_logic_qualification(ROOT)
        self.assertFalse(result["inventory_complete"])
        self.assertFalse(result["stored_logic_complete"])
        self.assertFalse(result["database_migration_complete"])
        self.assertFalse(result["production_ready"])

    def test_canonical_qualification_is_current(self) -> None:
        actual = json.loads((ROOT / "data-modernization/stored-logic/authfrds.qualification.json").read_text())
        self.assertEqual(build_stored_logic_qualification(ROOT), actual)
        self.assertEqual([], validate_stored_logic_qualification(ROOT, actual))

    def test_rehashed_completion_overclaim_is_rejected(self) -> None:
        changed = copy.deepcopy(build_stored_logic_qualification(ROOT))
        changed["inventory_complete"] = True
        changed["stored_logic_complete"] = True
        changed = seal(changed)
        errors = validate_stored_logic_qualification(ROOT, changed)
        self.assertIn("stored-logic-qualification-drift", errors)
        self.assertIn("stored-logic-qualification-overclaims-completion", errors)

    def test_schema_is_frozen(self) -> None:
        schema = json.loads((ROOT / "data-modernization/schema/stored-logic-qualification.schema.json").read_text())
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
