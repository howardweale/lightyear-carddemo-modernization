from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_checks_messaging import (
    CONTRACT_SHA256,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    SCENARIO_IDS,
    build_artifacts,
    changed_paths,
    compatibility_ledger,
    execute_checks_messaging,
    execution_plan,
    materialize_target,
    messaging_contract,
    readiness_receipt,
    validate_artifacts,
    validate_execution_receipt,
)
from lightyear_data.cloudbank_production_oauth import RECEIPT_TYPE as MS62_RECEIPT_TYPE


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cloudbank-upstream"
KEY = "unit-test-cloudbank-checks-messaging-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def ms62_receipt() -> dict[str, object]:
    return {"receipt_type": MS62_RECEIPT_TYPE, "content_sha256": HEX_A,
            "postgresql_image_id_sha256": HEX_B}


def passed_lane() -> dict[str, object]:
    return {
        "lane": "native-postgresql-checks-messaging",
        "status": "passed",
        "reason": None,
        "database_image_id_sha256": HEX_B,
        "contract_sha256": CONTRACT_SHA256,
        "scenario_count": len(SCENARIO_IDS),
        "scenarios": [{"id": identifier, "status": "passed"} for identifier in SCENARIO_IDS],
        "packaging": {"executable_jars": 5, "oracle_runtime_libraries": 0,
                      "microtx_runtime_libraries": 0},
        "synthetic_data_only": True,
        "raw_output_persisted": False,
    }


class CloudBankChecksMessagingTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        receipt = readiness_receipt(ROOT)
        self.assertFalse(receipt["checks_target_messaging_qualified"])
        self.assertFalse(receipt["native_oracle_aq_equivalence"])
        self.assertFalse(receipt["production_ready"])

    def test_contract_requires_real_durable_queue_failure_semantics(self) -> None:
        contract = messaging_contract()
        self.assertEqual("at-least-once-with-idempotent-message-key", contract["delivery"])
        self.assertEqual("fifo-within-aggregate", contract["ordering"])
        self.assertIn("skip-locked", contract["claim"])
        self.assertEqual(3, contract["retry"]["maximum_attempts"])
        self.assertEqual(SCENARIO_IDS, contract["required_scenarios"])

    def test_plan_binds_checks_and_testrunner_templates(self) -> None:
        plan = execution_plan(ROOT)
        self.assertEqual(["checks", "testrunner"], plan["services"])
        self.assertEqual(changed_paths(), sorted(item["path"] for item in plan["patches"]))
        self.assertEqual(14, len(plan["patches"]))
        self.assertFalse(plan["native_oracle_aq_lane"])

    def test_ledger_does_not_conflate_target_qualification_with_oracle_equivalence(self) -> None:
        ledger = compatibility_ledger()
        entries = {item["capability"]: item for item in ledger["entries"]}
        self.assertEqual("removed-from-target", entries["oracle-aq-jms-runtime"]["classification"])
        self.assertEqual("not-qualified", entries["native-oracle-aq-comparison"]["classification"])
        self.assertTrue(ledger["checks_target_messaging_eligible"])
        self.assertFalse(ledger["oracle_postgresql_messaging_equivalent"])

    def test_templates_remove_aq_and_include_idempotency_retry_and_dead_letter(self) -> None:
        patches = ROOT / OUTPUT_ROOT / "patches"
        for pom in ("checks-pom.xml", "testrunner-pom.xml"):
            text = (patches / pom).read_text(encoding="utf-8")
            self.assertNotIn("oracle-spring-boot-starter-aqjms", text)
            self.assertIn("postgresql", text)
        queue = (patches / "DurableCheckQueue.java").read_text(encoding="utf-8")
        self.assertIn("FOR UPDATE SKIP LOCKED", queue)
        self.assertIn("lease_until", queue)
        self.assertIn("'DEAD'", queue)
        producer = (patches / "DurableCheckProducer.java").read_text(encoding="utf-8")
        self.assertIn("ON CONFLICT (message_id) DO NOTHING", producer)
        account = (patches / "AccountService.java").read_text(encoding="utf-8")
        self.assertIn("CloudBankServiceTokenProvider", account)
        self.assertIn("Idempotency-Key", account)

    @unittest.skipUnless(SOURCE.is_dir(), "pinned CloudBank source is unavailable")
    def test_materialization_preserves_source_and_removes_aq_listeners(self) -> None:
        source_head = (SOURCE / ".git/HEAD").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            workspace = materialize_target(ROOT, SOURCE, Path(directory) / "workspace")
            for relative in changed_paths():
                self.assertTrue((workspace / relative).is_file(), relative)
            self.assertFalse((workspace / "checks/src/main/java/com/example/checks/controller/CheckReceiver.java").exists())
            self.assertFalse((workspace / "checks/src/main/java/com/example/checks/controller/ClearanceReceiver.java").exists())
        self.assertEqual(source_head, (SOURCE / ".git/HEAD").read_bytes())

    @patch("lightyear_data.cloudbank_checks_messaging.validate_ms62_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_checks_messaging.validate_checks_source", return_value=[])
    @patch("lightyear_data.cloudbank_checks_messaging.materialize_target")
    def test_execution_closes_only_target_checks_messaging(
        self, materialize: object, _source: object, _ms62: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            receipt = execute_checks_messaging(
                ROOT, ROOT, ms62_receipt(), output, KEY, "unit-test", "ms63-unit-run",
                lane_runner=lambda _workspace, _image: passed_lane(),
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["checks_target_messaging_qualified"])
            self.assertFalse(receipt["native_oracle_aq_equivalence"])
            self.assertFalse(receipt["remaining_service_workcells_complete"])
            self.assertFalse(receipt["production_ready"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-checks-messaging-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-checks-messaging-receipt-claims-invalid", errors)

    @patch("lightyear_data.cloudbank_checks_messaging.validate_ms62_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_checks_messaging.validate_checks_source", return_value=[])
    @patch("lightyear_data.cloudbank_checks_messaging.materialize_target")
    def test_failed_lane_writes_safe_aggregate_diagnostics(
        self, materialize: object, _source: object, _ms62: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            lane = passed_lane()
            lane["status"] = "failed"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_checks_messaging(ROOT, ROOT, ms62_receipt(), output, KEY, "unit-test",
                                         lane_runner=lambda _workspace, _image: lane)
            text = (output / "cloudbank-checks-messaging.failure.json").read_text()
            self.assertNotIn("password", text)
            self.assertNotIn("raw_stdout", text)

    def test_launchers_and_schemas_exist(self) -> None:
        for relative in (
            "cloudbank-checks-messaging.sh", "cloudbank-checks-messaging.ps1",
            "tools/cloudbank_checks_messaging.py",
            "reference-estates/cloudbank/schema/checks-messaging-readiness.schema.json",
            "reference-estates/cloudbank/schema/checks-messaging-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertIn("Invoke-FactoryDarkPython", (ROOT / "cloudbank-checks-messaging.ps1").read_text())


if __name__ == "__main__":
    unittest.main()
