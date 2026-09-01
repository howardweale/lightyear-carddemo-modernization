from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_data.oracle_core_sql import (
    CORE_CASE_TARGET,
    CORE_DOMAIN_IDS,
    MODEL_FAILURE_CODES,
    build_oracle_core_sql_artifacts,
    execute_core_case,
    validate_oracle_core_sql_artifacts,
)
from lightyear_data.oracle_coverage import build_behavior_catalog


ROOT = Path(__file__).resolve().parents[1]


class OracleCoreSqlCoverageTests(unittest.TestCase):
    def test_exact_core_domain_behavior_and_case_counts(self) -> None:
        corpus = build_oracle_core_sql_artifacts(ROOT)["core-sql-corpus.json"]
        self.assertEqual(list(CORE_DOMAIN_IDS), corpus["domain_ids"])
        self.assertEqual(46, corpus["topic_family_count"])
        self.assertEqual(230, corpus["behavior_count"])
        self.assertEqual(CORE_CASE_TARGET, corpus["case_count"])
        self.assertEqual(
            {"types": 260, "globalization": 180, "expressions": 240, "queries": 240},
            corpus["cases_by_domain"],
        )

    def test_all_governed_core_case_ids_execute_once_and_pass(self) -> None:
        catalog = build_behavior_catalog(ROOT)
        expected_ids = {
            case["id"]
            for behavior in catalog["behaviors"]
            if behavior["domain_id"] in CORE_DOMAIN_IDS
            for case in behavior["case_specifications"]
        }
        corpus = build_oracle_core_sql_artifacts(ROOT)["core-sql-corpus.json"]
        actual_ids = [item["id"] for item in corpus["results"]]
        self.assertEqual(expected_ids, set(actual_ids))
        self.assertEqual(len(actual_ids), len(set(actual_ids)))
        self.assertEqual({"passed-bounded-model"}, {item["status"] for item in corpus["results"]})
        self.assertTrue(all(item["expected"] == item["observed"] for item in corpus["results"]))

    def test_each_topic_has_five_focuses_and_four_case_dimensions(self) -> None:
        results = build_oracle_core_sql_artifacts(ROOT)["core-sql-corpus.json"]["results"]
        topics = sorted({item["topic"] for item in results})
        for topic in topics:
            selected = [item for item in results if item["topic"] == topic]
            self.assertEqual(20, len(selected), topic)
            self.assertEqual(5, len({item["focus"] for item in selected}), topic)
            self.assertEqual(
                {"canonical", "null-boundary", "session-version", "failure-recovery"},
                {item["dimension"] for item in selected},
                topic,
            )

    def test_contract_expectation_is_independent_from_model_failure_mapping(self) -> None:
        with patch.dict(MODEL_FAILURE_CODES, {"number": "ORA-20999"}):
            expected, observed = execute_core_case(
                "number", "failure and diagnostic semantics", "canonical"
            )
        self.assertEqual({"error": "ORA-01438"}, expected["focus"])
        self.assertEqual({"error": "ORA-20999"}, observed["focus"])
        self.assertNotEqual(expected, observed)

    def test_receipt_deduplicates_bootstrap_overlap_and_keeps_claims_false(self) -> None:
        receipt = build_oracle_core_sql_artifacts(ROOT)["core-sql.receipt.json"]
        self.assertEqual(230, receipt["core_behavior_verified_count"])
        self.assertEqual(920, receipt["catalog_case_verified_count"])
        self.assertEqual(8, receipt["bootstrap_behavior_count"])
        self.assertEqual(24, receipt["bootstrap_case_execution_count"])
        self.assertEqual(233, receipt["bounded_model_verified_behavior_count"])
        self.assertEqual(944, receipt["bounded_model_evidence_record_count"])
        self.assertEqual(1080, receipt["remaining_catalog_case_count"])
        for name in (
            "native_oracle_execution_observed", "native_oracle_conformance",
            "idempiere_application_equivalence", "cloudbank_mapping_complete", "migration_complete",
            "production_ready",
        ):
            self.assertFalse(receipt[name], name)

    def test_native_plan_requires_authorized_19c_and_26ai_execution(self) -> None:
        plan = build_oracle_core_sql_artifacts(ROOT)["native-execution-plan.json"]
        self.assertEqual(["19c", "26ai"], plan["required_database_versions"])
        self.assertEqual(230, plan["required_behavior_count"])
        self.assertEqual(920, plan["required_case_count"])
        self.assertTrue(plan["authorization_required"])
        self.assertFalse(plan["native_oracle_execution_observed"])
        self.assertFalse(plan["native_oracle_conformance"])

    def test_rehashed_overclaim_and_committed_drift_fail_closed(self) -> None:
        artifacts = build_oracle_core_sql_artifacts(ROOT)
        changed = copy.deepcopy(artifacts["core-sql.receipt.json"])
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
            output_root = project_root / "data-modernization/oracle-core-sql-coverage"
            output_root.mkdir(parents=True)
            for name, payload in artifacts.items():
                path = output_root / name
                if name.endswith(".json"):
                    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                else:
                    path.write_text(payload, encoding="utf-8")
            (output_root / "core-sql.receipt.json").write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            errors = validate_oracle_core_sql_artifacts(project_root)
            self.assertIn("oracle-core-sql-artifact-drift:core-sql.receipt.json", errors)

    def test_cli_schemas_and_committed_artifacts_are_deterministic(self) -> None:
        self.assertEqual([], validate_oracle_core_sql_artifacts(ROOT))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "lightyear_data",
                "verify-oracle-core-sql-coverage",
                "--project-root",
                str(ROOT),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(230, payload["core_behavior_verified_count"])
        self.assertEqual(920, payload["catalog_case_verified_count"])
        for name in (
            "oracle-core-sql-corpus.schema.json",
            "oracle-core-sql-coverage-receipt.schema.json",
        ):
            schema = json.loads((ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
