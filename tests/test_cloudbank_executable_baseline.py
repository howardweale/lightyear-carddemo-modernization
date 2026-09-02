from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from lightyear_data.cloudbank_baseline import (
    BUILD_RECEIPT_TYPE,
    ORACLE_IMAGE,
    ORACLE_RECEIPT_TYPE,
    ORACLE_TEST_CLASSES,
    PINNED_COMMIT,
    REACTOR_MODULES,
    UPSTREAM_IMAGE_BUILD_SERVICES,
    build_artifacts,
    build_plan,
    execution_contract,
    oracle_runtime_plan,
    readiness_receipt,
    validate_artifacts,
    validate_execution_receipt,
    validate_source_checkout,
)
from lightyear_data.contracts import sign


ROOT = Path(__file__).resolve().parents[1]
ESTATE = ROOT / "reference-estates/cloudbank"
KEY = "unit-test-cloudbank-baseline-key"
HEX = "a" * 64


def build_receipt() -> dict[str, object]:
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": BUILD_RECEIPT_TYPE,
            "release": "0.54.0",
            "source": build_plan()["source"],
            "build_plan_sha256": build_plan()["content_sha256"],
            "toolchain": {"java_version": "21.0.8", "java_major": 21, "maven_version": "3.9.11"},
            "commands": [
                {"argv_sha256": HEX, "exit_code": 0, "stdout_sha256": HEX, "stderr_sha256": HEX}
                for _ in range(4)
            ],
            "artifacts": [
                {
                    "module": module,
                    "path": f"{module}/target/{module}-0.0.1-SNAPSHOT.jar",
                    "sha256": HEX,
                    "size_bytes": 1_024,
                }
                for module in UPSTREAM_IMAGE_BUILD_SERVICES
            ],
            "status": "passed",
            "security": {
                "raw_stdout_persisted": False,
                "raw_stderr_persisted": False,
                "credentials_persisted": False,
            },
            "source_build_observed": True,
            "oracle_runtime_observed": False,
            "cloudbank_source_baseline_complete": False,
            "postgresql_mapping_complete": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
        KEY,
        "unit-test",
    )


def oracle_receipt() -> dict[str, object]:
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": ORACLE_RECEIPT_TYPE,
            "release": "0.54.0",
            "source": build_plan()["source"],
            "oracle_runtime_plan_sha256": oracle_runtime_plan()["content_sha256"],
            "build_receipt_sha256": build_receipt()["content_sha256"],
            "toolchain": {"java_version": "21.0.8", "java_major": 21, "maven_version": "3.9.11"},
            "oracle_image": ORACLE_IMAGE,
            "oracle_image_id_sha256": HEX,
            "command": {"argv_sha256": HEX, "exit_code": 0, "stdout_sha256": HEX, "stderr_sha256": HEX},
            "test_results": {"tests": 7, "failures": 0, "errors": 0, "skipped": 0, "classes": 3},
            "status": "passed",
            "security": {
                "raw_stdout_persisted": False,
                "raw_stderr_persisted": False,
                "credentials_persisted": False,
            },
            "source_build_observed": True,
            "oracle_runtime_observed": True,
            "cloudbank_source_baseline_complete": True,
            "customer_service_runtime_observed": False,
            "production_data_observed": False,
            "postgresql_mapping_complete": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
        KEY,
        "unit-test",
    )


