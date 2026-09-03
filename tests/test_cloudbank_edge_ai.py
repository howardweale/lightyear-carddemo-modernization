from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_checks_messaging import RECEIPT_TYPE as MS63_RECEIPT_TYPE
from lightyear_data.cloudbank_edge_ai import (
    CONTRACT_SHA256,
    OUTPUT_ROOT,
    PATCHES,
    REQUIRED_TESTS,
    RECEIPT_TYPE,
    SCENARIO_IDS,
    acceptance_contract,
    build_artifacts,
    compatibility_ledger,
    edge_contract,
    execute_edge_ai,
    execution_plan,
    materialize_target,
    readiness_receipt,
    required_workcells,
    validate_artifacts,
    validate_execution_receipt,
)
from lightyear_data.cloudbank_production_qualification import RECEIPT_TYPE as MS57_RECEIPT_TYPE


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cloudbank-upstream"
KEY = "unit-test-cloudbank-edge-ai-key"
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def ms63_receipt() -> dict[str, object]:
    return {"receipt_type": MS63_RECEIPT_TYPE, "content_sha256": HEX_A,
            "postgresql_image_id_sha256": HEX_C}


def ms57_receipt() -> dict[str, object]:
    return {"receipt_type": MS57_RECEIPT_TYPE, "content_sha256": HEX_B,
            "postgresql_image_id_sha256": HEX_C}


def passed_lane() -> dict[str, object]:
    return {
        "lane": "native-cloudbank-eight-service-edge-ai",
        "status": "passed",
        "reason": None,
        "contract_sha256": CONTRACT_SHA256,
        "scenario_count": len(SCENARIO_IDS),
        "scenarios": [{"id": identifier, "status": "passed"} for identifier in SCENARIO_IDS],
        "tests": REQUIRED_TESTS,
        "workcells": required_workcells(),
        "packaging": {"executable_jars": 8, "oracle_runtime_libraries": 0,
                      "microtx_runtime_libraries": 0},
        "external_credit_bureau_called": False,
        "external_model_called": False,
        "synthetic_data_only": True,
        "raw_output_persisted": False,
    }


