from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from lightyear_data.cloudbank_baseline import (
    ORACLE_IMAGE,
    ORACLE_RECEIPT_TYPE,
    build_plan,
    oracle_runtime_plan,
)
from lightyear_data.cloudbank_customer_postgres import (
    COLUMNS,
    POSTGRES_IMAGE,
    RECEIPT_TYPE,
    behavior_contract,
    build_artifacts,
    compatibility_ledger,
    execute_postgresql,
    readiness_receipt,
    source_contract,
    target_mapping,
    validate_artifacts,
    validate_postgresql_receipt,
    validate_source_files,
)
from lightyear_data.contracts import seal, sign


ROOT = Path(__file__).resolve().parents[1]
ESTATE = ROOT / "reference-estates/cloudbank/customer-postgresql"
KEY = "unit-test-cloudbank-customer-postgresql-key"
HEX = "a" * 64


def oracle_receipt() -> dict[str, object]:
    return sign(
        {
            "schema_version": "1.0",
            "receipt_type": ORACLE_RECEIPT_TYPE,
            "release": "0.54.0",
            "source": build_plan()["source"],
            "oracle_runtime_plan_sha256": oracle_runtime_plan()["content_sha256"],
            "build_receipt_sha256": HEX,
            "toolchain": {"java_version": "21.0.12", "java_major": 21, "maven_version": "3.9.16"},
            "oracle_image": ORACLE_IMAGE,
            "oracle_image_id_sha256": HEX,
            "command": {"argv_sha256": HEX, "exit_code": 0, "stdout_sha256": HEX, "stderr_sha256": HEX},
            "test_results": {"tests": 7, "failures": 0, "errors": 0, "skipped": 0, "classes": 3},
            "status": "passed",
            "security": {"raw_stdout_persisted": False, "raw_stderr_persisted": False, "credentials_persisted": False},
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


class FakeDocker:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(argv)
        if argv[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, f"sha256:{HEX}\n", "")
        if argv[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(argv, 0, "container-id\n", "")
        if argv[:2] == ["docker", "rm"]:
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[:2] == ["docker", "exec"] and "SELECT 1" in argv:
            return subprocess.CompletedProcess(argv, 0, "1\n", "")
        if argv[:3] == ["docker", "exec", "-i"]:
            output = "\n".join(f"{name}={value}" for name, value in behavior_contract()["required_native_checks"].items()) + "\n"
            return subprocess.CompletedProcess(argv, 0, output, "")
        return subprocess.CompletedProcess(argv, 1, "", "unexpected")


class CloudBankCustomerPostgreSQLTests(unittest.TestCase):
    def test_complete_customer_table_mapping_is_generated(self) -> None:
        mapping = target_mapping()
        self.assertEqual(7, len(COLUMNS))
        self.assertEqual(7, len(mapping["columns"]))
        self.assertEqual("CUSTOMER.CUSTOMERS", mapping["source_table"])
        self.assertEqual("cloudbank_customer.customers", mapping["target_table"])
        self.assertEqual("postgresql-16", mapping["target_dialect"])
        date = next(item for item in mapping["columns"] if item["source"] == "DATE_BECAME_CUSTOMER")
        self.assertIn("TIMESTAMP(0) WITHOUT TIME ZONE", date["target_type"])
        self.assertEqual("oracle-empty-string-to-null-then-identity", mapping["columns"][0]["transformation"])

    def test_semantic_traps_are_explicit_and_bounded(self) -> None:
        ledger = compatibility_ledger()
        ids = {item["item_id"] for item in ledger["entries"]}
        self.assertIn("column:date-became-customer", ids)
        self.assertIn("column:role", ids)
        self.assertIn("behavior:contains-search", ids)
        self.assertIn("behavior:oracle-ucp-wallet", ids)
        self.assertEqual([], ledger["unresolved_decisions"])
        self.assertFalse(ledger["bounded_database_mapping_blocked"])
        self.assertTrue(ledger["application_equivalence_blocked"])
        self.assertTrue(ledger["production_equivalence_blocked"])

    def test_static_readiness_does_not_overclaim_native_or_application_proof(self) -> None:
        receipt = readiness_receipt()
        self.assertTrue(receipt["target_selected"])
        self.assertTrue(receipt["postgresql_mapping_complete"])
        self.assertFalse(receipt["native_postgresql_observed"])
        self.assertFalse(receipt["bounded_database_mapping_qualified"])
        self.assertFalse(receipt["application_refactored"])
        self.assertFalse(receipt["target_equivalent"])
        self.assertTrue(receipt["source_oracle_receipt_required"])

    def test_committed_artifacts_are_deterministic_and_exclude_upstream_credentials(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts().items():
            path = ESTATE / name
            actual = path.read_text(encoding="utf-8")
            if isinstance(expected, str):
                self.assertEqual(expected, actual)
            else:
                self.assertEqual(expected, json.loads(actual))
        combined = "\n".join(path.read_text(encoding="utf-8") for path in ESTATE.glob("*") if path.suffix in {".json", ".sql", ".md"})
        for forbidden in ("SuperSecret", "andy@andy.com", "sanjay@sanjay.com", "mark@mark.com"):
            self.assertNotIn(forbidden, combined)

    def test_exact_pinned_customer_sources_are_bound(self) -> None:
        contract = source_contract()
        self.assertEqual(7, len(contract["source_files"]))
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        self.assertEqual([], validate_source_files(checkout))

    def test_native_runner_requires_oracle_receipt_and_emits_bounded_signed_receipt(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        fake = FakeDocker()
        receipt = execute_postgresql(
            checkout,
            oracle_receipt(),
            HEX,
            KEY,
            "unit-test",
            run=fake,
            pause=lambda _: None,
        )
        self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
        self.assertEqual(POSTGRES_IMAGE, receipt["postgresql_image"])
        self.assertTrue(receipt["bounded_database_mapping_qualified"])
        self.assertFalse(receipt["application_equivalent"])
        self.assertEqual([], validate_postgresql_receipt(receipt, KEY))
        run_command = next(command for command in fake.commands if command[:2] == ["docker", "run"])
        self.assertEqual(f"sha256:{HEX}", run_command[-1])
        self.assertTrue(any(command[:2] == ["docker", "rm"] for command in fake.commands))

        mismatched = FakeDocker()
        with self.assertRaisesRegex(ValueError, "image-id-mismatch"):
            execute_postgresql(
                checkout,
                oracle_receipt(),
                "b" * 64,
                KEY,
                "unit-test",
                run=mismatched,
                pause=lambda _: None,
            )
        self.assertFalse(any(command[:2] == ["docker", "run"] for command in mismatched.commands))

    def test_tamper_unsigned_and_overclaiming_receipts_fail_closed(self) -> None:
        checkout = ROOT.parent / "cloudbank-upstream"
        if not checkout.is_dir():
            self.skipTest("pinned CloudBank checkout is supplied by CI")
        receipt = execute_postgresql(checkout, oracle_receipt(), HEX, KEY, "unit-test", run=FakeDocker(), pause=lambda _: None)
        unsigned = copy.deepcopy(receipt)
        unsigned.pop("signature")
        self.assertIn("cloudbank-customer-postgresql-receipt-signature-invalid", validate_postgresql_receipt(unsigned, KEY))
        changed = copy.deepcopy(receipt)
        changed["checks"]["CB_ROWS"] = "5"
        changed = seal(changed)
        self.assertIn("cloudbank-customer-postgresql-receipt-checks-invalid", validate_postgresql_receipt(changed, KEY))
        overclaim = copy.deepcopy(receipt)
        overclaim["application_equivalent"] = True
        overclaim = sign(overclaim, KEY, "unit-test")
        self.assertIn("cloudbank-customer-postgresql-receipt-overclaims", validate_postgresql_receipt(overclaim, KEY))

    def test_cross_platform_launchers_schemas_and_operator_guidance_exist(self) -> None:
        self.assertTrue((ROOT / "cloudbank-customer-postgresql.sh").is_file())
        self.assertTrue((ROOT / "cloudbank-customer-postgresql.ps1").is_file())
        schemas = sorted((ROOT / "reference-estates/cloudbank/schema").glob("customer-postgresql-*.schema.json"))
        self.assertEqual(2, len(schemas))
        self.assertTrue(all(json.loads(path.read_text(encoding="utf-8"))["$schema"] for path in schemas))
        readme = (ESTATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not refactor or run the Spring application", readme)
        self.assertIn("ROLE", readme)


if __name__ == "__main__":
    unittest.main()
