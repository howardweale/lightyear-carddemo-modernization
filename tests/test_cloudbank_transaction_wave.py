from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_transaction_wave import (
    DEPLOYABLES,
    MS57_RECEIPT_TYPE,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    SOURCE_FILES,
    account_postgresql_mapping,
    admit_transaction_wave,
    build_artifacts,
    compatibility_ledger,
    portfolio_inventory,
    readiness_receipt,
    recovery_rehearsal,
    transaction_behavior_contract,
    validate_admission_receipt,
    validate_artifacts,
    wave_plan,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-transaction-wave-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


class CloudBankTransactionWaveTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_bounded(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts().items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        readiness = readiness_receipt()
        self.assertTrue(readiness["whole_application_inventory_complete"])
        self.assertFalse(readiness["native_transaction_wave_observed"])
        self.assertFalse(readiness["whole_application_equivalent"])
        self.assertFalse(readiness["production_ready"])

    def test_every_deployable_is_assigned_to_one_delivery_wave(self) -> None:
        inventory = portfolio_inventory()
        self.assertEqual(8, inventory["deployable_count"])
        self.assertEqual(set(DEPLOYABLES), {item["id"] for item in inventory["services"]})
        assigned = [service for wave in wave_plan()["waves"][:4] for service in wave["services"]]
        self.assertEqual(set(DEPLOYABLES), set(assigned))
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(["customer"], wave_plan()["waves"][0]["services"])
        self.assertEqual(["account", "transfer"], wave_plan()["waves"][1]["services"])

    def test_account_mapping_preserves_schema_constraints_and_open_semantics(self) -> None:
        mapping = account_postgresql_mapping()
        self.assertEqual(13, len(mapping["columns"]))
        self.assertTrue(any(item["rule"] == "identity" for item in mapping["columns"]))
        self.assertTrue(any(item["rule"] == "foreign-key" for item in mapping["columns"]))
        self.assertIn("ACCOUNT_TYPE in ('CH','SA','CC','LO')", mapping["constraints"])
        self.assertEqual(3, len(mapping["unresolved"]))
        self.assertFalse(mapping["target_schema_executed"])

    def test_ledger_keeps_aq_lra_and_native_recovery_open(self) -> None:
        ledger = compatibility_ledger()
        by_category = {entry["category"]: entry for entry in ledger["entries"]}
        self.assertEqual("blocked", by_category["messaging"]["status"])
        self.assertEqual("blocked", by_category["distributed-transactions"]["status"])
        self.assertEqual("simulated", by_category["recovery"]["status"])
        self.assertFalse(ledger["native_acceptance_complete"])

    def test_recovery_model_covers_all_native_acceptance_scenarios(self) -> None:
        contract_ids = {item["id"] for item in transaction_behavior_contract()["scenarios"]}
        rehearsal = recovery_rehearsal()
        result_ids = {item["id"] for item in rehearsal["results"]}
        self.assertEqual(8, rehearsal["scenario_count"])
        self.assertEqual(contract_ids, result_ids)
        self.assertTrue(all(item["status"] == "passed-simulated" for item in rehearsal["results"]))
        self.assertTrue(all(rehearsal["checks"].values()))
        self.assertFalse(rehearsal["native_runtime_observed"])

    def test_source_contract_pins_transaction_critical_files(self) -> None:
        self.assertEqual(17, len(SOURCE_FILES))
        self.assertTrue(all(len(digest) == 64 for digest in SOURCE_FILES.values()))
        self.assertIn("account/src/main/resources/db/changelog/txeventq.sql", SOURCE_FILES)
        self.assertIn("transfer/src/main/java/com/example/transfer/TransferService.java", SOURCE_FILES)

    @patch("lightyear_data.cloudbank_transaction_wave.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_transaction_wave.validate_ms57_receipt", return_value=[])
    def test_signed_admission_binds_ms57_without_overclaiming(
        self, _ms57: object, _source: object
    ) -> None:
        upstream = {
            "receipt_type": MS57_RECEIPT_TYPE,
            "content_sha256": HEX_A,
            "oracle_image_id_sha256": HEX_A,
            "postgresql_image_id_sha256": HEX_B,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            receipt = admit_transaction_wave(ROOT, ROOT, upstream, output, KEY, "unit-test")
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["transaction_wave_plan_admitted"])
            self.assertFalse(receipt["target_code_generated"])
            self.assertFalse(receipt["whole_application_equivalent"])
            self.assertEqual([], validate_admission_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_admission_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-transaction-wave-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-transaction-wave-receipt-claims-invalid", errors)

    def test_launchers_and_schemas_exist(self) -> None:
        for relative in (
            "cloudbank-transaction-wave.sh",
            "cloudbank-transaction-wave.ps1",
            "tools/cloudbank_transaction_wave.py",
            "reference-estates/cloudbank/schema/transaction-wave-readiness.schema.json",
            "reference-estates/cloudbank/schema/transaction-wave-admission-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
