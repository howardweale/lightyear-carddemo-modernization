from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_edge_ai import RECEIPT_TYPE as MS64_RECEIPT_TYPE
from lightyear_data.cloudbank_production_oauth import (
    _oauth_account_environment,
    _oauth_transfer_environment,
    _oauth_user_bootstrap_environment,
)
from lightyear_data.cloudbank_production_readiness import (
    CONTRACT_SHA256,
    OUTPUT_ROOT,
    RECEIPT_TYPE,
    SCENARIO_IDS,
    SERVICES,
    acceptance_contract,
    build_artifacts,
    compatibility_ledger,
    cutover_contract,
    deployment_contract,
    deployment_template,
    execute_rehearsal,
    execution_plan,
    readiness_receipt,
    render_deployment_bundle,
    validate_artifacts,
    validate_environment,
    validate_execution_receipt,
    validate_image_lock,
)
from lightyear_data.contracts import content_hash, sign


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-cloudbank-production-readiness-key"
HEX_A = "a" * 64
HEX_B = "b" * 64


def sealed(payload: dict[str, object]) -> dict[str, object]:
    payload["content_sha256"] = content_hash(payload)
    return payload


def ms64_receipt() -> dict[str, object]:
    return {"receipt_type": MS64_RECEIPT_TYPE, "content_sha256": HEX_A}


def image_lock() -> dict[str, object]:
    return sealed({
        "schema_version": "1.0",
        "lock_type": "lightyear-cloudbank-ms65-image-lock",
        "release": "0.65.0",
        "source_ms64_receipt_sha256": HEX_A,
        "images": [
            {"service": service, "reference": f"registry.example.test/cloudbank/{service}@sha256:{index:064x}"}
            for index, service in enumerate(SERVICES, start=1)
        ],
    })


def environment() -> dict[str, object]:
    return sealed({
        "schema_version": "1.0",
        "environment_type": "lightyear-cloudbank-ms65-environment",
        "release": "0.65.0",
        "cluster_identity_sha256": HEX_B,
        "namespace": "cloudbank-rehearsal",
        "ingress_namespace": "ingress-system",
        "database_egress_cidr": "10.20.0.0/24",
        "model_egress_cidr": "10.30.0.0/24",
        "service_secret_names": {
            service: f"cloudbank-{service}-external" for service in SERVICES
        },
        "non_production": True,
    })


def observation(lock: dict[str, object], env: dict[str, object], bundle: dict[str, object]) -> dict[str, object]:
    images = {item["service"]: item["reference"] for item in lock["images"]}
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "observation_type": "lightyear-cloudbank-ms65-rehearsal-observation",
        "release": "0.65.0",
        "bindings": {
            "source_ms64_receipt_sha256": HEX_A,
            "image_lock_sha256": lock["content_sha256"],
            "environment_sha256": env["content_sha256"],
            "deployment_bundle_sha256": bundle["content_sha256"],
            "cluster_identity_sha256": HEX_B,
        },
        "scenarios": [
            {"id": identifier, "status": "passed", "evidence_sha256": f"{index:064x}"}
            for index, identifier in enumerate(SCENARIO_IDS, start=100)
        ],
        "service_rollouts": [
            {"service": service, "image": images[service], "desired_replicas": 2,
             "ready_replicas": 2}
            for service in SERVICES
        ],
        "backup_restore": {
            "pre_cutover_state_sha256": "c" * 64,
            "backup_sha256": "d" * 64,
            "restored_state_sha256": "c" * 64,
        },
        "cutover_states": cutover_contract()["required_state_sequence"],
        "slo_window": {
            "requests": 250, "errors": 0, "p95_ms": 180, "duration_seconds": 300,
        },
        "synthetic_data_only": True,
        "raw_output_persisted": False,
        "secret_values_persisted": False,
        "production_environment": False,
    }
    return sign(payload, KEY, "unit-observer")


