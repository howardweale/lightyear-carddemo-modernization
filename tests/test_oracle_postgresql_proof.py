from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lightyear_common.io import write_json
from lightyear_data.contracts import seal
from lightyear_data.oracle_postgres_proof import (
    build_oracle_postgresql_proof,
    validate_oracle_postgresql_proof,
)


ROOT = Path(__file__).resolve().parents[1]


class OraclePostgreSQLProofTests(unittest.TestCase):
    def test_eight_claims_are_progressive_and_independent(self) -> None:
        proof = build_oracle_postgresql_proof(ROOT)
        self.assertEqual(list(range(1, 9)), [item["gate"] for item in proof["gates"]])
        self.assertEqual(
            [
                "schema-translation", "data-conversion", "constraints-and-indexes",
                "query-equivalence", "transaction-behavior", "cdc-and-resume",
                "cutover-and-rollback", "stored-logic",
            ],
            [item["claim"] for item in proof["gates"]],
        )

    def test_development_mechanisms_do_not_overclaim_live_qualification(self) -> None:
        proof = build_oracle_postgresql_proof(ROOT)
        statuses = {item["gate"]: item["status"] for item in proof["gates"]}
        self.assertEqual("policy-decision-required", statuses[5])
        self.assertEqual("passed-simulated", statuses[6])
        self.assertEqual("passed-simulated", statuses[7])
        self.assertEqual("passed-bounded-subset-with-open-gates", statuses[8])
        self.assertFalse(proof["database_migration_complete"])
        self.assertFalse(proof["production_ready"])

    def test_stored_logic_has_its_own_fail_closed_gate(self) -> None:
        stored = build_oracle_postgresql_proof(ROOT)["gates"][7]
        self.assertTrue(stored["evidence"]["qualification_core_ready"])
        self.assertFalse(stored["evidence"]["inventory_complete"])
        self.assertFalse(stored["evidence"]["stored_logic_complete"])
        self.assertTrue(stored["evidence"]["supported_procedure_subset_qualified"])

    def test_canonical_proof_is_current_and_valid(self) -> None:
        expected = build_oracle_postgresql_proof(ROOT)
        actual = json.loads((ROOT / "data-modernization/oracle-postgresql-proof/authfrds.proof.json").read_text())
        self.assertEqual(expected, actual)
        self.assertEqual([], validate_oracle_postgresql_proof(ROOT, actual))

    def test_tamper_and_completion_promotion_are_rejected(self) -> None:
        proof = build_oracle_postgresql_proof(ROOT)
        changed = copy.deepcopy(proof)
        changed["database_migration_complete"] = True
        changed = seal(changed)
        errors = validate_oracle_postgresql_proof(ROOT, changed)
        self.assertIn("oracle-postgresql-proof-drift", errors)
        self.assertIn("oracle-postgresql-proof-overclaims-completion", errors)

    def test_schema_is_frozen_and_parseable(self) -> None:
        schema = json.loads((ROOT / "data-modernization/schema/oracle-postgresql-proof.schema.json").read_text())
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
