from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_transaction_core import (
    CONTRACT_SHA256,
    DELETIONS,
    EXPECTED_TESTS,
    OUTPUT_ROOT,
    PATCHES,
    RECEIPT_TYPE,
    acceptance_contract,
    build_artifacts,
    changed_paths,
    compatibility_ledger,
    execute_transaction_core,
    readiness_receipt,
    transformation_plan,
    validate_artifacts,
    validate_execution_receipt,
)
from lightyear_data.cloudbank_transaction_wave import readiness_receipt as ms58_readiness
from lightyear_data.contracts import sign


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-transaction-core-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def admission_receipt() -> dict[str, object]:
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": "lightyear-cloudbank-transaction-wave-admission",
            "release": "0.58.0",
            "source_ms57_receipt_sha256": HEX_A,
            "oracle_image_id_sha256": HEX_A,
            "postgresql_image_id_sha256": HEX_B,
            "bindings": ms58_readiness()["bindings"],
            "status": "passed-transaction-wave-plan-admitted",
            "whole_application_inventory_complete": True,
            "whole_application_plan_complete": True,
            "transaction_wave_plan_admitted": True,
            "target_code_generated": False,
            "native_transaction_wave_observed": False,
            "native_messaging_observed": False,
            "native_lra_replacement_observed": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
            "security": {
                "source_checkout_mutated": False,
                "production_data_observed": False,
                "credentials_persisted": False,
                "human_promotion_authorized": False,
            },
        },
        KEY,
        "unit-test",
    )


def passed_lane() -> dict[str, object]:
    return {
        "lane": "postgresql-transaction-core",
        "status": "passed",
        "tests": EXPECTED_TESTS,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "maven_exit_code": 0,
        "database_image_id_sha256": HEX_B,
        "contract_sha256": CONTRACT_SHA256,
        "packaging": {
            "executable_jars": 2,
            "oracle_runtime_libraries": 0,
            "microtx_runtime_libraries": 0,
        },
        "stdout_sha256": HEX_A,
        "stderr_sha256": HEX_B,
        "raw_output_persisted": False,
    }


class CloudBankTransactionCoreTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_bounded(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        readiness = readiness_receipt(ROOT)
        self.assertTrue(readiness["target_code_generated"])
        self.assertFalse(readiness["native_transaction_wave_observed"])
        self.assertFalse(readiness["oracle_postgresql_equivalent"])
        self.assertFalse(readiness["production_ready"])

    def test_plan_replaces_both_services_and_retires_lra_participants(self) -> None:
        plan = transformation_plan(ROOT)
        self.assertEqual(changed_paths(), sorted(item["path"] for item in plan["changes"]))
        self.assertEqual(20, len(plan["changes"]))
        self.assertEqual(15, len(PATCHES))
        self.assertEqual(4, len(DELETIONS))
        deleted = {item["path"] for item in plan["changes"] if item["operation"] == "delete"}
        self.assertIn(
            "account/src/main/java/com/example/accounts/services/DepositService.java",
            deleted,
        )
        self.assertIn("account/src/main/resources/db/changelog/txeventq.sql", deleted)

    def test_acceptance_covers_all_eight_ms58_scenarios(self) -> None:
        contract = acceptance_contract(ROOT)
        self.assertEqual(8, len(contract["required_scenarios"]))
        self.assertEqual(EXPECTED_TESTS, contract["required_native_lane"]["tests"])
        self.assertFalse(contract["claim_boundary"]["oracle_postgresql_equivalence"])
        self.assertFalse(contract["claim_boundary"]["whole_application_equivalent"])

    def test_ledger_keeps_aq_and_oracle_equivalence_open(self) -> None:
        ledger = compatibility_ledger()
        by_name = {item["capability"]: item for item in ledger["entries"]}
        self.assertEqual("unsupported", by_name["oracle-aq-checks-flow"]["classification"])
        self.assertEqual(
            "policy-decision-required",
            by_name["oracle-source-equivalence"]["classification"],
        )
        self.assertFalse(ledger["whole_application_equivalent"])

    def test_templates_remove_oracle_database_and_microtx_dependencies(self) -> None:
        account_pom = (ROOT / OUTPUT_ROOT / "patches/account-pom.xml").read_text()
        transfer_pom = (ROOT / OUTPUT_ROOT / "patches/transfer-pom.xml").read_text()
        transfer_java = (ROOT / OUTPUT_ROOT / "patches/TransferService.java").read_text()
        self.assertIn("org.postgresql", account_pom)
        self.assertNotIn("com.oracle", account_pom)
        self.assertNotIn("microtx", transfer_pom.lower())
        self.assertNotIn("@LRA", transfer_java)

    @patch("lightyear_data.cloudbank_transaction_core._validate_patch_sources", return_value=[])
    @patch("lightyear_data.cloudbank_transaction_core.materialize_target")
    @patch("lightyear_data.cloudbank_transaction_core._native_postgresql_lane")
    def test_execution_receipt_is_signed_without_whole_application_overclaim(
        self, native: object, materialize: object, _source: object
    ) -> None:
        native.return_value = passed_lane()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            receipt = execute_transaction_core(
                ROOT,
                ROOT,
                admission_receipt(),
                output,
                KEY,
                "unit-test",
                "ms59-unit-run",
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["native_postgresql_transaction_core_observed"])
            self.assertTrue(receipt["bounded_local_atomicity_observed"])
            self.assertFalse(receipt["native_transaction_wave_observed"])
            self.assertFalse(receipt["native_lra_replacement_observed"])
            self.assertFalse(receipt["native_messaging_observed"])
            self.assertFalse(receipt["oracle_postgresql_equivalent"])
            self.assertFalse(receipt["whole_application_equivalent"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-transaction-core-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-transaction-core-receipt-claims-invalid", errors)

    def test_launchers_and_schemas_exist(self) -> None:
        for relative in (
            "cloudbank-transaction-core.sh",
            "cloudbank-transaction-core.ps1",
            "tools/cloudbank_transaction_core.py",
            "reference-estates/cloudbank/schema/transaction-core-readiness.schema.json",
            "reference-estates/cloudbank/schema/transaction-core-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
