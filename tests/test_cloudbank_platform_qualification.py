from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_platform_qualification import (
    CONTRACT_SHA256,
    CUTOVER_STATES,
    OUTPUT_ROOT,
    QUALIFIED_CLAIMS,
    RECEIPT_TYPE,
    SCENARIO_IDS,
    SERVICES,
    acceptance_contract,
    build_artifacts,
    compatibility_ledger,
    execute_qualification,
    execution_plan,
    gke_addons_template,
    platform_contract,
    preflight_platform,
    readiness_receipt,
    render_gke_addons,
    validate_artifacts,
    validate_execution_receipt,
    validate_observation,
    validate_profile,
)
from lightyear_data.contracts import sign


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-ms67-key"
HEX_A, HEX_B, HEX_C = "a" * 64, "b" * 64, "c" * 64


def image(service: str, index: int = 1) -> str:
    return f"europe-west2-docker.pkg.dev/test/cloudbank/{service}@sha256:{index:064x}"


def ms65_receipt() -> dict[str, object]:
    return {
        "receipt_type": "lightyear-cloudbank-production-readiness-rehearsal-execution",
        "content_sha256": HEX_A,
        "source_ms64_receipt_sha256": HEX_C,
        "deployment_bundle_sha256": HEX_B,
        "cluster_identity_sha256": HEX_B,
        "rehearsal": {"service_rollouts": [
            {"service": service, "image": image(service, index)}
            for index, service in enumerate(SERVICES, start=1)
        ]},
    }


def ms66_receipt() -> dict[str, object]:
    return {
        "receipt_type": "lightyear-cloudbank-whole-application-equivalence-execution",
        "content_sha256": HEX_C,
        "source_ms64_receipt_sha256": HEX_C,
    }


def profile(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "profile_type": "lightyear-cloudbank-ms67-platform-profile",
        "release": "0.67.0",
        "signer": "platform-owner",
        "context": "gke_test_europe-west2_cloudbank-ms67",
        "cluster_uid_sha256": HEX_B,
        "provider": "google-gke-standard-regional",
        "region": "europe-west2",
        "namespace": "cloudbank-ms67",
        "namespace_uid_sha256": HEX_C,
        "ingress_url": "https://cloudbank.test.example.com",
        "expected_hostname": "cloudbank.test.example.com",
        "model_mode": "in-cluster-ollama",
        "model_namespace": "cloudbank-model",
        "model_name": "qwen2.5:0.5b",
        "model_image": image("ollama-qwen2.5-0.5b", 90),
        "model_manifest_sha256": HEX_A,
        "model_external_egress": False,
        "mutating_drills_authorized": True,
        "production_access_authorized": False,
        "non_production": True,
    }
    payload.update(overrides)
    return sign(payload, KEY, "platform-owner")


