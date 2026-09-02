from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_oracle_equivalence import RECEIPT_TYPE as MS61_RECEIPT_TYPE
from lightyear_data.cloudbank_production_oauth import (
    CONTRACT_SHA256,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    SCENARIO_IDS,
    build_artifacts,
    changed_paths,
    compatibility_ledger,
    execute_production_oauth,
    execution_plan,
    materialize_target,
    readiness_receipt,
    security_contract,
    validate_artifacts,
    validate_execution_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "cloudbank-upstream"
KEY = "unit-test-cloudbank-production-oauth-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def ms61_receipt() -> dict[str, object]:
    return {
        "receipt_type": MS61_RECEIPT_TYPE,
        "content_sha256": HEX_A,
        "postgresql_image_id_sha256": HEX_B,
    }


def passed_lane() -> dict[str, object]:
    return {
        "lane": "native-production-oauth-account-transfer",
        "status": "passed",
        "reason": None,
        "database_image_id_sha256": HEX_B,
        "contract_sha256": CONTRACT_SHA256,
        "scenario_count": len(SCENARIO_IDS),
        "scenarios": [
            {"id": identifier, "status": "passed"} for identifier in SCENARIO_IDS
        ],
        "service_starts": {"azn-server": 2, "account": 2, "transfer": 2},
        "service_log_sha256": {"azn-server": [HEX_A], "account": [HEX_A], "transfer": [HEX_A]},
        "public_signing_key_sha256": HEX_A,
        "jwks_sha256": HEX_B,
        "packaging": {
            "executable_jars": 3,
            "oracle_runtime_libraries": 0,
            "microtx_runtime_libraries": 0,
        },
        "maven_exit_code": 0,
        "maven_stdout_sha256": HEX_A,
        "maven_stderr_sha256": HEX_B,
        "ports": "ephemeral-loopback-only",
        "synthetic_data_only": True,
        "credentials_persisted": False,
        "raw_output_persisted": False,
    }


class CloudBankProductionOAuthTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts(ROOT).items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        readiness = readiness_receipt(ROOT)
        self.assertFalse(readiness["production_oauth_application_profile_qualified"])
        self.assertFalse(readiness["whole_application_equivalent"])
        self.assertFalse(readiness["production_ready"])

    def test_security_contract_is_real_oauth_not_static_token_authentication(self) -> None:
        contract = security_contract()
        self.assertEqual("oauth2-oidc-jwt", contract["protocol"])
        self.assertEqual(["client_credentials"], contract["grant_types_exercised"])
        self.assertEqual(SCENARIO_IDS, contract["required_scenarios"])
        validation = contract["token_validation"]
        self.assertEqual("rsa-3072-jwks", validation["signature"])
        self.assertIn("cloudbank-account", validation["audiences"])
        self.assertIn("cloudbank.internal", validation["scopes"])

    def test_plan_binds_three_services_and_all_templates(self) -> None:
        plan = execution_plan(ROOT)
        self.assertEqual(["azn-server", "account", "transfer"], plan["services"])
        self.assertEqual(changed_paths(), sorted(item["path"] for item in plan["patches"]))
        self.assertEqual(12, len(plan["patches"]))
        self.assertFalse(plan["external_tls_termination"])
        self.assertFalse(plan["secret_manager_integration"])

    def test_ledger_separates_application_oauth_from_deployment_readiness(self) -> None:
        ledger = compatibility_ledger()
        entries = {item["capability"]: item for item in ledger["entries"]}
        self.assertEqual("native-qualified", entries["jwt-audience-isolation"]["classification"])
        self.assertEqual("native-qualified", entries["service-to-service-oauth"]["classification"])
        self.assertEqual("not-qualified", entries["external-tls-termination"]["classification"])
        self.assertTrue(ledger["production_oauth_application_profile_eligible"])
        self.assertFalse(ledger["production_oauth_operational_deployment_qualified"])

    def test_templates_have_no_embedded_credentials_or_static_internal_header(self) -> None:
        patches = ROOT / OUTPUT_ROOT / "patches"
        transfer = (patches / "TransferOAuthService.java").read_text(encoding="utf-8")
        self.assertNotIn("X-CloudBank-Internal-Token", transfer)
        self.assertIn("CloudBankServiceTokenProvider", transfer)
        self.assertIn("getAuthorizationHeader", transfer)
        self.assertNotIn("httpBasic", (patches / "TransferOAuthSecurityConfiguration.java").read_text())
        application = (patches / "azn-application.yaml").read_text(encoding="utf-8")
        self.assertIn("AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SECRET", application)
        self.assertNotIn("password123", application)
        self.assertIn("private-key-path", application)

    @unittest.skipUnless(SOURCE.is_dir(), "pinned CloudBank source is unavailable")
    def test_materialization_preserves_source_and_creates_oauth_target(self) -> None:
        source_head = (SOURCE / ".git/HEAD").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            workspace = materialize_target(ROOT, SOURCE, Path(directory) / "workspace")
            for relative in changed_paths():
                self.assertTrue((workspace / relative).is_file(), relative)
            azn_pom = (workspace / "azn-server/pom.xml").read_text(encoding="utf-8")
            self.assertIn("postgresql", azn_pom)
            self.assertNotIn("oracle-spring-boot", azn_pom)
        self.assertEqual(source_head, (SOURCE / ".git/HEAD").read_bytes())

    @patch(
        "lightyear_data.cloudbank_production_oauth.validate_ms61_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_production_oauth.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_production_oauth.materialize_target")
    def test_execution_closes_only_application_oauth_boundary(
        self, materialize: object, _source: object, _ms61: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            receipt = execute_production_oauth(
                ROOT,
                ROOT,
                ms61_receipt(),
                output,
                KEY,
                "unit-test",
                "ms62-unit-run",
                lane_runner=lambda _workspace, _image: passed_lane(),
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["production_oauth_application_profile_qualified"])
            self.assertTrue(receipt["service_to_service_client_credentials_observed"])
            self.assertFalse(receipt["production_oauth_operational_deployment_qualified"])
            self.assertFalse(receipt["external_tls_termination_observed"])
            self.assertFalse(receipt["native_messaging_observed"])
            self.assertFalse(receipt["production_ready"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-production-oauth-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-production-oauth-receipt-claims-invalid", errors)

    @patch(
        "lightyear_data.cloudbank_production_oauth.validate_ms61_receipt",
        return_value=[],
    )
    @patch("lightyear_data.cloudbank_production_oauth.validate_source", return_value=[])
    @patch("lightyear_data.cloudbank_production_oauth.materialize_target")
    def test_failed_lane_writes_safe_aggregate_diagnostics(
        self, materialize: object, _source: object, _ms61: object
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            materialize.return_value = output / "workspace"
            failed = passed_lane()
            failed["status"] = "failed"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_production_oauth(
                    ROOT,
                    ROOT,
                    ms61_receipt(),
                    output,
                    KEY,
                    "unit-test",
                    "ms62-failed-run",
                    lane_runner=lambda _workspace, _image: failed,
                )
            diagnostic = output / "cloudbank-production-oauth.failure.json"
            text = diagnostic.read_text(encoding="utf-8")
            self.assertNotIn("client-secret", text)
            self.assertNotIn("access_token", text)
            self.assertNotIn("raw_stdout", text)

    def test_launchers_exist(self) -> None:
        for relative in (
            "cloudbank-production-oauth.sh",
            "cloudbank-production-oauth.ps1",
            "tools/cloudbank_production_oauth.py",
            "reference-estates/cloudbank/schema/production-oauth-readiness.schema.json",
            "reference-estates/cloudbank/schema/production-oauth-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        powershell = (ROOT / "cloudbank-production-oauth.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-FactoryDarkPython", powershell)
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertIn("cloudbank-production-oauth.sh materialize", workflow)
        self.assertIn("mvn -pl azn-server,account,transfer", workflow)


if __name__ == "__main__":
    unittest.main()