class CloudBankProductionReadinessTests(unittest.TestCase):
    def test_committed_artifacts_are_deterministic_and_fail_closed(self) -> None:
        self.assertEqual([], validate_artifacts(ROOT))
        for name, expected in build_artifacts().items():
            actual = json.loads((ROOT / OUTPUT_ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(expected, actual)
        receipt = readiness_receipt()
        self.assertFalse(receipt["production_like_rehearsal_complete"])
        self.assertFalse(receipt["production_deployed"])
        self.assertFalse(receipt["production_ready"])

    def test_contract_covers_all_services_and_operational_controls(self) -> None:
        contract = deployment_contract()
        self.assertEqual(list(SERVICES), contract["services"])
        self.assertEqual(2, contract["replicas_per_service"])
        self.assertTrue(contract["controls"]["network_default_deny"])
        self.assertTrue(contract["controls"]["model_egress_restricted_to_chatbot"])
        self.assertTrue(contract["controls"]["external_secrets_only"])
        self.assertFalse(contract["production_ready"])
        self.assertEqual(SCENARIO_IDS, execution_plan()["required_scenarios"])
        self.assertEqual(CONTRACT_SHA256, acceptance_contract()["required_contract_sha256"])

    def test_ledger_keeps_customer_production_gates_open(self) -> None:
        entries = {item["capability"]: item for item in compatibility_ledger()["entries"]}
        self.assertEqual("not-qualified", entries["production-deployment"]["classification"])
        self.assertEqual("not-qualified", entries["native-cdc"]["classification"])
        self.assertEqual("not-qualified", entries["whole-application-equivalence"]["classification"])

    def test_template_has_eight_hardened_workloads_and_no_secret_objects(self) -> None:
        template = deployment_template()
        self.assertEqual(8, template.count("kind: Deployment"))
        self.assertEqual(8, template.count("kind: ServiceAccount"))
        self.assertEqual(8, template.count("\nkind: Service\n"))
        self.assertEqual(8, template.count("kind: PodDisruptionBudget"))
        self.assertEqual(3, template.count("kind: NetworkPolicy"))
        self.assertEqual(8, template.count("readOnlyRootFilesystem: true"))
        self.assertEqual(8, template.count("maxUnavailable: 0"))
        self.assertEqual(8, template.count('image: "{{IMAGE_'))
        self.assertIn("mountPath: /var/run/secrets/cloudbank/signing", template)
        self.assertIn('secretName: "{{SECRET_AZN_SERVER}}"', template)
        self.assertIn("name: chatbot-model-egress", template)
        self.assertNotIn("kind: Secret", template)

    def test_image_lock_and_environment_render_placeholder_free_bundle(self) -> None:
        lock, env = image_lock(), environment()
        self.assertEqual([], validate_image_lock(lock, HEX_A))
        self.assertEqual([], validate_environment(env))
        manifest, bundle = render_deployment_bundle(lock, env, HEX_A)
        self.assertNotIn("{{", manifest)
        self.assertEqual(8, bundle["resource_counts"]["deployments"])
        self.assertEqual(0, bundle["resource_counts"]["secret_objects"])
        self.assertFalse(bundle["production_environment"])

    def test_deployment_carries_the_qualified_native_runtime_overrides(self) -> None:
        manifest, _ = render_deployment_bundle(image_lock(), environment(), HEX_A)
        deployed = {}
        for document in manifest.split("---\n"):
            if "kind: Deployment\n" not in document:
                continue
            service = re.search(r"^  name: (\S+)$", document, re.MULTILINE).group(1)
            # Read only explicit container env entries, which override envFrom/imported defaults.
            deployed[service] = {
                name: value.strip('"') for name, value in re.findall(
                    r'^        - \{name: ([A-Z_]+), value: ([^}]+)\}$', document, re.MULTILINE
                )
            }
        self.assertEqual(set(SERVICES), set(deployed))
        native_account = _oauth_account_environment({}, 8080, "jdbc:postgresql://test/db", "test")
        native_transfer = _oauth_transfer_environment({}, 8080, 8080, "http://test/token", "test")
        for service, values in deployed.items():
            self.assertEqual(native_account["SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT"],
                             values["SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT"], service)
            self.assertEqual("8080", values["SERVER_PORT"], service)
            self.assertEqual("true", values["MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED"], service)
            self.assertEqual("never", values["MANAGEMENT_ENDPOINT_HEALTH_SHOW_DETAILS"], service)
            self.assertFalse(any("PASSWORD" in name or "SECRET" in name for name in values))
        self.assertEqual(_oauth_user_bootstrap_environment()["AZN_BOOTSTRAP_USERS_ENABLED"],
                         deployed["azn-server"]["AZN_BOOTSTRAP_USERS_ENABLED"])
        for service in ("account", "transfer"):
            self.assertEqual("cloudbank-oauth", deployed[service]["SPRING_PROFILES_ACTIVE"])
        for service in ("transfer", "checks"):
            self.assertEqual(native_transfer["CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED"],
                             deployed[service]["CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED"], service)

    def test_unbounded_network_and_mutable_image_are_rejected(self) -> None:
        env = environment()
        env["database_egress_cidr"] = "0.0.0.0/0"
        env["content_sha256"] = content_hash(env)
        self.assertTrue(any("database_egress_cidr" in item for item in validate_environment(env)))
        env = environment()
        env["database_password"] = "must-not-be-admitted"
        env["content_sha256"] = content_hash(env)
        self.assertIn(
            "cloudbank-production-readiness-environment-fields-invalid",
            validate_environment(env),
        )
        lock = image_lock()
        lock["images"][0]["reference"] = "registry.example.test/cloudbank/azn-server:latest"
        lock["content_sha256"] = content_hash(lock)
        self.assertTrue(any("reference" in item for item in validate_image_lock(lock, HEX_A)))

    def test_environment_json_round_trip_preserves_validation_and_bundle(self) -> None:
        lock, env = image_lock(), environment()
        # render-site-inputs.sh writes sorted JSON, including the secret-name map.
        serialized = json.loads(json.dumps(env, indent=2, sort_keys=True))
        self.assertNotEqual(list(env["service_secret_names"]), list(serialized["service_secret_names"]))
        self.assertEqual([], validate_environment(serialized))
        self.assertEqual(
            render_deployment_bundle(lock, env, HEX_A),
            render_deployment_bundle(lock, serialized, HEX_A),
        )

    def test_environment_rejects_missing_extra_or_invalid_secret_names(self) -> None:
        valid = environment()["service_secret_names"]
        cases = (
            {name: value for name, value in valid.items() if name != "chatbot"},
            {**valid, "unexpected-service": "unexpected-secret"},
            {**valid, "chatbot": "invalid/secret"},
            list(valid),
        )
        for secrets in cases:
            with self.subTest(secrets=secrets):
                env = environment()
                env["service_secret_names"] = secrets
                env["content_sha256"] = content_hash(env)
                self.assertIn("cloudbank-production-readiness-environment-secrets-invalid",
                              validate_environment(env))

    @patch("lightyear_data.cloudbank_production_readiness.validate_ms64_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_production_readiness.validate_edge_source", return_value=[])
    def test_execution_closes_only_rehearsal_claims(self, _source: object, _ms64: object) -> None:
        lock, env = image_lock(), environment()
        _, bundle = render_deployment_bundle(lock, env, HEX_A)
        observed = observation(lock, env, bundle)

        def materialize(_project: Path, _source_root: Path, output: Path) -> Path:
            for service in SERVICES:
                path = output / service
                path.mkdir(parents=True, exist_ok=True)
                (path / "pom.xml").write_text("<project/>", encoding="utf-8")
            return output

        with tempfile.TemporaryDirectory() as directory:
            receipt = execute_rehearsal(
                ROOT, ROOT, ms64_receipt(), lock, env, observed, Path(directory), KEY,
                "unit-test", "ms65-unit-run", materializer=materialize,
            )
            self.assertEqual(RECEIPT_TYPE, receipt["receipt_type"])
            self.assertTrue(receipt["production_like_rehearsal_complete"])
            self.assertTrue(receipt["cutover_rehearsal_complete"])
            self.assertTrue(receipt["rollback_rehearsal_complete"])
            self.assertFalse(receipt["production_deployed"])
            self.assertFalse(receipt["migration_complete"])
            self.assertFalse(receipt["production_ready"])
            self.assertEqual([], validate_execution_receipt(receipt, KEY, ROOT))
            tampered = copy.deepcopy(receipt)
            tampered["production_ready"] = True
            errors = validate_execution_receipt(tampered, KEY, ROOT)
            self.assertIn("cloudbank-production-readiness-receipt-content-hash-invalid", errors)
            self.assertIn("cloudbank-production-readiness-receipt-claims-invalid", errors)

    @patch("lightyear_data.cloudbank_production_readiness.validate_ms64_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_production_readiness.validate_edge_source", return_value=[])
    def test_failed_or_misbound_observation_is_rejected(self, _source: object, _ms64: object) -> None:
        lock, env = image_lock(), environment()
        _, bundle = render_deployment_bundle(lock, env, HEX_A)
        observed = observation(lock, env, bundle)
        observed["slo_window"]["errors"] = 1
        observed = sign(observed, KEY, "unit-observer")

        def materialize(_project: Path, _source_root: Path, output: Path) -> Path:
            for service in SERVICES:
                path = output / service
                path.mkdir(parents=True, exist_ok=True)
                (path / "pom.xml").write_text("<project/>", encoding="utf-8")
            return output

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with self.assertRaisesRegex(ValueError, "acceptance-failed"):
                execute_rehearsal(
                    ROOT, ROOT, ms64_receipt(), lock, env, observed, output, KEY,
                    "unit-test", materializer=materialize,
                )
            failure = (output / "cloudbank-production-readiness.failure.json").read_text()
            self.assertNotIn("password", failure)
            self.assertNotIn("token", failure)

    @patch("lightyear_data.cloudbank_production_readiness.validate_ms64_receipt", return_value=[])
    @patch("lightyear_data.cloudbank_production_readiness.validate_edge_source", return_value=[])
    def test_output_inside_source_and_blank_signer_fail_before_materialization(
        self, _source: object, _ms64: object,
    ) -> None:
        lock, env = image_lock(), environment()
        _, bundle = render_deployment_bundle(lock, env, HEX_A)
        observed = observation(lock, env, bundle)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            with self.assertRaisesRegex(ValueError, "signer-required"):
                execute_rehearsal(
                    ROOT, source, ms64_receipt(), lock, env, observed, source.parent / "outside",
                    KEY, "   ", materializer=lambda *_args: self.fail("materialized"),
                )
            with self.assertRaisesRegex(ValueError, "output-inside-source"):
                execute_rehearsal(
                    ROOT, source, ms64_receipt(), lock, env, observed, source / "output",
                    KEY, "unit-test", materializer=lambda *_args: self.fail("materialized"),
                )

    def test_launchers_and_schemas_exist(self) -> None:
        for relative in (
            "cloudbank-production-readiness.sh", "cloudbank-production-readiness.ps1",
            "tools/cloudbank_production_readiness.py",
            "reference-estates/cloudbank/schema/production-readiness.schema.json",
            "reference-estates/cloudbank/schema/production-readiness-execution-receipt.schema.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertIn(
            "Invoke-FactoryDarkPython", (ROOT / "cloudbank-production-readiness.ps1").read_text()
        )


if __name__ == "__main__":
    unittest.main()
