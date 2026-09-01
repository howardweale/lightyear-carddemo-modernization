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
from lightyear_data.oracle_schema_structured import (
    BEHAVIOR_TARGET,
    CASE_TARGET,
    CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
    CUMULATIVE_CATALOG_CASE_TARGET,
    DOMAIN_IDS,
    MODEL_FAILURE_CODES,
    build_oracle_schema_structured_artifacts,
    execute_schema_structured_case,
    validate_oracle_schema_structured_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class OracleSchemaStructuredCoverageTests(unittest.TestCase):
    def test_exact_topic_behavior_and_case_counts(self) -> None:
        corpus = build_oracle_schema_structured_artifacts(ROOT)["schema-structured-corpus.json"]
        self.assertEqual(list(DOMAIN_IDS), corpus["domain_ids"])
        self.assertEqual(24, corpus["topic_family_count"])
        self.assertEqual(BEHAVIOR_TARGET, corpus["behavior_count"])
        self.assertEqual(CASE_TARGET, corpus["case_count"])
        self.assertEqual(
            {"schema-dml": 200, "schema-objects": 140, "structured-data": 140},
            corpus["cases_by_domain"],
        )
        self.assertEqual({20}, set(corpus["cases_by_topic"].values()))

    def test_all_governed_case_ids_execute_once_and_pass(self) -> None:
        catalog = build_behavior_catalog(ROOT)
        expected_ids = {
            case["id"]
            for behavior in catalog["behaviors"]
            if behavior["domain_id"] in DOMAIN_IDS
            for case in behavior["case_specifications"]
        }
        corpus = build_oracle_schema_structured_artifacts(ROOT)["schema-structured-corpus.json"]
        actual_ids = [item["id"] for item in corpus["results"]]
        self.assertEqual(expected_ids, set(actual_ids))
        self.assertEqual(len(actual_ids), len(set(actual_ids)))
        self.assertEqual({"passed-bounded-model"}, {item["status"] for item in corpus["results"]})
        self.assertTrue(all(item["expected"] == item["observed"] for item in corpus["results"]))

    def test_each_topic_has_five_focuses_and_four_case_dimensions(self) -> None:
        results = build_oracle_schema_structured_artifacts(ROOT)["schema-structured-corpus.json"][
            "results"
        ]
        for topic in sorted({item["topic"] for item in results}):
            selected = [item for item in results if item["topic"] == topic]
            self.assertEqual(20, len(selected), topic)
            self.assertEqual(5, len({item["focus"] for item in selected}), topic)
            self.assertEqual(
                {"canonical", "null-boundary", "session-version", "failure-recovery"},
                {item["dimension"] for item in selected},
                topic,
            )

    def test_contract_expectations_are_independent_from_executed_model(self) -> None:
        with patch.dict(MODEL_FAILURE_CODES, {"json": "ORA-20999"}):
            expected, observed = execute_schema_structured_case(
                "json", "failure and diagnostic semantics", "canonical"
            )
        self.assertEqual({"error": "ORA-40441"}, expected["focus"])
        self.assertEqual({"error": "ORA-20999"}, observed["focus"])
        self.assertNotEqual(expected, observed)
        with patch(
            "lightyear_data.oracle_schema_structured._null_policy",
            return_value="mutated-observation",
        ):
            expected, observed = execute_schema_structured_case(
                "blob", "null and absence semantics", "canonical"
            )
        self.assertEqual(
            "null-lob-empty-lob-and-zero-length-lob-remain-distinct", expected["focus"]
        )
        self.assertEqual("mutated-observation", observed["focus"])

    def test_high_risk_boundaries_have_concrete_observations(self) -> None:
        expectations = {
            "merge": {"updated_ids": [2], "inserted_ids": [3], "deleted_ids": [4]},
            "defaults": {
                "omitted_value": "STANDARD",
                "explicit_null_standard": None,
                "explicit_null_default_on_null": "ON_NULL",
            },
            "partitioning": {
                "range": {"2024-12-31": "P2024", "2025-01-01": "PMAX"},
                "list": {"UK": "P_UK", "US": "P_US"},
                "hash_partition_count": 4,
            },
            "json": {
                "account_id": 7,
                "status_is_json_null": True,
                "missing_path_exists": False,
                "generated_tags": ["a", "b"],
            },
            "json-datatype": {
                "19c": "native-json-datatype-unavailable",
                "26ai": "native-json-datatype-available",
                "version_delta_required": True,
            },
        }
        for topic, value in expectations.items():
            expected, observed = execute_schema_structured_case(
                topic, "canonical semantics", "canonical"
            )
            self.assertEqual(value, expected["focus"])
            self.assertEqual(expected, observed)

    def test_receipt_completes_catalog_and_deduplicates_all_bootstrap_ids(self) -> None:
        receipt = build_oracle_schema_structured_artifacts(ROOT)[
            "schema-structured.receipt.json"
        ]
        self.assertEqual(50, receipt["schema_dml_behavior_verified_count"])
        self.assertEqual(35, receipt["schema_object_behavior_verified_count"])
        self.assertEqual(35, receipt["structured_data_behavior_verified_count"])
        self.assertEqual(120, receipt["schema_structured_behavior_verified_count"])
        self.assertEqual(480, receipt["schema_structured_case_verified_count"])
        self.assertEqual(500, receipt["catalog_behavior_verified_count"])
        self.assertEqual(CUMULATIVE_CATALOG_CASE_TARGET, receipt["catalog_case_verified_count"])
        self.assertEqual(
            CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
            receipt["bounded_model_verified_behavior_count"],
        )
        self.assertEqual(2024, receipt["bounded_model_evidence_record_count"])
        self.assertEqual(0, receipt["remaining_catalog_case_count"])
        self.assertTrue(receipt["all_catalog_cases_implemented"])
        self.assertTrue(receipt["bounded_catalog_execution_complete"])
        for name in (
            "native_oracle_execution_observed",
            "native_oracle_conformance",
            "live_schema_or_dml_observed",
            "live_lob_json_xml_or_object_observed",
            "idempiere_application_equivalence",
            "cloudbank_mapping_complete",
            "migration_complete",
            "production_ready",
        ):
            self.assertFalse(receipt[name], name)

    def test_native_plan_requires_schema_storage_and_version_delta_evidence(self) -> None:
        plan = build_oracle_schema_structured_artifacts(ROOT)["native-execution-plan.json"]
        self.assertEqual(["19c", "26ai"], plan["required_database_versions"])
        self.assertEqual(120, plan["required_behavior_count"])
        self.assertEqual(480, plan["required_case_count"])
        self.assertIn("pre_and_post_schema_metadata", plan["required_schema_dml_observations"])
        self.assertIn("lob_storage_attributes", plan["required_structured_data_observations"])
        self.assertIn("19c_native_json_datatype_unavailable", plan["required_version_deltas"])
        self.assertIn("pre_state_hash", plan["required_receipt_fields"])
        self.assertTrue(plan["authorization_required"])
        self.assertFalse(plan["native_oracle_execution_observed"])

    def test_rehashed_overclaim_and_committed_drift_fail_closed_in_temp_tree(self) -> None:
        artifacts = build_oracle_schema_structured_artifacts(ROOT)
        changed = copy.deepcopy(artifacts["schema-structured.receipt.json"])
        changed["native_oracle_execution_observed"] = True
        changed["native_oracle_conformance"] = True
        changed["live_lob_json_xml_or_object_observed"] = True
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
            for relative in (
                "data-modernization/oracle-core-sql-coverage",
                "data-modernization/oracle-plsql-coverage",
                "data-modernization/oracle-transaction-cdc-coverage",
            ):
                shutil.copytree(ROOT / relative, project_root / relative)
            output_root = project_root / "data-modernization/oracle-schema-structured-coverage"
            output_root.mkdir(parents=True)
            for name, payload in artifacts.items():
                path = output_root / name
                if name.endswith(".json"):
                    path.write_text(
                        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                else:
                    path.write_text(payload, encoding="utf-8")
            (output_root / "schema-structured.receipt.json").write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            errors = validate_oracle_schema_structured_artifacts(project_root)
            self.assertIn(
                "oracle-schema-structured-artifact-drift:schema-structured.receipt.json", errors
            )
            self.assertIn("oracle-schema-structured-overclaim:native_oracle_conformance", errors)
            self.assertIn(
                "oracle-schema-structured-overclaim:live_lob_json_xml_or_object_observed", errors
            )

    def test_cli_schemas_and_committed_artifacts_are_deterministic(self) -> None:
        self.assertEqual([], validate_oracle_schema_structured_artifacts(ROOT))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "lightyear_data",
                "verify-oracle-schema-structured-coverage",
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
        self.assertEqual(120, payload["schema_structured_behavior_verified_count"])
        self.assertEqual(480, payload["schema_structured_case_verified_count"])
        self.assertEqual(500, payload["bounded_model_verified_behavior_count"])
        self.assertTrue(payload["bounded_catalog_execution_complete"])
        for name in (
            "oracle-schema-structured-corpus.schema.json",
            "oracle-schema-structured-coverage-receipt.schema.json",
        ):
            schema = json.loads(
                (ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8")
            )
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