class CloudBankEdgeAITests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        receipt = readiness_receipt(ROOT)
        self.assertFalse(receipt["remaining_service_workcells_complete"])
        self.assertFalse(receipt["eight_service_target_assembled"])
        self.assertFalse(receipt["production_ready"])

    def test_contract_separates_application_controls_from_external_quality(self) -> None:
        contract = edge_contract()
        self.assertEqual("cloudbank-creditscore", contract["creditscore"]["audience"])
        self.assertFalse(contract["creditscore"]["real_credit_decision"])
        self.assertEqual("cloudbank-chatbot", contract["chatbot"]["audience"])
        self.assertFalse(contract["chatbot"]["model_quality_qualified"])
        self.assertEqual(SCENARIO_IDS, contract["required_scenarios"])

    def test_plan_assembles_all_eight_services_and_fresh_output(self) -> None:
        plan = execution_plan(ROOT)
        self.assertEqual(8, len(plan["services"]))
        self.assertEqual(
            ["azn-server", "checks", "testrunner", "creditscore", "chatbot"],
            [item["service"] for item in plan["remaining_service_workcells"]],
        )
        self.assertTrue(all(
            item["generated_and_executed_by_ms64"]
            for item in plan["remaining_service_workcells"]
        ))
        self.assertEqual(sorted(PATCHES), sorted(item["path"] for item in plan["patches"]))
        self.assertTrue(plan["fresh_output_required"])
        self.assertFalse(plan["external_model_called_by_acceptance"])

    def test_ledger_preserves_bureau_model_and_equivalence_boundaries(self) -> None:
        ledger = compatibility_ledger()
        entries = {item["capability"]: item for item in ledger["entries"]}
        self.assertEqual("not-qualified", entries["creditscore-real-bureau-result"]["classification"])
        self.assertEqual("not-qualified", entries["chatbot-model-answer-quality"]["classification"])
        self.assertTrue(ledger["remaining_service_workcells_eligible"])
        self.assertFalse(ledger["whole_application_equivalent"])

    def test_templates_encode_identity_synthetic_provenance_and_fail_closed_ai(self) -> None:
        patches = ROOT / OUTPUT_ROOT / "patches"
        score = (patches / "SyntheticCreditScoreService.java").read_text(encoding="utf-8")
        self.assertIn("HmacSHA256", score)
        self.assertIn("synthetic-v1", score)
        self.assertNotIn("SecureRandom", score)
        credit_security = (patches / "CreditScoreOAuthSecurityConfiguration.java").read_text()
        chat_security = (patches / "ChatbotOAuthSecurityConfiguration.java").read_text()
        self.assertIn("cloudbank-creditscore", credit_security)
        self.assertIn("cloudbank-chatbot", chat_security)
        chat = (patches / "ChatController.java").read_text(encoding="utf-8")
        self.assertIn("BLOCKED_INPUT", chat)
        self.assertIn("TOO_MANY_REQUESTS", chat)
        self.assertIn("SERVICE_UNAVAILABLE", chat)
        policy = (patches / "ChatbotEndpointPolicy.java").read_text(encoding="utf-8")
        self.assertIn("allowlisted", policy)
        self.assertIn("HTTPS", policy)

    @unittest.skipUnless(SOURCE.is_dir(), "pinned CloudBank source is unavailable")
    def test_materialization_preserves_source_and_assembles_all_services(self) -> None:
        source_head = (SOURCE / ".git/HEAD").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            workspace = materialize_target(ROOT, SOURCE, Path(directory) / "workspace")
            for service in execution_plan(ROOT)["services"]:
                self.assertTrue((workspace / service / "pom.xml").is_file(), service)
            for relative in PATCHES:
                self.assertTrue((workspace / relative).is_file(), relative)
            customer_pom = (workspace / "customer/pom.xml").read_text(encoding="utf-8")
            self.assertIn("postgresql", customer_pom)
            self.assertNotIn("oracle-spring-boot", customer_pom)
        self.assertEqual(source_head, (SOURCE / ".git/HEAD").read_bytes())

    @patch("lightyear_data.cloudbank_edge_ai.validate_ms57_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_edge_ai.validate_ms63_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_edge_ai.validate_edge_source", return_value=[])
    @patch("lightyear_data.cloudbank_edge_ai.materialize_target")
    def test_execution_closes_only_edge_ai_application_boundary(
        self, materialize: object, _source: object, _ms63: object, _ms57: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            receipt = execute_edge_ai(
                ROOT, ROOT, ms63_receipt(), ms57_receipt(), output, KEY, "unit-test",
                "ms64-unit-run", lane_runner=lambda _workspace: passed_lane(),
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["remaining_service_workcells_complete"])
            self.assertTrue(receipt["eight_service_target_assembled"])
            self.assertEqual(required_workcells(), receipt["edge_ai_lane"]["workcells"])
            self.assertFalse(receipt["real_credit_decision_equivalent"])
            self.assertFalse(receipt["model_quality_qualified"])
            self.assertFalse(receipt["whole_application_equivalent"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-edge-ai-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-edge-ai-receipt-claims-invalid", errors)

    @patch("lightyear_data.cloudbank_edge_ai.validate_ms57_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_edge_ai.validate_ms63_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_edge_ai.validate_edge_source", return_value=[])
    @patch("lightyear_data.cloudbank_edge_ai.materialize_target")
    def test_receipt_image_mismatch_and_failed_lane_are_rejected(
        self, materialize: object, _source: object, _ms63: object, _ms57: object
    ) -> None:
        wrong_ms57 = ms57_receipt()
        wrong_ms57["postgresql_image_id_sha256"] = "d" * 64
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "image-chain-invalid"):
                execute_edge_ai(ROOT, ROOT, ms63_receipt(), wrong_ms57, Path(directory), KEY, "unit")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            lane = passed_lane()
            lane["status"] = "failed"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_edge_ai(ROOT, ROOT, ms63_receipt(), ms57_receipt(), output, KEY, "unit",
                                lane_runner=lambda _workspace: lane)
            diagnostic = (output / "cloudbank-edge-ai.failure.json").read_text()
            self.assertNotIn("prompt", diagnostic)
            self.assertNotIn("secret", diagnostic)

    def test_launchers_schemas_and_acceptance_exist(self) -> None:
        for relative in (
            "cloudbank-edge-ai.sh", "cloudbank-edge-ai.ps1", "tools/cloudbank_edge_ai.py",
            "reference-estates/cloudbank/schema/edge-ai-readiness.schema.json",
            "reference-estates/cloudbank/schema/edge-ai-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        acceptance = acceptance_contract(ROOT)
        self.assertEqual(28, len(acceptance["required_scenarios"]))
        self.assertEqual(REQUIRED_TESTS, acceptance["required_tests"])
        self.assertEqual(required_workcells(), acceptance["required_workcells"])
        self.assertIn("Invoke-FactoryDarkPython", (ROOT / "cloudbank-edge-ai.ps1").read_text())


if __name__ == "__main__":
    unittest.main()
