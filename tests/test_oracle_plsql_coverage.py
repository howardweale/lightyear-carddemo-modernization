from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_data.oracle_coverage import build_behavior_catalog
from lightyear_data.oracle_plsql import (
    CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
    CUMULATIVE_CATALOG_CASE_TARGET,
    MODEL_FAILURE_CODES,
    PLSQL_CASE_TARGET,
    build_oracle_plsql_artifacts,
    execute_plsql_case,
    validate_oracle_plsql_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class OraclePlsqlCoverageTests(unittest.TestCase):
    def test_exact_plsql_topic_behavior_and_case_counts(self) -> None:
        corpus = build_oracle_plsql_artifacts(ROOT)["plsql-corpus.json"]
        self.assertEqual("plsql", corpus["domain_id"])
        self.assertEqual(16, corpus["topic_family_count"])
        self.assertEqual(80, corpus["behavior_count"])
        self.assertEqual(PLSQL_CASE_TARGET, corpus["case_count"])
        self.assertEqual({20}, set(corpus["cases_by_topic"].values()))

    def test_all_governed_plsql_case_ids_execute_once_and_pass(self) -> None:
        catalog = build_behavior_catalog(ROOT)
        expected_ids = {
            case["id"]
            for behavior in catalog["behaviors"]
            if behavior["domain_id"] == "plsql"
            for case in behavior["case_specifications"]
        }
        corpus = build_oracle_plsql_artifacts(ROOT)["plsql-corpus.json"]
        actual_ids = [item["id"] for item in corpus["results"]]
        self.assertEqual(expected_ids, set(actual_ids))
        self.assertEqual(len(actual_ids), len(set(actual_ids)))
        self.assertEqual({"passed-bounded-model"}, {item["status"] for item in corpus["results"]})
        self.assertTrue(all(item["expected"] == item["observed"] for item in corpus["results"]))

    def test_each_topic_has_five_focuses_and_four_case_dimensions(self) -> None:
        results = build_oracle_plsql_artifacts(ROOT)["plsql-corpus.json"]["results"]
        for topic in sorted({item["topic"] for item in results}):
            selected = [item for item in results if item["topic"] == topic]
            self.assertEqual(20, len(selected), topic)
            self.assertEqual(5, len({item["focus"] for item in selected}), topic)
            self.assertEqual(
                {"canonical", "null-boundary", "session-version", "failure-recovery"},
                {item["dimension"] for item in selected},
                topic,
            )

    def test_contract_expectation_is_independent_from_model_diagnostic(self) -> None:
        with patch.dict(MODEL_FAILURE_CODES, {"select-into": "ORA-20999"}):
            expected, observed = execute_plsql_case(
                "select-into", "failure and diagnostic semantics", "canonical"
            )
        self.assertEqual({"error": "ORA-01403"}, expected["focus"])
        self.assertEqual({"error": "ORA-20999"}, observed["focus"])
        self.assertNotEqual(expected, observed)

    def test_high_risk_plsql_boundaries_have_concrete_observations(self) -> None:
        expectations = {
            "packages": {"session_calls": [1, 2, 3], "new_session_state": 0},
            "forall": {
                "applied": [1, 2],
                "errors": [{"index": 2, "code": "ORA-02290"}],
            },
            "dynamic-sql": {"statement_kind": "UPDATE", "affected_rows": 2, "bind_count": 1},
            "autonomous": {
                "business_rows_after_outer_rollback": [],
                "autonomous_audit_rows": ["audit-committed"],
            },
        }
        for topic, value in expectations.items():
            expected, observed = execute_plsql_case(topic, "canonical semantics", "canonical")
            self.assertEqual(value, expected["focus"])
            self.assertEqual(expected, observed)

    def test_receipt_deduplicates_overlap_and_reports_cumulative_counts(self) -> None:
        receipt = build_oracle_plsql_artifacts(ROOT)["plsql.receipt.json"]
        self.assertEqual(80, receipt["plsql_behavior_verified_count"])
        self.assertEqual(320, receipt["plsql_case_verified_count"])
        self.assertEqual(310, receipt["catalog_behavior_verified_count"])
        self.assertEqual(CUMULATIVE_CATALOG_CASE_TARGET, receipt["catalog_case_verified_count"])
        self.assertEqual(
            CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
            receipt["bounded_model_verified_behavior_count"],
        )
        self.assertEqual(1264, receipt["bounded_model_evidence_record_count"])
        self.assertEqual(760, receipt["remaining_catalog_case_count"])
        for name in (
            "native_oracle_execution_observed", "native_oracle_conformance",
            "idempiere_application_equivalence", "cloudbank_mapping_complete",
            "migration_complete", "production_ready",
        ):
            self.assertFalse(receipt[name], name)

    def test_native_plan_requires_plsql_session_and_side_effect_evidence(self) -> None:
        plan = build_oracle_plsql_artifacts(ROOT)["native-execution-plan.json"]
        self.assertEqual(["19c", "26ai"], plan["required_database_versions"])
        self.assertEqual(80, plan["required_behavior_count"])
        self.assertEqual(320, plan["required_case_count"])
        self.assertIn("package_state_reset", plan["required_session_controls"])
        self.assertIn("observed_side_effects", plan["required_receipt_fields"])
        self.assertTrue(plan["authorization_required"])
        self.assertFalse(plan["native_oracle_execution_observed"])

    def test_rehashed_overclaim_and_committed_drift_fail_closed_in_temp_tree(self) -> None:
        artifacts = build_oracle_plsql_artifacts(ROOT)
        changed = copy.deepcopy(artifacts["plsql.receipt.json"])
        changed["native_oracle_execution_observed"] = True
        changed["native_oracle_conformance"] = True
        changed = seal(changed)
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            for relative in (
                "data-modernization/oracle-dialect-conformance/fixture-catalog.json",
                "reference-estates/idempiere/oracle-semantic-fixtures.json",
            ):
                target = project_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            shutil.copytree(
                ROOT / "data-modernization/oracle-core-sql-coverage",
                project_root / "data-modernization/oracle-core-sql-coverage",
            )
            output_root = project_root / "data-modernization/oracle-plsql-coverage"
            output_root.mkdir(parents=True)
            for name, payload in artifacts.items():
                path = output_root / name
                if name.endswith(".json"):
                    path.write_text(
                        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                else:
                    path.write_text(payload, encoding="utf-8")
            (output_root / "plsql.receipt.json").write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            errors = validate_oracle_plsql_artifacts(project_root)
            self.assertIn("oracle-plsql-artifact-drift:plsql.receipt.json", errors)
            self.assertIn("oracle-plsql-overclaim:native_oracle_conformance", errors)

    def test_cli_schemas_and_committed_artifacts_are_deterministic(self) -> None:
        self.assertEqual([], validate_oracle_plsql_artifacts(ROOT))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [
                sys.executable, "-m", "lightyear_data", "verify-oracle-plsql-coverage",
                "--project-root", str(ROOT),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(80, payload["plsql_behavior_verified_count"])
        self.assertEqual(320, payload["plsql_case_verified_count"])
        self.assertEqual(312, payload["bounded_model_verified_behavior_count"])
        for name in (
            "oracle-plsql-corpus.schema.json",
            "oracle-plsql-coverage-receipt.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