class CloudBankExecutableBaselineTests(unittest.TestCase):
    def test_full_pinned_source_and_upstream_build_scope_are_explicit(self) -> None:
        plan = build_plan()
        self.assertEqual(PINNED_COMMIT, plan["source"]["commit"])
        self.assertTrue(plan["source_scope"]["full_pinned_subtree_required"])
        self.assertEqual(189, plan["source_scope"]["tracked_file_count"])
        self.assertEqual(list(REACTOR_MODULES), plan["source_scope"]["reactor_modules"])
        self.assertEqual(10, len(REACTOR_MODULES))
        self.assertEqual(7, len(UPSTREAM_IMAGE_BUILD_SERVICES))
        self.assertEqual(21, plan["toolchain"]["java_major"])
        self.assertEqual("3.6.0", plan["toolchain"]["maven_minimum"])
        self.assertFalse(plan["claim_boundary"]["postgresql_mapping_complete"])

    def test_oracle_runtime_is_bound_to_seven_real_upstream_tests(self) -> None:
        plan = oracle_runtime_plan()
        self.assertEqual(list(ORACLE_TEST_CLASSES), plan["scope"]["test_classes"])
        self.assertEqual(7, plan["scope"]["expected_test_count"])
        self.assertEqual(ORACLE_IMAGE, plan["scope"]["oracle_image"])
        self.assertTrue(plan["admission"]["signed_build_receipt_required"])
        self.assertEqual(0, plan["admission"]["failures_errors_skips_allowed"])
        self.assertFalse(plan["claim_boundary"]["customer_service_runtime_observed"])

    def test_readiness_is_honest_about_unexecuted_and_unmapped_work(self) -> None:
        receipt = readiness_receipt()
        self.assertEqual("ready-to-execute-not-observed", receipt["gate_status"])
        self.assertFalse(receipt["source_build_observed"])
        self.assertFalse(receipt["oracle_runtime_observed"])
        self.assertFalse(receipt["cloudbank_source_baseline_complete"])
        self.assertFalse(receipt["production_data_observed"])
        self.assertFalse(receipt["target_selected"])
        self.assertFalse(receipt["postgresql_mapping_complete"])
        self.assertIn("separately authorized", execution_contract()["data_rule"])

    def test_committed_artifacts_are_deterministic_and_schemas_are_valid_json(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts().items():
            actual = json.loads((ESTATE / "executable-baseline" / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        schemas = sorted((ESTATE / "schema").glob("*.schema.json"))
        self.assertEqual(
            {
                "executable-baseline-readiness.schema.json",
                "oracle-runtime-execution-receipt.schema.json",
                "source-build-execution-receipt.schema.json",
                "customer-postgresql-execution-receipt.schema.json",
                "customer-postgresql-readiness.schema.json",
            },
            {path.name for path in schemas},
        )
        self.assertTrue(all(json.loads(path.read_text(encoding="utf-8"))["$schema"] for path in schemas))

    def test_exact_pinned_checkout_is_admitted(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        self.assertEqual([], validate_source_checkout(checkout))

    def test_signed_build_and_oracle_receipts_are_admitted(self) -> None:
        self.assertEqual([], validate_execution_receipt(build_receipt(), KEY))
        self.assertEqual([], validate_execution_receipt(oracle_receipt(), KEY))

    def test_unsigned_tampered_incomplete_and_overclaiming_receipts_fail_closed(self) -> None:
        unsigned = build_receipt()
        unsigned.pop("signature")
        self.assertIn("cloudbank-receipt-signature-invalid", validate_execution_receipt(unsigned, KEY))

        wrong_source = copy.deepcopy(build_receipt())
        wrong_source["source"]["commit"] = "0" * 40
        self.assertIn("cloudbank-receipt-source-mismatch", validate_execution_receipt(wrong_source, KEY))

        java17 = copy.deepcopy(build_receipt())
        java17["toolchain"]["java_major"] = 17
        self.assertIn("cloudbank-receipt-java-major-invalid", validate_execution_receipt(java17, KEY))

        incomplete = copy.deepcopy(oracle_receipt())
        incomplete["test_results"]["tests"] = 6
        self.assertIn("cloudbank-oracle-receipt-test-results-invalid", validate_execution_receipt(incomplete, KEY))

        overclaim = copy.deepcopy(oracle_receipt())
        overclaim["postgresql_mapping_complete"] = True
        self.assertIn("cloudbank-receipt-overclaims:postgresql_mapping_complete", validate_execution_receipt(overclaim, KEY))

        leaked = copy.deepcopy(oracle_receipt())
        leaked["database_password"] = "should-never-be-here"
        self.assertIn("cloudbank-receipt-forbidden-sensitive-field", validate_execution_receipt(leaked, KEY))

    def test_cross_platform_launchers_and_operator_boundary_are_present(self) -> None:
        self.assertTrue((ROOT / "cloudbank-executable-baseline.sh").is_file())
        self.assertTrue((ROOT / "cloudbank-executable-baseline.ps1").is_file())
        readme = (ESTATE / "executable-baseline/README.md").read_text(encoding="utf-8")
        self.assertIn("Real customer or production data is neither present nor implied", readme)
        self.assertIn("PostgreSQL target selection and mapping remain false", readme)


if __name__ == "__main__":
    unittest.main()
