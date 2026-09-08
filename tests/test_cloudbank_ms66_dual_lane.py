from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from lightyear_data.cloudbank_journeys import OBSERVATION_TYPE, hashed
from lightyear_data.cloudbank_ms66_dual_lane import (
    build_lane_observation,
    image_rows,
    recovery_state,
    validate_recovery_state,
    validate_shared_journey,
)
from lightyear_data.cloudbank_ms66_dual_lane_gke import (
    OracleGkeRuntime,
    cleanup_from_recovery_state,
    isolated_lane_resources,
)
from lightyear_data.cloudbank_ms66_hardening import (
    HARDENING_CONTRACT_SHA256,
    PATCH_SHA256,
    RELEASE,
    build_source_image_lock,
    source_identity,
    validate_hardening,
    validate_materialization_receipt,
    validate_source_image_lock,
)
from lightyear_data.cloudbank_whole_application_equivalence import (
    MINIMUM_START_COUNTS,
    SCENARIOS,
    SERVICES,
    journey_contract,
    validate_lane_observation,
)
from lightyear_data.contracts import seal, sign


ROOT = Path(__file__).resolve().parents[1]
KEY = "unit-test-ms66-governed-hardening-key"
SIGNER = "ms66-unit@example.com"
HEX_A, HEX_B, HEX_C, HEX_D = "a" * 64, "b" * 64, "c" * 64, "d" * 64


def immutable(name: str, index: int) -> str:
    return f"us-west1-docker.pkg.dev/test-project/cloudbank/{name}@sha256:{index:064x}"


def source_images() -> dict[str, str]:
    return {service: immutable(service + "-ms66-oracle", index)
            for index, service in enumerate(SERVICES, start=1)}


def materialization() -> dict[str, object]:
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-cloudbank-ms66-governed-hardening-materialization",
        "release": RELEASE,
        "source": source_identity(),
        "hardening_contract_sha256": HARDENING_CONTRACT_SHA256,
        "patch_sha256": PATCH_SHA256,
        "materialized_tree_sha256": HEX_A,
        "source_checkout_mutated": False,
        "materialized_application_identity": "pinned-source-plus-governed-hardening",
        "exact_unchanged_upstream_application": False,
    })


def source_lock() -> dict[str, object]:
    return build_source_image_lock(
        source_images(), materialization(), controller_commit="1" * 40,
        cloud_build_id="12345678-1234-1234-1234-123456789abc",
        java_base_image=immutable("java21-patched", 90),
        oracle_runtime_image=immutable("oracle-free-ms66", 91),
        microtx_runtime_image=immutable("microtx-ms66", 92),
        key=KEY, signer=SIGNER,
    )


def shared_journey(lane: str, images: dict[str, str], lock_sha256: str) -> dict[str, object]:
    scenarios: list[dict[str, object]] = []
    for identifier, normalized in SCENARIOS:
        evidence: dict[str, object] = {"bounded_marker": identifier}
        if identifier == "full-stack-restart-restores-journey":
            evidence["services"] = {
                service: {
                    "image": images[service],
                    "ready_replicas": 2,
                    "http_readiness": 200,
                    "observed_start_count": MINIMUM_START_COUNTS[service],
                }
                for service in SERVICES
            }
        scenarios.append({
            "id": identifier,
            "status": "passed",
            "normalized_result": normalized,
            "evidence": evidence,
            "evidence_sha256": hashed(evidence),
        })
    bindings: dict[str, object] = {
        "lane": "gke-oracle-governed-source" if lane == "oracle" else "gke-postgresql-target",
        "journey_contract_sha256": journey_contract()["content_sha256"],
        "environment": {"project": "test-project"},
    }
    if lane == "oracle":
        bindings.update({
            "source_image_lock_sha256": lock_sha256,
            "hardening_contract_sha256": HARDENING_CONTRACT_SHA256,
            "hardening_patch_sha256": PATCH_SHA256,
        })
    else:
        bindings.update({"image_lock_sha256": lock_sha256, "ms64_receipt_sha256": HEX_B})
    return sign({
        "schema_version": "1.0",
        "observation_type": OBSERVATION_TYPE,
        "run_id": f"ms66-unit-{lane}",
        "bindings": bindings,
        "status": "passed-shared-journeys",
        "scenarios": scenarios,
        "started_at_unix": 1,
        "finished_at_unix": 2,
        "scenario_count": len(SCENARIOS),
        "fixture_account_ids": [1, 2],
        "fixture_records_retained": True,
        "synthetic_data_only": True,
        "raw_output_persisted": False,
        "credentials_persisted": False,
        "production_environment": False,
        "whole_application_equivalent": False,
        "ms65_complete": False,
        "ms66_complete": False,
        "ms67_complete": False,
        "recovery": {"status": "restored", "errors": [], "remaining_stopped_services": []},
    }, KEY, SIGNER)


