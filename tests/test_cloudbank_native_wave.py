from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_native_wave import (
    CONTRACT_SHA256,
    EXPECTED_SCENARIOS,
    OUTPUT_ROOT,
    PATCHES,
    RECEIPT_TYPE,
    SCENARIO_IDS,
    acceptance_contract,
    build_artifacts,
    changed_paths,
    compatibility_ledger,
    execute_native_wave,
    execution_plan,
    readiness_receipt,
    validate_artifacts,
    validate_execution_receipt,
)
from lightyear_data.cloudbank_transaction_core import RECEIPT_TYPE as MS59_RECEIPT_TYPE


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-native-wave-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def ms59_receipt() -> dict[str, object]:
    return {
        "receipt_type": MS59_RECEIPT_TYPE,
        "content_sha256": HEX_A,
        "postgresql_image_id_sha256": HEX_B,
    }


def passed_lane() -> dict[str, object]:
    return {
        "lane": "native-account-transfer-http",
        "status": "passed",
        "reason": None,
        "database_image_id_sha256": HEX_B,
        "contract_sha256": CONTRACT_SHA256,
        "scenario_count": EXPECTED_SCENARIOS,
        "scenarios": [{"id": name, "status": "passed"} for name in SCENARIO_IDS],
        "service_starts": {"account": 2, "transfer": 2},
        "service_log_sha256": {"account": [HEX_A, HEX_B], "transfer": [HEX_A, HEX_B]},
        "packaging": {
            "executable_jars": 2,
            "oracle_runtime_libraries": 0,
            "microtx_runtime_libraries": 0,
        },
        "maven_exit_code": 0,
        "maven_stdout_sha256": HEX_A,
        "maven_stderr_sha256": HEX_B,
        "ports": "ephemeral-loopback-only",
        "synthetic_data_only": True,
        "raw_output_persisted": False,
    }


class CloudBankNativeWaveTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_bounded(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        readiness = readiness_receipt(ROOT)
        self.assertTrue(readiness["integrated_target_generated"])
        self.assertFalse(readiness["native_transaction_wave_observed"])
        self.assertFalse(readiness["native_lra_replacement_observed"])
        self.assertFalse(readiness["production_identity_qualified"])
        self.assertFalse(readiness["production_ready"])

    def test_plan_runs_eleven_real_http_restart_and_concurrency_scenarios(self) -> None:
        plan = execution_plan(ROOT)
        self.assertEqual(changed_paths(), sorted(item["path"] for item in plan["patches"]))
        self.assertEqual(3, len(PATCHES))
        self.assertEqual(11, len(plan["scenario_ids"]))
        self.assertIn("restart-transfer-and-account", plan["stages"])
        contract = acceptance_contract(ROOT)
        self.assertEqual({"account": 2, "transfer": 2}, contract["required_service_starts"])
        self.assertEqual("ephemeral-loopback-only", contract["required_runtime_boundaries"]["service_ports"])

    def test_ledger_closes_bounded_target_lra_but_keeps_larger_gates_open(self) -> None:
        ledger = compatibility_ledger()
        by_name = {item["capability"]: item for item in ledger["entries"]}
        self.assertEqual("normalized-equivalent", by_name["target-lra-removal"]["classification"])
        self.assertEqual("policy-decision-required", by_name["production-oauth2-oidc"]["classification"])
        self.assertEqual("unsupported", by_name["oracle-aq-checks-flow"]["classification"])
        self.assertEqual("unsupported", by_name["remaining-five-services"]["classification"])
        self.assertTrue(ledger["bounded_target_lra_replacement_eligible"])
        self.assertFalse(ledger["oracle_postgresql_equivalent"])

    def test_integration_templates_are_explicit_and_do_not_persist_credentials(self) -> None:
        patches = ROOT / OUTPUT_ROOT / "patches"
        expected_header = (
            "// Copyright (c) 2023, Oracle and/or its affiliates.\n"
            "// Licensed under the Universal Permissive License v 1.0.\n"
        )
        for template in patches.glob("*.java"):
            self.assertTrue(template.read_text(encoding="utf-8").startswith(expected_header))
        account_security = (patches / "AccountWaveSecurityConfiguration.java").read_text()
        transfer_security = (patches / "TransferWaveSecurityConfiguration.java").read_text()
        transfer_service = (patches / "TransferService.java").read_text()
        self.assertIn('@Profile("cloudbank-wave")', account_security)
        self.assertIn('@Profile("cloudbank-wave")', transfer_security)
        self.assertIn("httpBasic", transfer_security)
        self.assertIn("${cloudbank.wave.user-password}", transfer_security)
        self.assertNotIn("password123", transfer_security)
        self.assertIn("HttpStatusCodeException", transfer_service)
        self.assertIn("exception.getStatusCode()", transfer_service)

    @patch("lightyear_data.cloudbank_native_wave.validate_ms59_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_native_wave.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_native_wave.materialize_target")
    @patch("lightyear_data.cloudbank_native_wave._native_wave_lane")
    def test_execution_receipt_closes_only_bounded_native_wave(
        self, native: object, materialize: object, _source: object, _ms59: object
    ) -> None:
        native.return_value = passed_lane()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            receipt = execute_native_wave(
                ROOT,
                ROOT,
                ms59_receipt(),
                output,
                KEY,
                "unit-test",
                "ms60-unit-run",
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["native_transaction_wave_observed"])
            self.assertTrue(receipt["native_lra_replacement_observed"])
            self.assertTrue(receipt["durable_restart_replay_observed"])
            self.assertFalse(receipt["production_identity_qualified"])
            self.assertFalse(receipt["native_messaging_observed"])
            self.assertFalse(receipt["oracle_postgresql_equivalent"])
            self.assertFalse(receipt["whole_application_equivalent"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-native-wave-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-native-wave-receipt-claims-invalid", errors)

    @patch("lightyear_data.cloudbank_native_wave.validate_ms59_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_native_wave.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_native_wave.materialize_target")
    @patch("lightyear_data.cloudbank_native_wave._native_wave_lane")
    def test_failure_diagnostic_is_aggregate_and_secret_free(
        self, native: object, materialize: object, _source: object, _ms59: object
    ) -> None:
        native.return_value = {
            "lane": "native-account-transfer-http",
            "status": "failed",
            "reason": "runtime-gate-failed:RuntimeError",
            "raw_output_persisted": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_native_wave(
                    ROOT, ROOT, ms59_receipt(), output, KEY, "unit-test", "failed-run"
                )
            diagnostic = (output / "cloudbank-native-transaction-wave.failure.json").read_text()
            self.assertNotIn("password", diagnostic.lower())
            self.assertNotIn("token", diagnostic.lower())
            self.assertNotIn("stdout", diagnostic.lower())

    def test_launchers_and_schemas_exist(self) -> None:
        for relative in (
            "cloudbank-native-wave.sh",
            "cloudbank-native-wave.ps1",
            "tools/cloudbank_native_wave.py",
            "reference-estates/cloudbank/schema/native-transaction-wave-readiness.schema.json",
            "reference-estates/cloudbank/schema/native-transaction-wave-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        powershell = (ROOT / "cloudbank-native-wave.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-FactoryDarkPython", powershell)
        self.assertNotIn("Resolve-LightyearPython", powershell)


if __name__ == "__main__":
    unittest.main()
