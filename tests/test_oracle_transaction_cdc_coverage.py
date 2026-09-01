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
from lightyear_data.oracle_transaction_cdc import (
    BEHAVIOR_TARGET,
    CASE_TARGET,
    CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
    CUMULATIVE_CATALOG_CASE_TARGET,
    DOMAIN_IDS,
    MODEL_FAILURE_CODES,
    build_oracle_transaction_cdc_artifacts,
    execute_transaction_cdc_case,
    validate_oracle_transaction_cdc_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class OracleTransactionCdcCoverageTests(unittest.TestCase):
    def test_exact_topic_behavior_and_case_counts(self) -> None:
        corpus = build_oracle_transaction_cdc_artifacts(ROOT)["transaction-cdc-corpus.json"]
        self.assertEqual(list(DOMAIN_IDS), corpus["domain_ids"])
        self.assertEqual(14, corpus["topic_family_count"])
        self.assertEqual(BEHAVIOR_TARGET, corpus["behavior_count"])
        self.assertEqual(CASE_TARGET, corpus["case_count"])
        self.assertEqual({"transactions": 180, "operations": 100}, corpus["cases_by_domain"])
        self.assertEqual({20}, set(corpus["cases_by_topic"].values()))

    def test_all_governed_case_ids_execute_once_and_pass(self) -> None:
        catalog = build_behavior_catalog(ROOT)
        expected_ids = {
            case["id"]
            for behavior in catalog["behaviors"]
            if behavior["domain_id"] in DOMAIN_IDS
            for case in behavior["case_specifications"]
        }
        corpus = build_oracle_transaction_cdc_artifacts(ROOT)["transaction-cdc-corpus.json"]
        actual_ids = [item["id"] for item in corpus["results"]]
        self.assertEqual(expected_ids, set(actual_ids))
        self.assertEqual(len(actual_ids), len(set(actual_ids)))
        self.assertEqual({"passed-bounded-model"}, {item["status"] for item in corpus["results"]})
        self.assertTrue(all(item["expected"] == item["observed"] for item in corpus["results"]))

    def test_each_topic_has_five_focuses_and_four_case_dimensions(self) -> None:
        results = build_oracle_transaction_cdc_artifacts(ROOT)["transaction-cdc-corpus.json"][
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
        with patch.dict(MODEL_FAILURE_CODES, {"deadlock": "ORA-20999"}):
            expected, observed = execute_transaction_cdc_case(
                "deadlock", "failure and diagnostic semantics", "canonical"
            )
        self.assertEqual({"error": "ORA-00060"}, expected["focus"])
        self.assertEqual({"error": "ORA-20999"}, observed["focus"])
        self.assertNotEqual(expected, observed)
        with patch(
            "lightyear_data.oracle_transaction_cdc._null_policy",
            return_value="mutated-observation",
        ):
            expected, observed = execute_transaction_cdc_case(
                "logminer", "null and absence semantics", "canonical"
            )
        self.assertEqual(
            "supplemental-data-absence-is-distinct-from-sql-null", expected["focus"]
        )
        self.assertEqual("mutated-observation", observed["focus"])

    def test_high_risk_boundaries_have_concrete_observations(self) -> None:
        expectations = {
            "savepoint": {"after_partial_rollback": [1], "transaction_open": True},
            "serializable": {
                "initial": "v1", "conflict": "ORA-08177", "snapshot_scope": "transaction"
            },
            "deadlock": {
                "victim_error": "ORA-00060",
                "victim_statement_rolled_back": True,
                "transaction_usable": True,
            },
            "logminer": {
                "ordered_scns": [101, 102],
                "operations": ["INSERT", "UPDATE"],
                "resume_exclusive_after_scn": 102,
            },
            "privileges": {
                "select_before_grant": False,
                "select_after_grant": True,
                "select_after_revoke": False,
            },
        }
        for topic, value in expectations.items():
            expected, observed = execute_transaction_cdc_case(
                topic, "canonical semantics", "canonical"
            )
            self.assertEqual(value, expected["focus"])
            self.assertEqual(expected, observed)

    def test_receipt_deduplicates_overlap_and_reports_cumulative_counts(self) -> None:
        receipt = build_oracle_transaction_cdc_artifacts(ROOT)["transaction-cdc.receipt.json"]
        self.assertEqual(45, receipt["transaction_behavior_verified_count"])
        self.assertEqual(25, receipt["operations_behavior_verified_count"])
        self.assertEqual(70, receipt["transaction_cdc_behavior_verified_count"])
        self.assertEqual(280, receipt["transaction_cdc_case_verified_count"])
        self.assertEqual(380, receipt["catalog_behavior_verified_count"])
        self.assertEqual(CUMULATIVE_CATALOG_CASE_TARGET, receipt["catalog_case_verified_count"])
        self.assertEqual(
            CUMULATIVE_BOUNDED_BEHAVIOR_TARGET,
            receipt["bounded_model_verified_behavior_count"],
        )
        self.assertEqual(1544, receipt["bounded_model_evidence_record_count"])
        self.assertEqual(480, receipt["remaining_catalog_case_count"])
        for name in (
            "native_oracle_execution_observed",
            "native_oracle_conformance",
            "live_concurrency_observed",
            "live_redo_or_logminer_observed",
            "live_privilege_enforcement_observed",
            "idempiere_application_equivalence",
            "cloudbank_mapping_complete",
            "migration_complete",
            "production_ready",
        ):
            self.assertFalse(receipt[name], name)

    def test_native_plan_requires_concurrency_cdc_and_security_evidence(self) -> None:
        plan = build_oracle_transaction_cdc_artifacts(ROOT)["native-execution-plan.json"]
        self.assertEqual(["19c", "26ai"], plan["required_database_versions"])
        self.assertEqual(70, plan["required_behavior_count"])
        self.assertEqual(280, plan["required_case_count"])
        self.assertIn("two_or_more_session_identities", plan["required_session_controls"])
        self.assertIn("deadlock_victim_and_rollback_scope", plan["required_concurrency_observations"])
        self.assertIn("resume_checkpoint", plan["required_cdc_observations"])
        self.assertIn("oracle_error_stack", plan["required_receipt_fields"])
        self.assertTrue(plan["authorization_required"])
        self.assertTrue(plan["logminer_privileges_required"])
        self.assertFalse(plan["native_oracle_execution_observed"])

    def test_rehashed_overclaim_and_committed_drift_fail_closed_in_temp_tree(self) -> None:
        artifacts = build_oracle_transaction_cdc_artifacts(ROOT)
        changed = copy.deepcopy(artifacts["transaction-cdc.receipt.json"])
        changed["native_oracle_execution_observed"] = True
        changed["native_oracle_conformance"] = True
        changed["live_redo_or_logminer_observed"] = True
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
            ):
                shutil.copytree(ROOT / relative, project_root / relative)
            output_root = project_root / "data-modernization/oracle-transaction-cdc-coverage"
            output_root.mkdir(parents=True)
            for name, payload in artifacts.items():
                path = output_root / name
                if name.endswith(".json"):
                    path.write_text(
                        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                else:
                    path.write_text(payload, encoding="utf-8")
            (output_root / "transaction-cdc.receipt.json").write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            errors = validate_oracle_transaction_cdc_artifacts(project_root)
            self.assertIn(
                "oracle-transaction-cdc-artifact-drift:transaction-cdc.receipt.json", errors
            )
            self.assertIn("oracle-transaction-cdc-overclaim:native_oracle_conformance", errors)
            self.assertIn(
                "oracle-transaction-cdc-overclaim:live_redo_or_logminer_observed", errors
            )

    def test_cli_schemas_and_committed_artifacts_are_deterministic(self) -> None:
        self.assertEqual([], validate_oracle_transaction_cdc_artifacts(ROOT))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "lightyear_data",
                "verify-oracle-transaction-cdc-coverage",
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
        self.assertEqual(70, payload["transaction_cdc_behavior_verified_count"])
        self.assertEqual(280, payload["transaction_cdc_case_verified_count"])
        self.assertEqual(381, payload["bounded_model_verified_behavior_count"])
        for name in (
            "oracle-transaction-cdc-corpus.schema.json",
            "oracle-transaction-cdc-coverage-receipt.schema.json",
        ):
            schema = json.loads(
                (ROOT / "data-modernization/schema" / name).read_text(encoding="utf-8")
            )
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])


if __name__ == "__main__":
    unittest.main()