def authorization() -> dict[str, str]:
    return {
        "private.pem": "-----BEGIN PRIVATE KEY-----\nunit\n-----END PRIVATE KEY-----",
        "public.pem": "-----BEGIN PUBLIC KEY-----\nunit\n-----END PUBLIC KEY-----",
        "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_ID": "owner-client",
        "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SECRET": "owner-secret",
        "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SCOPES":
            "cloudbank.read,cloudbank.write,cloudbank.transfer",
        "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_ID": "service-client",
        "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SECRET": "service-secret",
        "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SCOPES":
            "cloudbank.internal,cloudbank.test",
        "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_ID": "credit-client",
        "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_SECRET": "credit-secret",
        "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_SCOPES": "cloudbank.read",
        "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_ID": "chat-client",
        "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_SECRET": "chat-secret",
        "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_SCOPES": "cloudbank.read",
    }


class CloudBankMs66DualLaneTests(unittest.TestCase):
    def test_governed_hardening_and_source_lock_are_exact_and_signed(self) -> None:
        self.assertEqual([], validate_hardening(ROOT))
        patch_text = (ROOT / "factory/cloudbank/whole-application-equivalence/oracle-hardening"
                      / "source-hardening.patch").read_text(encoding="utf-8")
        for marker in (
            "JmsHeaders.REDELIVERED",
            "STATE = 'READY'",
            "STATE IN ('READY', 'PROCESSING')",
            "STATE = 'READY' AND ATTEMPTS = 0",
            "cancelOnFamily = {}",
            "findJournalForLRAidOrNull",
            "withdraw compensate has no local effect for rejected LRA",
            "Ms66WithdrawNoEffectCallbacksTests",
            "Ms66InsufficientFundsTransferTests",
        ):
            self.assertIn(marker, patch_text)
        self.assertEqual([], validate_materialization_receipt(materialization()))
        lock = source_lock()
        self.assertEqual([], validate_source_image_lock(lock, KEY))
        self.assertEqual(source_images(), image_rows(lock))
        self.assertFalse(lock["source_checkout_mutated"])
        self.assertFalse(lock["exact_unchanged_upstream_application"])
        self.assertEqual(PATCH_SHA256, lock["hardening_patch_sha256"])
        damaged = copy.deepcopy(lock)
        damaged["images"][0]["reference"] = "https://registry.invalid/image@sha256:" + "0" * 64
        self.assertIn(
            "cloudbank-ms66-source-image-lock-images-invalid",
            validate_source_image_lock(damaged, KEY),
        )

    def test_shared_journeys_convert_to_same_run_signed_lane_observations(self) -> None:
        oracle_images = source_images()
        postgres_images = {service: immutable(service, index + 20)
                           for index, service in enumerate(SERVICES, start=1)}
        lock = source_lock()
        oracle = shared_journey("oracle", oracle_images, str(lock["content_sha256"]))
        postgres = shared_journey("postgresql", postgres_images, HEX_D)
        self.assertEqual([], validate_shared_journey(
            oracle, KEY, "oracle", image_lock_sha256=str(lock["content_sha256"]),
            expected_images=oracle_images,
        ))
        self.assertEqual([], validate_shared_journey(
            postgres, KEY, "postgresql", image_lock_sha256=HEX_D,
            expected_images=postgres_images,
        ))
        common = {
            "ms61_sha256": HEX_A,
            "ms64_sha256": HEX_B,
            "oracle_image_id_sha256": HEX_C,
            "postgresql_image_id_sha256": HEX_D,
            "comparison_run_id": "ms66-unit-comparison",
            "oracle_source_image_lock_sha256": str(lock["content_sha256"]),
            "postgresql_image_lock_sha256": HEX_D,
            "oracle_journey_sha256": str(oracle["content_sha256"]),
            "postgresql_journey_sha256": str(postgres["content_sha256"]),
        }
        observations = {
            "oracle": build_lane_observation(
                oracle, KEY, SIGNER, "oracle", expected_images=oracle_images,
                recovery={"status": "restored", "errors": []}, **common,
            ),
            "postgresql": build_lane_observation(
                postgres, KEY, SIGNER, "postgresql", expected_images=postgres_images,
                recovery={"status": "restored", "errors": []}, **common,
            ),
        }
        for lane, observed in observations.items():
            self.assertEqual([], validate_lane_observation(
                observed, KEY, lane, ms61_sha256=HEX_A, ms64_sha256=HEX_B,
                oracle_image=HEX_C, postgres_image=HEX_D,
                comparison_run_id="ms66-unit-comparison",
                oracle_source_image_lock_sha256=str(lock["content_sha256"]),
                postgresql_image_lock_sha256=HEX_D,
                oracle_journey_sha256=str(oracle["content_sha256"]),
                postgresql_journey_sha256=str(postgres["content_sha256"]),
            ))

    def test_isolated_resources_use_only_locked_images_and_restricted_app_pods(self) -> None:
        lock = source_lock()
        resources, model_policy = isolated_lane_resources(
            namespace="cloudbank-ms66-unit", run_id="ms66-unit-run",
            images=source_images(), oracle_image=lock["native_runtime_images"]["oracle"],
            microtx_image=lock["native_runtime_images"]["microtx"],
            authorization=authorization(), oracle_password="L" + "1" * 32,
            schema_password="S" + "2" * 32, model_namespace="cloudbank-model",
            model_name="qwen2.5:0.5b",
        )
        self.assertEqual(41, len(resources))
        deployments = {row["metadata"]["name"]: row for row in resources
                       if row["kind"] == "Deployment"}
        self.assertEqual(set(SERVICES) | {"microtx"}, set(deployments))
        oracle = next(row for row in resources if row["kind"] == "StatefulSet")
        oracle_pod = oracle["spec"]["template"]["spec"]
        oracle_container = oracle_pod["containers"][0]
        self.assertNotIn("volumes", oracle_pod)
        self.assertNotIn("volumeMounts", oracle_container)
        self.assertNotIn("tcpSocket", oracle_container["readinessProbe"])
        self.assertEqual(
            ["/opt/oracle/healthcheck.sh"],
            oracle_container["readinessProbe"]["exec"]["command"],
        )
        self.assertEqual(5, oracle_container["readinessProbe"]["timeoutSeconds"])
        self.assertEqual(
            "2Gi", oracle_container["resources"]["requests"]["ephemeral-storage"]
        )
        self.assertEqual(
            "8Gi", oracle_container["resources"]["limits"]["ephemeral-storage"]
        )
        for service in SERVICES:
            pod = deployments[service]["spec"]["template"]["spec"]
            container = pod["containers"][0]
            self.assertEqual(source_images()[service], container["image"])
            self.assertFalse(pod["automountServiceAccountToken"])
            self.assertTrue(pod["securityContext"]["runAsNonRoot"])
            self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
            self.assertEqual(["ALL"], container["securityContext"]["capabilities"]["drop"])
        self.assertEqual("NetworkPolicy", model_policy["kind"])
        self.assertEqual("cloudbank-model", model_policy["metadata"]["namespace"])
        authorization_secret = next(
            row for row in resources
            if row["kind"] == "Secret" and row["metadata"]["name"] == "ms66-authorization"
        )
        self.assertNotIn(
            "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_ID", authorization_secret["stringData"]
        )
        azn_environment = {
            row["name"]: row for row in
            deployments["azn-server"]["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        expected_client_slots = {
            "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_ID":
                "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_ID",
            "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SECRET":
                "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_SECRET",
            "AZN_AUTHORIZATION_SERVER_ADMIN_CLIENT_ID":
                "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_ID",
            "AZN_AUTHORIZATION_SERVER_ADMIN_CLIENT_SECRET":
                "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_SECRET",
        }
        for environment_name, secret_key in expected_client_slots.items():
            self.assertEqual(
                {"name": "ms66-authorization", "key": secret_key},
                azn_environment[environment_name]["valueFrom"]["secretKeyRef"],
            )
        expected_scope_slots = {
            "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SCOPES":
                "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SCOPES",
            "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SCOPES":
                "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SCOPES",
            "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SCOPES":
                "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_SCOPES",
            "AZN_AUTHORIZATION_SERVER_ADMIN_CLIENT_SCOPES":
                "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_SCOPES",
        }
        for environment_name, secret_key in expected_scope_slots.items():
            self.assertEqual(
                {"name": "ms66-authorization", "key": secret_key},
                azn_environment[environment_name]["valueFrom"]["secretKeyRef"],
            )
        serialized_lock = json.dumps(lock, sort_keys=True)
        self.assertNotIn("owner-secret", serialized_lock)
        self.assertNotIn("L" + "1" * 32, serialized_lock)
        with self.assertRaisesRegex(ValueError, "isolated-lane-input-invalid"):
            isolated_lane_resources(
                namespace="cloudbank-ms66-unit", run_id="ms66-unit-run",
                images=source_images(), oracle_image=lock["native_runtime_images"]["oracle"],
                microtx_image=lock["native_runtime_images"]["microtx"],
                authorization=authorization(), oracle_password="L" + "1" * 32,
                schema_password="S" + "2" * 32, model_namespace="cloudbank-model",
                model_name="bad\nmodel",
            )

    def test_oracle_lane_uses_the_deployed_authorization_client_contract(self) -> None:
        runtime = OracleGkeRuntime(
            project="test-project", region="us-west1", cluster="test-cluster",
            namespace="cloudbank-ms66-unit", images=source_images(), run_id="ms66-unit-run",
            output=ROOT, signing_key=KEY, signer=SIGNER,
        )
        with patch.object(runtime, "secret_json", return_value=authorization()):
            runtime.load_credentials()
        self.assertEqual(("owner-client", "owner-secret"), runtime.credentials["owner"])
        self.assertEqual(("service-client", "service-secret"), runtime.credentials["account"])
        self.assertEqual(runtime.credentials["account"], runtime.credentials["test"])
        self.assertEqual(("credit-client", "credit-secret"), runtime.credentials["credit"])
        self.assertEqual(("chat-client", "chat-secret"), runtime.credentials["chat"])

        for missing in (
            "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_ID",
            "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SECRET",
            "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_ID",
            "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_SECRET",
        ):
            damaged = authorization()
            damaged.pop(missing)
            with self.subTest(missing=missing), self.assertRaisesRegex(
                ValueError, "authorization-secret-shape-invalid"
            ):
                isolated_lane_resources(
                    namespace="cloudbank-ms66-unit", run_id="ms66-unit-run",
                    images=source_images(),
                    oracle_image=immutable("oracle-free-ms66", 91),
                    microtx_image=immutable("microtx-ms66", 92),
                    authorization=damaged, oracle_password="L" + "1" * 32,
                    schema_password="S" + "2" * 32, model_namespace="cloudbank-model",
                    model_name="qwen2.5:0.5b",
                )

        for prefix, scopes in (
            ("DEFAULT", "cloudbank.transfer"),
            ("SERVICE", "cloudbank.internal"),
            ("CREDITSCORE", "cloudbank.read,cloudbank.write"),
            ("CHATBOT", "cloudbank.read,cloudbank.admin"),
        ):
            damaged = authorization()
            damaged[f"AZN_AUTHORIZATION_SERVER_{prefix}_CLIENT_SCOPES"] = scopes
            with self.subTest(prefix=prefix), self.assertRaisesRegex(
                ValueError, "authorization-scope-contract-invalid"
            ):
                isolated_lane_resources(
                    namespace="cloudbank-ms66-unit", run_id="ms66-unit-run",
                    images=source_images(),
                    oracle_image=immutable("oracle-free-ms66", 91),
                    microtx_image=immutable("microtx-ms66", 92),
                    authorization=damaged, oracle_password="L" + "1" * 32,
                    schema_password="S" + "2" * 32, model_namespace="cloudbank-model",
                    model_name="qwen2.5:0.5b",
                )

    def test_recovery_journal_covers_crash_gaps_and_cleanup_checks_identity(self) -> None:
        pending = recovery_state(
            run_id="ms66-unit-run", context="gke_test-project_us-west1_test-cluster",
            namespace="cloudbank-ms66-unit", source_image_lock_sha256=HEX_A,
            phase="namespace-create-pending", namespace_uid=None,
            model_namespace="cloudbank-model", model_policy_name="ms66-unit-policy",
            model_policy_uid=None, cleanup_required=True, key=KEY, signer=SIGNER,
        )
        self.assertEqual([], validate_recovery_state(pending, KEY))
        with self.assertRaisesRegex(ValueError, "recovery-state-input-invalid"):
            recovery_state(
                run_id="ms66-unit-run", context="gke_test-project_us-west1_test-cluster",
                namespace="cloudbank-ms66-unit", source_image_lock_sha256=HEX_A,
                phase="planned", namespace_uid="unexpected-uid",
                model_namespace="cloudbank-model", model_policy_name="ms66-unit-policy",
                model_policy_uid=None, cleanup_required=False, key=KEY, signer=SIGNER,
            )

        active = recovery_state(
            run_id="ms66-unit-run", context="gke_test-project_us-west1_test-cluster",
            namespace="cloudbank-ms66-unit", source_image_lock_sha256=HEX_A,
            phase="cleanup-pending", namespace_uid="namespace-uid",
            model_namespace="cloudbank-model", model_policy_name="ms66-unit-policy",
            model_policy_uid="policy-uid", cleanup_required=True, key=KEY, signer=SIGNER,
        )
        calls: list[list[str]] = []

        def fake_command(argv: list[str], **_kwargs: object) -> str:
            calls.append(argv)
            if "get" in argv and "networkpolicy" in argv:
                return json.dumps({"metadata": {"uid": "policy-uid", "labels": {
                    "lightyear.ai/ms66-run": "ms66-unit-run",
                    "app.kubernetes.io/managed-by": "lightyear-ms66",
                }}})
            if "get" in argv and "namespace" in argv:
                return json.dumps({"metadata": {"uid": "namespace-uid", "labels": {
                    "lightyear.ai/ms66-run": "ms66-unit-run",
                    "app.kubernetes.io/managed-by": "lightyear-ms66",
                    "environment": "non-production",
                }}})
            return ""

        with patch("lightyear_data.cloudbank_ms66_dual_lane_gke.command", fake_command):
            restored = cleanup_from_recovery_state(active, KEY)
        self.assertEqual("restored", restored["status"])
        self.assertEqual(4, len(calls))
        self.assertTrue(any("networkpolicy" in row and "delete" in row for row in calls))
        self.assertTrue(any("namespace" in row and "delete" in row for row in calls))
        damaged = copy.deepcopy(active)
        damaged["namespace"] = "different"
        with self.assertRaisesRegex(ValueError, "signature-invalid"):
            cleanup_from_recovery_state(damaged, KEY)

        def policy_delete_fails(argv: list[str], **_kwargs: object) -> str:
            if "get" in argv and "networkpolicy" in argv:
                return json.dumps({"metadata": {"uid": "policy-uid", "labels": {
                    "lightyear.ai/ms66-run": "ms66-unit-run",
                    "app.kubernetes.io/managed-by": "lightyear-ms66",
                }}})
            if "delete" in argv and "networkpolicy" in argv:
                raise RuntimeError("bounded unit failure")
            if "get" in argv and "namespace" in argv:
                return json.dumps({"metadata": {"uid": "namespace-uid", "labels": {
                    "lightyear.ai/ms66-run": "ms66-unit-run",
                    "app.kubernetes.io/managed-by": "lightyear-ms66",
                    "environment": "non-production",
                }}})
            return ""

        with patch("lightyear_data.cloudbank_ms66_dual_lane_gke.command", policy_delete_fails):
            partial = cleanup_from_recovery_state(active, KEY)
        self.assertEqual("failed", partial["status"])
        self.assertIsNone(partial["remaining_isolated_namespace"])
        self.assertEqual("ms66-unit-policy", partial["remaining_model_policy"])

    def test_cloud_build_is_pinned_async_recoverable_and_never_uses_latest(self) -> None:
        gke = ROOT / "factory/cloudbank/platform-qualification/gke"
        build = (gke / "cloudbuild-ms66-dual-lane.yaml").read_text(encoding="utf-8")
        recovery = (gke / "cloudbuild-ms66-recovery.yaml").read_text(encoding="utf-8")
        submit = (gke / "submit-ms66-dual-lane.sh").read_text(encoding="utf-8")
        recover_submit = (gke / "submit-ms66-recovery.sh").read_text(encoding="utf-8")
        for marker in (
            "4f41b16d00c45503f691836fee8138010c969e86",
            "6aa92e89c783f123c4da8d7ae18108004a4f4a99",
            "bd918386209f284a1ed31802555740eb34b75348",
            PATCH_SHA256,
            "checkout-exact-upstream",
            "materialize-governed-hardening",
            "-Dtest=Ms66WithdrawNoEffectCallbacksTests,Ms66InsufficientFundsTransferTests",
            "run-durable-ms66-dual-lane",
            "diskSizeGb: '100'",
        ):
            self.assertIn(marker, build)
        for marker in (
            "--async", "--ongoing", "Evidence secret must have exactly one enabled version",
            "roles/container.developer", "roles/storage.objectAdmin",
            'index("ms67-ms66-dual-lane")', "ACTIVE_MS66_DUAL_LANE_BUILD",
            "Authorization secret does not match the four-client MS66 scope contract",
            "AZN_AUTHORIZATION_SERVER_CREDITSCORE_CLIENT_ID",
            "AZN_AUTHORIZATION_SERVER_CHATBOT_CLIENT_ID",
            '["cloudbank.internal", "cloudbank.test"]',
        ):
            self.assertIn(marker, submit)
        for marker in (
            "recover-identity-bound-lane", "_RECOVERY_STATE_SHA256",
            "lightyear-cloudbank-journey-recovery", "recovery-execution.json",
            "CLOUD_LOGGING_ONLY", "recovery_exit=$$?", "MS66_LANE_RECOVERY=FAILED",
        ):
            self.assertIn(marker, recovery)
        for marker in ("--async", "--ongoing", 'index("ms67-ms66-recovery")'):
            self.assertIn(marker, recover_submit)
        self.assertIn("gvenzl/oracle-free:23.26.1-slim-faststart", submit)
        self.assertIn(
            'MS66_MICROTX_IMAGE_CANDIDATE:-container-registry.oracle.com/database/otmm:24.4.1',
            submit,
        )
        self.assertNotIn("container-registry.oracle.com/database/otmm:24.4}", submit)
        self.assertNotIn("docker pull latest", build)
        self.assertIn('short="$${source_commit:0:12}"', build)
        self.assertNotIn('short="${_SOURCE_COMMIT:', build)
        self.assertIn('build_id="$BUILD_ID"', build)
        self.assertIn('isolated_namespace="cloudbank-ms66-$${build_id:0:8}"', build)
        self.assertNotIn('$${BUILD_ID:', build)
        self.assertNotIn("operator-held-value", build + recovery + submit + recover_submit)
        self.assertTrue((gke / "Dockerfile.ms66-oracle-source").is_file())


if __name__ == "__main__":
    unittest.main()
