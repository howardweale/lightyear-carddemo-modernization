from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_native_wave import RECEIPT_TYPE as MS60_RECEIPT_TYPE
from lightyear_data.cloudbank_oracle_equivalence import (
    EXPECTED_TESTS,
    OBSERVATION_SHA256,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    TEST_PATCHES,
    build_artifacts,
    changed_paths,
    compatibility_ledger,
    equivalence_contract,
    execute_equivalence,
    execution_plan,
    materialize_workspaces,
    observation_contract,
    readiness_receipt,
    validate_artifacts,
    validate_execution_receipt,
)
from lightyear_data.cloudbank_production_qualification import (
    RECEIPT_TYPE as MS57_RECEIPT_TYPE,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cloudbank-upstream"
KEY = "unit-test-cloudbank-oracle-equivalence-key"
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def ms57_receipt() -> dict[str, object]:
    return {
        "receipt_type": MS57_RECEIPT_TYPE,
        "content_sha256": HEX_A,
        "oracle_image_id_sha256": HEX_B,
        "postgresql_image_id_sha256": HEX_C,
    }


def ms60_receipt() -> dict[str, object]:
    return {
        "receipt_type": MS60_RECEIPT_TYPE,
        "content_sha256": HEX_B,
        "postgresql_image_id_sha256": HEX_C,
    }


def passed_lane(name: str, image_id: str) -> dict[str, object]:
    return {
        "lane": name,
        "status": "passed",
        "tests": EXPECTED_TESTS,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "maven_exit_code": 0,
        "database_image_id_sha256": image_id,
        "observation_sha256": OBSERVATION_SHA256,
        "marker_stdout_count": 1,
        "marker_report_count": 1,
        "test_reports_present": 2,
        "failed_tests": [],
        "failure_phase": None,
        "stdout_sha256": HEX_A,
        "stderr_sha256": HEX_B,
        "raw_output_persisted": False,
        "synthetic_data_only": True,
    }


class CloudBankOracleEquivalenceTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        readiness = readiness_receipt(ROOT)
        self.assertTrue(readiness["contract_complete"])
        self.assertFalse(readiness["native_oracle_lane_observed"])
        self.assertFalse(readiness["oracle_postgresql_equivalent"])
        self.assertFalse(readiness["production_ready"])

    def test_shared_contract_has_seven_exact_normalized_observations(self) -> None:
        contract = observation_contract()
        self.assertEqual(7, contract["scenario_count"])
        self.assertEqual(OBSERVATION_SHA256, contract["marker_sha256"])
        self.assertEqual("exact-normalized-observation-marker", contract["comparison_policy"])
        acceptance = equivalence_contract(ROOT)
        self.assertEqual(EXPECTED_TESTS, acceptance["tests_per_lane"])
        self.assertEqual(["oracle", "postgresql"], acceptance["required_lanes"])
        self.assertTrue(acceptance["eligible_claim"]["oracle_postgresql_equivalent"])
        self.assertFalse(
            acceptance["eligible_claim"]["exact_internal_implementation_equivalent"]
        )

    def test_plan_binds_all_four_isolated_test_templates(self) -> None:
        plan = execution_plan(ROOT)
        self.assertEqual(4, len(plan["patches"]))
        self.assertEqual(changed_paths(), sorted(item["path"] for item in plan["patches"]))
        self.assertEqual("sequential-database-lanes", plan["runtime_order"])
        for template in (ROOT / OUTPUT_ROOT / "patches").glob("*.java"):
            self.assertTrue(
                template.read_text(encoding="utf-8").startswith(
                    "// Copyright (c) 2023, Oracle and/or its affiliates.\n"
                )
            )

    def test_ledger_exposes_implementation_and_observation_differences(self) -> None:
        entries = {item["capability"]: item for item in compatibility_ledger()["entries"]}
        self.assertEqual(
            "intentional-implementation-change",
            entries["source-lra-compensation-target-atomic-rollback"]["classification"],
        )
        self.assertEqual(
            "observable-difference",
            entries["oracle-zero-amount-failure-journal"]["classification"],
        )
        self.assertEqual(
            "partially-observed",
            entries["source-transfer-http-runtime"]["classification"],
        )
        self.assertFalse(compatibility_ledger()["whole_application_equivalent"])

    @unittest.skipUnless(SOURCE.is_dir(), "pinned CloudBank source is unavailable")
    def test_materialization_preserves_source_and_creates_both_lanes(self) -> None:
        source_head = (SOURCE / ".git/HEAD").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            oracle, postgres = materialize_workspaces(ROOT, SOURCE, Path(directory) / "work")
            for lane, workspace in (("oracle", oracle), ("postgresql", postgres)):
                for relative in TEST_PATCHES[lane]:
                    self.assertTrue((workspace / relative).is_file())
            self.assertIn("oracle", str(oracle))
            self.assertIn("postgresql", str(postgres))
        self.assertEqual(source_head, (SOURCE / ".git/HEAD").read_bytes())

    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms57_receipt",
        return_value=[],
    )
    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms60_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_oracle_equivalence.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_oracle_equivalence.materialize_workspaces")
    def test_execution_closes_only_bounded_equivalence(
        self, materialize: object, _source: object, _ms60: object, _ms57: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = (output / "oracle", output / "postgresql")
            receipt = execute_equivalence(
                ROOT,
                ROOT,
                ms57_receipt(),
                ms60_receipt(),
                output,
                KEY,
                "unit-test",
                "ms61-unit-run",
                oracle_runner=lambda _workspace, image: passed_lane("oracle", image),
                postgres_runner=lambda _workspace, image: passed_lane("postgresql", image),
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["oracle_postgresql_equivalent"])
            self.assertTrue(receipt["customer_equivalence_inherited_from_ms57"])
            self.assertFalse(receipt["exact_internal_implementation_equivalent"])
            self.assertFalse(receipt["oracle_integrated_http_wave_observed"])
            self.assertFalse(receipt["production_identity_qualified"])
            self.assertFalse(receipt["whole_application_equivalent"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-oracle-equivalence-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-oracle-equivalence-receipt-claims-invalid", errors)

    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms57_receipt",
        return_value=[],
    )
    @patch(
        "lightyear_data.cloudbank_oracle_equivalence.validate_ms60_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_oracle_equivalence.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_oracle_equivalence.materialize_workspaces")
    def test_failed_comparison_writes_only_safe_aggregate_diagnostics(
        self, materialize: object, _source: object, _ms60: object, _ms57: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = (output / "oracle", output / "postgresql")
            failed = passed_lane("postgresql", HEX_C)
            failed["status"] = "failed"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_equivalence(
                    ROOT,
                    ROOT,
                    ms57_receipt(),
                    ms60_receipt(),
                    output,
                    KEY,
                    "unit-test",
                    "ms61-failed-run",
                    oracle_runner=lambda _workspace, image: passed_lane("oracle", image),
                    postgres_runner=lambda _workspace, _image: failed,
                )
            diagnostic = (output / "cloudbank-oracle-postgresql-equivalence.failure.json")
            text = diagnostic.read_text(encoding="utf-8")
            self.assertNotIn("synthetic-ms61-token", text)
            self.assertNotIn("raw_stdout", text)

    def test_launchers_schemas_and_verification_integration_exist(self) -> None:
        for relative in (
            "cloudbank-oracle-equivalence.sh",
            "cloudbank-oracle-equivalence.ps1",
            "tools/cloudbank_oracle_equivalence.py",
            "reference-estates/cloudbank/schema/oracle-postgresql-equivalence-readiness.schema.json",
            "reference-estates/cloudbank/schema/oracle-postgresql-equivalence-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        powershell = (ROOT / "cloudbank-oracle-equivalence.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-FactoryDarkPython", powershell)
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertIn("cloudbank-oracle-equivalence.sh materialize", workflow)
        self.assertIn("OracleAccountEquivalenceTests", workflow)
        self.assertIn("PostgreSqlAccountEquivalenceTests", workflow)


if __name__ == "__main__":
    unittest.main()