def observation(site: dict[str, object], prior65: dict[str, object], prior66: dict[str, object]) -> dict[str, object]:
    rollouts = prior65["rehearsal"]["service_rollouts"]
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "observation_type": "lightyear-cloudbank-ms67-platform-observation",
        "release": "0.67.0",
        "signer": "platform-observer",
        "bindings": {
            "source_ms65_receipt_sha256": HEX_A,
            "source_ms66_receipt_sha256": HEX_C,
            "profile_sha256": site["content_sha256"],
            "deployment_bundle_sha256": HEX_B,
            "cluster_identity_sha256": HEX_B,
            "platform_contract_sha256": platform_contract()["content_sha256"],
            "evidence_contract_sha256": acceptance_contract()["bindings"]["evidence_contract_sha256"],
        },
        "cluster": {
            "context": site["context"], "cluster_uid_sha256": HEX_B,
            "namespace": site["namespace"], "namespace_uid_sha256": HEX_C,
            "provider": site["provider"], "region": site["region"],
            "kubernetes_version": "v1.31.6", "node_count": 3,
            "failure_domains": ["europe-west2-a", "europe-west2-b", "europe-west2-c"],
        },
        "scenarios": [
            {"id": identifier, "status": "passed", "evidence_sha256": f"{index:064x}"}
            for index, identifier in enumerate(SCENARIO_IDS, start=100)
        ],
        "service_rollouts": [
            {"service": row["service"], "image": row["image"], "desired_replicas": 2,
             "ready_replicas": 2, "available_during_drills": True} for row in rollouts
        ],
        "tls": {"hostname": site["expected_hostname"], "trusted_chain": True, "san_match": True,
                "minimum_protocol": "TLSv1.2", "certificate_days_remaining": 60,
                "plaintext_rejected": True},
        "external_secrets": {"controller_ready": True, "store_reference_sha256": HEX_A,
                             "synced_services": list(SERVICES), "rotation_observed": True,
                             "secret_values_persisted": False},
        "observability": {"metrics_services": list(SERVICES), "log_services": list(SERVICES),
                          "trace_services": list(SERVICES), "correlation_id_sha256": HEX_A,
                          "alert_fired": True, "alert_recovered": True},
        "load": {"tool": "k6", "requests": 2500, "duration_seconds": 600, "concurrency": 25,
                 "errors": 0, "p95_ms": 180, "requests_per_second": 4.1},
        "security": {
            "image_scans": [
                {"service": row["service"], "image": row["image"], "critical": 0, "high": 0,
                 "scan_sha256": f"{index + 300:064x}"} for index, row in enumerate(rollouts)
            ],
            "signed_services": list(SERVICES), "provenance_services": list(SERVICES),
            "manifest_scan": {"critical": 0, "high": 0}, "runtime_policy_violations": 0,
            "network_policy_tests_passed": True,
        },
        "backup_restore": {"pre_state_sha256": HEX_A, "backup_sha256": HEX_B,
                           "restored_state_sha256": HEX_A, "rpo_seconds": 30,
                           "rto_seconds": 240, "point_in_time_restore": True},
        "resilience": {"node_disruption_observed": True, "failure_domain_disruption_observed": True,
                       "all_services_recovered": True, "data_loss_observed": False},
        "rolling_deployments": [
            {"service": service, "previous_image": image(service, index),
             "candidate_image": image(service, index + 100), "maximum_unavailable": 0,
             "completed": True} for index, service in enumerate(SERVICES, start=1)
        ],
        "cutover_rollback": {"states": CUTOVER_STATES, "canary_percent": 10,
                             "target_traffic_percent": 100, "business_journey_count": 18,
                             "rollback_exercised": True, "all_services_recovered": True,
                             "pre_state_sha256": HEX_A, "post_rollback_state_sha256": HEX_A},
        "safety": {"non_production": True, "synthetic_data_only": True,
                   "production_accessed": False, "raw_logs_persisted": False,
                   "raw_traces_persisted": False, "secret_values_persisted": False,
                   "cluster_credentials_persisted": False, "backup_bodies_persisted": False},
    }
    return sign(payload, KEY, "platform-observer")


class CloudBankPlatformQualificationTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts().items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        self.assertTrue(all(readiness_receipt()[name] is False for name in QUALIFIED_CLAIMS))

    def test_contract_covers_every_requested_real_platform_control(self) -> None:
        contract = platform_contract()
        self.assertEqual(list(SERVICES), contract["services"])
        self.assertEqual(28, len(SCENARIO_IDS))
        self.assertEqual(CONTRACT_SHA256, acceptance_contract()["required_contract_sha256"])
        for control in ("tls", "external_secrets", "observability", "load", "security",
                        "in_cluster_model", "backup_restore", "availability",
                        "rolling_deployment", "cutover_rollback"):
            self.assertIn(control, contract["controls"])
        self.assertFalse(contract["production_ready"])
        self.assertEqual(SCENARIO_IDS, execution_plan()["required_scenarios"])

    def test_gke_template_has_external_secrets_tls_telemetry_and_no_values(self) -> None:
        template = gke_addons_template()
        self.assertEqual(8, template.count("kind: ExternalSecret"))
        self.assertIn("kind: ClusterIssuer", template)
        self.assertIn("kind: Ingress", template)
        self.assertIn("name: otel-collector", template)
        self.assertIn("cidr: \"{{GOOGLE_APIS_CIDR}}\"", template)
        self.assertNotIn("kind: Secret\n", template)
        rendered = render_gke_addons(
            "test-project", "europe-west2", "cloudbank-ms67", "cloudbank-ms67",
            "cloudbank.test.example.com", "owner@example.com",
            "otel/opentelemetry-collector-contrib@sha256:" + "1" * 64,
            "cloudbank-model", image("ollama-qwen2.5-0.5b", 90), "qwen2.5:0.5b",
            HEX_A,
            "199.36.153.8/30",
        )
        self.assertNotIn("{{", rendered)
        self.assertIn("name: chatbot-only-model-ingress", rendered)
        self.assertIn("lightyear.ai/model-manifest-sha256: \"" + HEX_A + "\"", rendered)
        self.assertIn("networking.k8s.io/v1", rendered)

    def test_profile_rejects_production_http_and_missing_authorization(self) -> None:
        self.assertEqual([], validate_profile(profile(), KEY))
        invalid = profile(ingress_url="http://cloudbank.test.example.com",
                          production_access_authorized=True, non_production=False,
                          mutating_drills_authorized=False)
        errors = validate_profile(invalid, KEY)
        self.assertIn("cloudbank-platform-qualification-profile-ingress-invalid", errors)
        self.assertIn("cloudbank-platform-qualification-profile-authorization-invalid", errors)

    @patch("lightyear_data.cloudbank_platform_qualification.shutil.which", return_value="/bin/tool")
    def test_preflight_uses_explicit_context_and_persists_only_hashes(self, _which: object) -> None:
        calls: list[list[str]] = []
        def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "safe-output", "")
        result = preflight_platform(profile(), KEY, runner=runner)
        self.assertEqual(6, len(calls))
        self.assertTrue(all("--context" in command for command in calls))
        self.assertNotIn("safe-output", json.dumps(result))
        self.assertFalse(result["mutations_performed"])

    @patch("lightyear_data.cloudbank_platform_qualification.validate_ms65_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_platform_qualification.validate_ms66_receipt", return_value=[])
    def test_passing_execution_qualifies_only_non_production_platform(
        self, _ms66: object, _ms65: object,
    ) -> None:
        prior65, prior66, site = ms65_receipt(), ms66_receipt(), profile()
        observed = observation(site, prior65, prior66)
        self.assertEqual([], validate_observation(observed, KEY, ms65=prior65, ms66=prior66, profile=site))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            receipt = execute_qualification(
                ROOT, prior65, prior66, site, observed, output, KEY, "admission-owner", "ms67-unit-run"
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["non_production_platform_qualified"])
            self.assertTrue(receipt["cutover_rollback_qualified"])
            self.assertFalse(receipt["customer_idp_qualified"])
            self.assertFalse(receipt["migration_complete"])
            self.assertFalse(receipt["production_deployed"])
            self.assertFalse(receipt["production_ready"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))

    @patch("lightyear_data.cloudbank_platform_qualification.validate_ms65_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_platform_qualification.validate_ms66_receipt", return_value=[])
    def test_failed_live_evidence_is_minimized_and_rejected(self, _ms66: object, _ms65: object) -> None:
        prior65, prior66, site = ms65_receipt(), ms66_receipt(), profile()
        observed = observation(site, prior65, prior66)
        observed["load"]["errors"] = 1
        observed["external_secrets"]["rotation_observed"] = False
        observed["backup_restore"]["restored_state_sha256"] = HEX_C
        observed = sign(observed, KEY, "platform-observer")
        errors = validate_observation(observed, KEY, ms65=prior65, ms66=prior66, profile=site)
        self.assertTrue(any("load-invalid" in item for item in errors))
        self.assertTrue(any("secrets-invalid" in item for item in errors))
        self.assertTrue(any("backup-invalid" in item for item in errors))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_qualification(ROOT, prior65, prior66, site, observed, output, KEY, "owner")
            failure = (output / "cloudbank-platform-qualification.failure.json").read_text()
            self.assertNotIn("password", failure)
            self.assertNotIn("kubeconfig", failure)

    def test_security_scan_must_match_the_deployed_digest(self) -> None:
        prior65, prior66, site = ms65_receipt(), ms66_receipt(), profile()
        observed = observation(site, prior65, prior66)
        observed["security"]["image_scans"][0]["image"] = image("azn-server", 999)
        observed = sign(observed, KEY, "platform-observer")
        errors = validate_observation(observed, KEY, ms65=prior65, ms66=prior66, profile=site)
        self.assertIn("cloudbank-platform-qualification-observation-security-invalid", errors)

    def test_malformed_receipt_summary_is_rejected_without_type_error(self) -> None:
        malformed = readiness_receipt()
        malformed["platform_summary"] = {
            "provider": "google-gke-standard-regional", "region": "europe-west2",
            "kubernetes_version": "v1.31", "node_count": "three", "failure_domain_count": 3,
            "load_requests": 2500, "load_p95_ms": 180, "rpo_seconds": 30, "rto_seconds": 240,
        }
        errors = validate_execution_receipt(malformed, KEY, ROOT)
        self.assertIn("cloudbank-platform-qualification-receipt-summary-invalid", errors)

    def test_ledger_and_launchers_keep_ms68_open(self) -> None:
        entries = {row["capability"]: row["classification"]
                   for row in compatibility_ledger()["entries"]}
        self.assertEqual("not-qualified", entries["customer-idp"])
        self.assertEqual("not-qualified", entries["representative-production-volume"])
        self.assertEqual("not-qualified", entries["production-readiness"])
        for relative in (
            "cloudbank-platform-qualification.sh", "cloudbank-platform-qualification.ps1",
            "tools/cloudbank_platform_qualification.py",
            "reference-estates/cloudbank/schema/platform-qualification-profile.schema.json",
            "reference-estates/cloudbank/schema/platform-qualification-observation.schema.json",
            "reference-estates/cloudbank/schema/platform-qualification-execution-receipt.schema.json",
            "reference-estates/cloudbank/schema/platform-qualification-readiness.schema.json",
            "factory/cloudbank/platform-qualification/gke/bootstrap.sh",
            "factory/cloudbank/platform-qualification/gke/destroy.sh",
            "factory/cloudbank/platform-qualification/gke/Dockerfile.evidence-runner",
            "factory/cloudbank/platform-qualification/gke/cloudbuild-prerequisite-chain.yaml",
            "factory/cloudbank/platform-qualification/gke/run-prerequisite-chain.sh",
            "factory/cloudbank/platform-qualification/gke/submit-prerequisite-chain.sh",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        bootstrap = (ROOT / "factory/cloudbank/platform-qualification/gke/bootstrap.sh").read_text()
        for service_api in (
            "compute.googleapis.com",
            "container.googleapis.com",
            "iam.googleapis.com",
            "serviceusage.googleapis.com",
            "sqladmin.googleapis.com",
        ):
            self.assertIn(service_api, bootstrap)
        for required in ("--region", "--enable-private-nodes", "--workload-pool",
                         "--edition ENTERPRISE", "--availability-type REGIONAL",
                         "--enable-point-in-time-recovery",
                         "roles/secretmanager.secretAccessor", "--no-assign-ip",
                         "--enable-dns-access", "--no-enable-ip-access", "--dns-endpoint"):
            self.assertIn(required, bootstrap)

    def test_cloud_build_prerequisite_chain_is_secret_backed_and_minimized(self) -> None:
        gke = ROOT / "factory/cloudbank/platform-qualification/gke"
        cloudbuild = (gke / "cloudbuild-prerequisite-chain.yaml").read_text()
        runner = (gke / "run-prerequisite-chain.sh").read_text()
        submit = (gke / "submit-prerequisite-chain.sh").read_text()

        self.assertIn("secretEnv:", cloudbuild)
        self.assertIn("cloudbank-ms67-evidence-key", submit)
        service_account_name = next(
            line.split('"', 2)[1]
            for line in submit.splitlines()
            if line.startswith('service_account_name="')
        )
        self.assertGreaterEqual(len(service_account_name), 6)
        self.assertLessEqual(len(service_account_name), 30)
        self.assertNotIn("operator-held-value", cloudbuild + runner + submit)
        self.assertIn("--async", submit)
        self.assertIn("--gcs-source-staging-dir", submit)
        self.assertIn("--public-access-prevention", submit)
        self.assertIn("CLOUD_LOGGING_ONLY", cloudbuild)
        self.assertIn("ms67-chain-export/**", cloudbuild)

        ordered_commands = (
            "cloudbank-executable-baseline.sh source-build",
            "cloudbank-executable-baseline.sh oracle-runtime",
            "cloudbank-customer-postgresql.sh native-postgresql",
            "cloudbank-dark-factory.sh run",
            "cloudbank-production-qualification.sh run",
            "cloudbank-transaction-wave.sh admit",
            "cloudbank-transaction-core.sh run",
            "cloudbank-native-wave.sh run",
            "cloudbank-oracle-equivalence.sh run",
            "cloudbank-production-oauth.sh run",
            "cloudbank-checks-messaging.sh run",
            "cloudbank-edge-ai.sh run",
        )
        offsets = [runner.index(command) for command in ordered_commands]
        self.assertEqual(sorted(offsets), offsets)
        self.assertIn("Expected 12 prerequisite receipts", runner)
        self.assertIn("credentials_persisted\": False", runner)


if __name__ == "__main__":
    unittest.main()
