from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from lightyear_common.io import write_json

from .cloudbank_edge_ai import (
    RECEIPT_TYPE as MS64_RECEIPT_TYPE,
    materialize_target as materialize_ms64_target,
    validate_edge_source,
    validate_execution_receipt as validate_ms64_receipt,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.65.0"
OUTPUT_ROOT = Path("factory/cloudbank/production-readiness")
RECEIPT_TYPE = "lightyear-cloudbank-production-readiness-rehearsal-execution"
RECEIPT_NAME = "cloudbank-production-readiness.receipt.json"
FAILURE_NAME = "cloudbank-production-readiness.failure.json"
MANIFEST_NAME = "cloudbank-production-readiness.yaml"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")

SERVICES = (
    "azn-server", "customer", "account", "transfer", "checks", "testrunner",
    "creditscore", "chatbot",
)

SCENARIO_IDS = [
    "signed-ms64-eight-service-receipt-admitted",
    "eight-immutable-container-images-bound",
    "deployment-manifest-placeholder-free",
    "eight-deployments-and-services-present",
    "dedicated-service-accounts-and-token-automount-disabled",
    "non-root-read-only-least-privilege-containers",
    "cpu-and-memory-requests-and-limits-enforced",
    "startup-liveness-and-readiness-probes-enforced",
    "zero-unavailable-rolling-update-policy-enforced",
    "pod-disruption-budgets-cover-all-services",
    "default-deny-network-policy-enforced",
    "database-model-and-dns-egress-bounded",
    "external-secret-references-contain-no-values",
    "release-and-configuration-hashes-projected",
    "all-eight-service-rollouts-ready",
    "pre-cutover-backup-created-and-verified",
    "backup-restore-reproduces-pre-cutover-state",
    "synthetic-smoke-suite-passes",
    "candidate-canary-readiness-observed",
    "traffic-switch-checkpoint-recorded",
    "post-cutover-business-checks-pass",
    "rollback-drill-restores-checkpoint",
    "bounded-slo-window-meets-threshold",
    "raw-output-secrets-and-production-data-not-persisted",
]
CONTRACT_SHA256 = hashlib.sha256(";".join(SCENARIO_IDS).encode()).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _placeholder(service: str) -> str:
    return "{{IMAGE_" + service.upper().replace("-", "_") + "}}"


def deployment_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-production-like-deployment",
        "release": RELEASE,
        "services": list(SERVICES),
        "replicas_per_service": 2,
        "image_policy": "immutable-sha256-digest-only",
        "orchestrator": "kubernetes",
        "controls": {
            "service_account_per_service": True,
            "automount_service_account_token": False,
            "run_as_non_root": True,
            "read_only_root_filesystem": True,
            "allow_privilege_escalation": False,
            "capabilities_dropped": ["ALL"],
            "seccomp_profile": "RuntimeDefault",
            "resource_requests_and_limits": True,
            "startup_liveness_readiness_probes": True,
            "rolling_update": {"max_unavailable": 0, "max_surge": 1},
            "pod_disruption_budget_per_service": True,
            "network_default_deny": True,
            "model_egress_restricted_to_chatbot": True,
            "external_secrets_only": True,
        },
        "site_specific_inputs": [
            "namespace", "cluster_identity_sha256", "database_egress_cidr",
            "model_egress_cidr", "ingress_namespace", "service_secret_names",
        ],
        "production_environment": False,
        "production_ready": False,
    })


def cutover_contract() -> dict[str, Any]:
    states = [
        "admitted", "backup-verified", "candidate-ready", "smoke-passed",
        "traffic-switched", "business-checks-passed", "rollback-exercised", "recovered",
    ]
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-cutover-rollback-rehearsal",
        "release": RELEASE,
        "required_state_sequence": states,
        "data_class": "synthetic-only",
        "backup": "content-addressed-pre-cutover",
        "restore": "exact-normalized-state-hash",
        "traffic_switch": "explicit-checkpoint",
        "rollback": "mandatory-and-observed",
        "slo_window": {
            "minimum_requests": 100, "maximum_errors": 0, "maximum_p95_ms": 500,
            "minimum_duration_seconds": 60, "maximum_duration_seconds": 3600,
        },
        "native_cdc": False,
        "customer_cutover_authorized": False,
        "production_ready": False,
    })


def execution_plan() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "plan_type": "lightyear-cloudbank-production-readiness-rehearsal",
        "release": RELEASE,
        "requires": [
            "signed-ms64-eight-service-receipt", "same-evidence-key",
            "eight-immutable-image-digests", "non-production-cluster-identity",
            "site-specific-network-and-secret-references",
        ],
        "services": list(SERVICES),
        "stages": [
            "validate-signed-ms64-and-pinned-source",
            "materialize-fresh-eight-service-target",
            "bind-eight-immutable-image-digests",
            "render-hardened-kubernetes-bundle",
            "validate-static-deployment-controls",
            "observe-eight-service-rollout-and-canary",
            "verify-pre-cutover-backup-and-restore",
            "run-synthetic-smoke-and-bounded-slo-window",
            "record-traffic-switch-and-business-checks",
            "exercise-rollback-and-recovery",
            "sign-bounded-production-like-rehearsal-receipt",
        ],
        "required_scenarios": SCENARIO_IDS,
        "fresh_output_required": True,
        "production_data": False,
        "production_deployment": False,
        "native_cdc": False,
        "whole_application_equivalence": False,
        "production_ready": False,
    })


def compatibility_ledger() -> dict[str, Any]:
    rows = [
        ("eight-service-image-lock", "rehearsal-qualified", "immutable-digests"),
        ("kubernetes-security-context", "rehearsal-qualified", "restricted-containers"),
        ("kubernetes-availability-controls", "rehearsal-qualified", "replicas-rollout-pdb"),
        ("network-policy", "rehearsal-qualified", "default-deny-site-cidrs"),
        ("secret-values", "excluded", "external-secret-references-only"),
        ("backup-restore", "rehearsal-qualified", "synthetic-state-hash"),
        ("cutover-rollback", "rehearsal-qualified", "explicit-state-sequence"),
        ("bounded-slo", "rehearsal-qualified", "synthetic-window"),
        ("production-data", "not-qualified", "customer-authorization-required"),
        ("native-cdc", "not-qualified", "source-platform-capture-required"),
        ("oracle-aq-equivalence", "not-qualified", "native-oracle-lane-required"),
        ("enterprise-idp-and-secret-rotation", "not-qualified", "customer-platform-required"),
        ("credit-decision", "not-qualified", "regulated-provider-required"),
        ("model-answer-quality", "not-qualified", "approved-model-evaluation-required"),
        ("whole-application-equivalence", "not-qualified", "integrated-dual-run-required"),
        ("production-deployment", "not-qualified", "customer-change-authority-required"),
    ]
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-cloudbank-production-readiness-compatibility",
        "release": RELEASE,
        "entries": [
            {"capability": capability, "classification": classification, "evidence": evidence}
            for capability, classification, evidence in rows
        ],
        "production_like_rehearsal_eligible": True,
        "production_deployment_eligible": False,
        "migration_complete": False,
        "production_ready": False,
    })


def deployment_template() -> str:
    lines = [
        "apiVersion: v1", "kind: Namespace", "metadata:", "  name: \"{{NAMESPACE}}\"", "---",
        "apiVersion: v1", "kind: ConfigMap", "metadata:",
        "  name: cloudbank-runtime", "  namespace: \"{{NAMESPACE}}\"", "data:",
        "  LIGHTYEAR_RELEASE: \"0.65.0\"",
        "  LIGHTYEAR_CONFIGURATION_SHA256: \"{{CONFIGURATION_SHA256}}\"",
        "  CLOUDBANK_SECURITY_ISSUER_URI: \"http://azn-server:8080\"",
        "  CLOUDBANK_SECURITY_JWK_SET_URI: \"http://azn-server:8080/oauth2/jwks\"",
        "  CLOUDBANK_OAUTH_ISSUER: \"http://azn-server:8080\"",
        "  CLOUDBANK_OAUTH_JWK_SET_URI: \"http://azn-server:8080/oauth2/jwks\"",
        "  CLOUDBANK_SECURITY_SERVICE_TOKEN_URI: \"http://azn-server:8080/oauth2/token\"",
        "  AZN_AUTHORIZATION_SERVER_SIGNING_KEY_PRIVATE_KEY_PATH: \"/var/run/secrets/cloudbank/signing/private.pem\"",
        "  AZN_AUTHORIZATION_SERVER_SIGNING_KEY_PUBLIC_KEY_PATH: \"/var/run/secrets/cloudbank/signing/public.pem\"",
        "  ACCOUNT_TRANSACTION_URL: \"http://account:8080/api/v1/transfers\"",
        "  ACCOUNT_JOURNAL_URL: \"http://account:8080/api/v1/account/journal\"",
        "  SERVER_ADDRESS: \"0.0.0.0\"", "  EUREKA_CLIENT_ENABLED: \"false\"",
        "  SPRING_CLOUD_DISCOVERY_ENABLED: \"false\"", "---",
    ]
    for service in SERVICES:
        lines.extend([
            "apiVersion: v1", "kind: ServiceAccount", "metadata:", f"  name: {service}",
            "  namespace: \"{{NAMESPACE}}\"", "automountServiceAccountToken: false", "---",
            "apiVersion: apps/v1", "kind: Deployment", "metadata:", f"  name: {service}",
            "  namespace: \"{{NAMESPACE}}\"", "  labels:", f"    app.kubernetes.io/name: {service}",
            "    app.kubernetes.io/part-of: cloudbank", "spec:", "  replicas: 2", "  strategy:",
            "    type: RollingUpdate", "    rollingUpdate:", "      maxUnavailable: 0",
            "      maxSurge: 1", "  selector:", "    matchLabels:",
            f"      app.kubernetes.io/name: {service}", "  template:", "    metadata:", "      labels:",
            f"        app.kubernetes.io/name: {service}", "        app.kubernetes.io/part-of: cloudbank",
            "      annotations:",
            "        lightyear.ai/configuration-sha256: \"{{CONFIGURATION_SHA256}}\"",
            "    spec:", f"      serviceAccountName: {service}",
            "      automountServiceAccountToken: false", "      securityContext:",
            "        runAsNonRoot: true", "        seccompProfile:", "          type: RuntimeDefault",
            "      containers:", f"      - name: {service}", f"        image: \"{_placeholder(service)}\"",
            "        imagePullPolicy: IfNotPresent", "        ports:",
            "        - name: http", "          containerPort: 8080", "        envFrom:",
            "        - configMapRef:", "            name: cloudbank-runtime", "        - secretRef:",
            f"            name: \"{{{{SECRET_{service.upper().replace('-', '_')}}}}}\"",
            "        env:",
            "        - {name: SERVER_PORT, value: \"8080\"}",
            "        - {name: SPRING_CLOUD_CONFIG_ENABLED, value: \"false\"}",
            "        - {name: SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT, value: org.hibernate.dialect.PostgreSQLDialect}",
            "        - {name: MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED, value: \"true\"}",
            "        - {name: MANAGEMENT_ENDPOINT_HEALTH_SHOW_DETAILS, value: never}",
        ])
        if service == "azn-server":
            # Match the qualified client-credentials lane; do not create sample human users.
            lines.append("        - {name: AZN_BOOTSTRAP_USERS_ENABLED, value: \"false\"}")
        if service in {"account", "transfer"}:
            lines.append("        - {name: SPRING_PROFILES_ACTIVE, value: cloudbank-oauth}")
        if service == "transfer":
            lines.append("        - {name: CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED, value: \"true\"}")
        lines.extend([
            "        startupProbe:", "          httpGet:", "            path: /actuator/health/liveness",
            "            port: http", "          failureThreshold: 30", "          periodSeconds: 10",
            "        livenessProbe:", "          httpGet:", "            path: /actuator/health/liveness",
            "            port: http", "          periodSeconds: 10", "          timeoutSeconds: 2",
            "        readinessProbe:", "          httpGet:", "            path: /actuator/health/readiness",
            "            port: http", "          periodSeconds: 5", "          timeoutSeconds: 2",
            "        resources:", "          requests:", "            cpu: 100m", "            memory: 256Mi",
            "          limits:", "            cpu: \"1\"", "            memory: 1Gi",
            "        securityContext:", "          allowPrivilegeEscalation: false",
            "          readOnlyRootFilesystem: true", "          capabilities:", "            drop:",
            "            - ALL", "        volumeMounts:", "        - name: tmp", "          mountPath: /tmp",
        ])
        if service == "azn-server":
            lines.extend([
                "        - name: signing-keys",
                "          mountPath: /var/run/secrets/cloudbank/signing",
                "          readOnly: true",
            ])
        lines.extend([
            "      volumes:", "      - name: tmp", "        emptyDir:", "          sizeLimit: 128Mi",
        ])
        if service == "azn-server":
            lines.extend([
                "      - name: signing-keys", "        secret:",
                "          secretName: \"{{SECRET_AZN_SERVER}}\"",
                "          items:", "          - key: private.pem", "            path: private.pem",
                "          - key: public.pem", "            path: public.pem",
            ])
        lines.extend([
            "---", "apiVersion: v1", "kind: Service", "metadata:", f"  name: {service}",
            "  namespace: \"{{NAMESPACE}}\"", "spec:", "  selector:",
            f"    app.kubernetes.io/name: {service}", "  ports:", "  - name: http", "    port: 8080",
            "    targetPort: http", "---", "apiVersion: policy/v1", "kind: PodDisruptionBudget",
            "metadata:", f"  name: {service}", "  namespace: \"{{NAMESPACE}}\"", "spec:",
            "  minAvailable: 1", "  selector:", "    matchLabels:",
            f"      app.kubernetes.io/name: {service}", "---",
        ])
    lines.extend([
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: default-deny", "  namespace: \"{{NAMESPACE}}\"", "spec:", "  podSelector: {}",
        "  policyTypes:", "  - Ingress", "  - Egress", "---",
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: cloudbank-bounded-traffic", "  namespace: \"{{NAMESPACE}}\"", "spec:",
        "  podSelector:", "    matchLabels:", "      app.kubernetes.io/part-of: cloudbank",
        "  policyTypes:", "  - Ingress", "  - Egress", "  ingress:", "  - from:",
        "    - podSelector:", "        matchLabels:", "          app.kubernetes.io/part-of: cloudbank",
        "    - namespaceSelector:", "        matchLabels:",
        "          kubernetes.io/metadata.name: \"{{INGRESS_NAMESPACE}}\"", "  egress:", "  - to:",
        "    - podSelector:", "        matchLabels:", "          app.kubernetes.io/part-of: cloudbank",
        "  - to:", "    - namespaceSelector:", "        matchLabels:",
        "          kubernetes.io/metadata.name: kube-system", "    ports:", "    - protocol: UDP",
        "      port: 53", "    - protocol: TCP", "      port: 53", "  - to:", "    - ipBlock:",
        "        cidr: \"{{DATABASE_EGRESS_CIDR}}\"", "    ports:", "    - protocol: TCP", "      port: 5432",
        "---", "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: chatbot-model-egress", "  namespace: \"{{NAMESPACE}}\"", "spec:",
        "  podSelector:", "    matchLabels:", "      app.kubernetes.io/name: chatbot",
        "  policyTypes:", "  - Egress", "  egress:", "  - to:", "    - ipBlock:",
        "        cidr: \"{{MODEL_EGRESS_CIDR}}\"", "    ports:", "    - protocol: TCP",
        "      port: 443", "",
    ])
    return "\n".join(lines)


def acceptance_contract() -> dict[str, Any]:
    template_hash = _sha256_bytes(deployment_template().encode())
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-production-readiness-acceptance",
        "release": RELEASE,
        "bindings": {
            "deployment_contract_sha256": deployment_contract()["content_sha256"],
            "cutover_contract_sha256": cutover_contract()["content_sha256"],
            "execution_plan_sha256": execution_plan()["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
            "deployment_template_sha256": template_hash,
        },
        "required_ms64_receipt_type": MS64_RECEIPT_TYPE,
        "required_scenarios": SCENARIO_IDS,
        "required_contract_sha256": CONTRACT_SHA256,
        "required_services": list(SERVICES),
        "eligible_claim": {
            "production_like_rehearsal_complete": True,
            "cutover_rehearsal_complete": True,
            "rollback_rehearsal_complete": True,
            "production_deployed": False,
            "whole_application_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
    })


def readiness_receipt() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-cloudbank-production-readiness-rehearsal-readiness",
        "release": RELEASE,
        "bindings": acceptance_contract()["bindings"],
        "acceptance_contract_sha256": acceptance_contract()["content_sha256"],
        "gate_status": "ready-for-signed-ms64-and-authorized-non-production-rehearsal",
        "production_like_rehearsal_complete": False,
        "cutover_rehearsal_complete": False,
        "rollback_rehearsal_complete": False,
        "production_deployed": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    })


def build_artifacts() -> dict[str, dict[str, Any]]:
    return {
        "deployment-contract.json": deployment_contract(),
        "cutover-contract.json": cutover_contract(),
        "execution-plan.json": execution_plan(),
        "compatibility-ledger.json": compatibility_ledger(),
        "acceptance-contract.json": acceptance_contract(),
        "readiness.receipt.json": readiness_receipt(),
    }


def write_artifacts(project_root: Path) -> None:
    root = project_root / OUTPUT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in build_artifacts().items():
        write_json(root / name, payload)
    template_root = root / "kubernetes"
    template_root.mkdir(parents=True, exist_ok=True)
    (template_root / "cloudbank-template.yaml").write_text(deployment_template(), encoding="utf-8")


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    root = project_root / OUTPUT_ROOT
    for name, expected in build_artifacts().items():
        try:
            actual = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-production-readiness-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-production-readiness-artifact-drift:{name}")
    template = root / "kubernetes/cloudbank-template.yaml"
    if not template.is_file() or template.read_text(encoding="utf-8") != deployment_template():
        errors.append("cloudbank-production-readiness-deployment-template-drift")
    if len(SCENARIO_IDS) != 24 or len(set(SCENARIO_IDS)) != 24:
        errors.append("cloudbank-production-readiness-scenarios-invalid")
    claims = (
        "production_like_rehearsal_complete", "cutover_rehearsal_complete",
        "rollback_rehearsal_complete", "production_deployed", "whole_application_equivalent",
        "migration_complete", "production_ready",
    )
    if any(readiness_receipt().get(name) is not False for name in claims):
        errors.append("cloudbank-production-readiness-readiness-overclaims")
    return sorted(set(errors))


def _validate_sealed(payload: dict[str, Any], kind: str) -> list[str]:
    errors: list[str] = []
    if payload.get("content_sha256") != content_hash(payload):
        errors.append(f"cloudbank-production-readiness-{kind}-content-hash-invalid")
    return errors


def validate_image_lock(payload: dict[str, Any], ms64_sha256: str) -> list[str]:
    errors = _validate_sealed(payload, "image-lock")
    if set(payload) != {
        "schema_version", "lock_type", "release", "source_ms64_receipt_sha256",
        "images", "content_sha256",
    }:
        errors.append("cloudbank-production-readiness-image-lock-fields-invalid")
    if payload.get("lock_type") != "lightyear-cloudbank-ms65-image-lock" \
            or payload.get("release") != RELEASE \
            or payload.get("source_ms64_receipt_sha256") != ms64_sha256:
        errors.append("cloudbank-production-readiness-image-lock-identity-invalid")
    images = payload.get("images") or []
    if not isinstance(images, list) or any(not isinstance(item, dict) for item in images):
        errors.append("cloudbank-production-readiness-image-lock-images-invalid")
        images = []
    if [item.get("service") for item in images] != list(SERVICES):
        errors.append("cloudbank-production-readiness-image-lock-services-invalid")
    if any(set(item) != {"service", "reference"} for item in images if isinstance(item, dict)):
        errors.append("cloudbank-production-readiness-image-lock-fields-invalid")
    pattern = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
    if any(not pattern.fullmatch(str(item.get("reference", ""))) for item in images):
        errors.append("cloudbank-production-readiness-image-lock-reference-invalid")
    if len({item.get("reference") for item in images}) != len(SERVICES):
        errors.append("cloudbank-production-readiness-image-lock-duplicate-invalid")
    return sorted(set(errors))


def validate_environment(payload: dict[str, Any]) -> list[str]:
    errors = _validate_sealed(payload, "environment")
    if set(payload) != {
        "schema_version", "environment_type", "release", "cluster_identity_sha256",
        "namespace", "ingress_namespace", "database_egress_cidr", "model_egress_cidr",
        "service_secret_names", "non_production", "content_sha256",
    }:
        errors.append("cloudbank-production-readiness-environment-fields-invalid")
    if payload.get("environment_type") != "lightyear-cloudbank-ms65-environment" \
            or payload.get("release") != RELEASE \
            or payload.get("non_production") is not True \
            or not HEX_64.fullmatch(str(payload.get("cluster_identity_sha256", ""))):
        errors.append("cloudbank-production-readiness-environment-identity-invalid")
    for name in ("namespace", "ingress_namespace"):
        if not DNS_LABEL.fullmatch(str(payload.get(name, ""))):
            errors.append(f"cloudbank-production-readiness-environment-{name}-invalid")
    for name in ("database_egress_cidr", "model_egress_cidr"):
        try:
            network = ipaddress.ip_network(str(payload.get(name, "")), strict=False)
            if network.prefixlen == 0:
                raise ValueError("unbounded")
        except ValueError:
            errors.append(f"cloudbank-production-readiness-environment-{name}-invalid")
    secrets = payload.get("service_secret_names") or {}
    if not isinstance(secrets, dict):
        errors.append("cloudbank-production-readiness-environment-secrets-invalid")
        secrets = {}
    if set(secrets) != set(SERVICES) or any(
        not DNS_LABEL.fullmatch(str(secrets.get(service, ""))) for service in SERVICES
    ):
        errors.append("cloudbank-production-readiness-environment-secrets-invalid")
    forbidden = ("password", "secret_value", "token", "private_key", "pepper")
    if any(name in payload for name in forbidden):
        errors.append("cloudbank-production-readiness-environment-secret-value-invalid")
    return sorted(set(errors))


def render_deployment_bundle(
    image_lock: dict[str, Any], environment: dict[str, Any], ms64_sha256: str,
) -> tuple[str, dict[str, Any]]:
    errors = validate_image_lock(image_lock, ms64_sha256) + validate_environment(environment)
    if errors:
        raise ValueError(";".join(sorted(set(errors))))
    manifest = deployment_template().replace("{{NAMESPACE}}", environment["namespace"])
    manifest = manifest.replace("{{INGRESS_NAMESPACE}}", environment["ingress_namespace"])
    manifest = manifest.replace("{{DATABASE_EGRESS_CIDR}}", environment["database_egress_cidr"])
    manifest = manifest.replace("{{MODEL_EGRESS_CIDR}}", environment["model_egress_cidr"])
    manifest = manifest.replace("{{CONFIGURATION_SHA256}}", environment["content_sha256"])
    for item in image_lock["images"]:
        manifest = manifest.replace(_placeholder(item["service"]), item["reference"])
    for service, secret_name in environment["service_secret_names"].items():
        manifest = manifest.replace(
            "{{SECRET_" + service.upper().replace("-", "_") + "}}", secret_name,
        )
    if "{{" in manifest or "}}" in manifest:
        raise ValueError("cloudbank-production-readiness-manifest-placeholder-invalid")
    bundle = seal({
        "schema_version": "1.0",
        "bundle_type": "lightyear-cloudbank-ms65-deployment-bundle",
        "release": RELEASE,
        "source_ms64_receipt_sha256": ms64_sha256,
        "image_lock_sha256": image_lock["content_sha256"],
        "environment_sha256": environment["content_sha256"],
        "cluster_identity_sha256": environment["cluster_identity_sha256"],
        "namespace": environment["namespace"],
        "manifest_sha256": _sha256_bytes(manifest.encode()),
        "services": list(SERVICES),
        "resource_counts": {
            "namespaces": 1, "config_maps": 1, "service_accounts": 8,
            "deployments": 8, "services": 8, "pod_disruption_budgets": 8,
            "network_policies": 3, "secret_objects": 0,
        },
        "secret_values_present": False,
        "production_environment": False,
    })
    return manifest, bundle


def validate_observation(
    observation: dict[str, Any], key: str, *, ms64_sha256: str,
    image_lock: dict[str, Any], environment: dict[str, Any], bundle: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if set(observation) != {
        "schema_version", "observation_type", "release", "bindings", "scenarios",
        "service_rollouts", "backup_restore", "cutover_states", "slo_window",
        "synthetic_data_only", "raw_output_persisted", "secret_values_persisted",
        "production_environment", "content_sha256", "signature",
    }:
        errors.append("cloudbank-production-readiness-observation-fields-invalid")
    if observation.get("observation_type") != "lightyear-cloudbank-ms65-rehearsal-observation" \
            or observation.get("release") != RELEASE:
        errors.append("cloudbank-production-readiness-observation-identity-invalid")
    if observation.get("content_sha256") != content_hash(observation):
        errors.append("cloudbank-production-readiness-observation-content-hash-invalid")
    if not verify_signature(observation, key):
        errors.append("cloudbank-production-readiness-observation-signature-invalid")
    signature = observation.get("signature") or {}
    if not isinstance(signature, dict) or not str(signature.get("signer", "")).strip():
        errors.append("cloudbank-production-readiness-observation-signer-invalid")
    expected_bindings = {
        "source_ms64_receipt_sha256": ms64_sha256,
        "image_lock_sha256": image_lock.get("content_sha256"),
        "environment_sha256": environment.get("content_sha256"),
        "deployment_bundle_sha256": bundle.get("content_sha256"),
        "cluster_identity_sha256": environment.get("cluster_identity_sha256"),
    }
    if observation.get("bindings") != expected_bindings:
        errors.append("cloudbank-production-readiness-observation-binding-invalid")
    scenarios = observation.get("scenarios") or []
    if not isinstance(scenarios, list) or any(not isinstance(item, dict) for item in scenarios):
        errors.append("cloudbank-production-readiness-observation-scenarios-invalid")
        scenarios = []
    if [item.get("id") for item in scenarios] != SCENARIO_IDS \
            or any(item.get("status") != "passed" for item in scenarios) \
            or any(not HEX_64.fullmatch(str(item.get("evidence_sha256", ""))) for item in scenarios) \
            or any(set(item) != {"id", "status", "evidence_sha256"} for item in scenarios):
        errors.append("cloudbank-production-readiness-observation-scenarios-invalid")
    rollouts = observation.get("service_rollouts") or []
    if not isinstance(rollouts, list) or any(not isinstance(item, dict) for item in rollouts):
        errors.append("cloudbank-production-readiness-observation-rollouts-invalid")
        rollouts = []
    locked_images = image_lock.get("images") or []
    if not isinstance(locked_images, list):
        locked_images = []
    expected_images = {
        item["service"]: item["reference"] for item in locked_images
        if isinstance(item, dict) and "service" in item and "reference" in item
    }
    if [item.get("service") for item in rollouts] != list(SERVICES) or any(
        item.get("image") != expected_images.get(item.get("service"))
        or item.get("desired_replicas") != 2 or item.get("ready_replicas") != 2
        or set(item) != {"service", "image", "desired_replicas", "ready_replicas"}
        for item in rollouts
    ):
        errors.append("cloudbank-production-readiness-observation-rollouts-invalid")
    backup = observation.get("backup_restore") or {}
    if not isinstance(backup, dict):
        errors.append("cloudbank-production-readiness-observation-backup-invalid")
        backup = {}
    if not all(HEX_64.fullmatch(str(backup.get(name, ""))) for name in (
        "pre_cutover_state_sha256", "backup_sha256", "restored_state_sha256",
    )) or backup.get("restored_state_sha256") != backup.get("pre_cutover_state_sha256") \
            or set(backup) != {
                "pre_cutover_state_sha256", "backup_sha256", "restored_state_sha256",
            }:
        errors.append("cloudbank-production-readiness-observation-backup-invalid")
    if observation.get("cutover_states") != cutover_contract()["required_state_sequence"]:
        errors.append("cloudbank-production-readiness-observation-cutover-invalid")
    slo = observation.get("slo_window") or {}
    if not isinstance(slo, dict):
        errors.append("cloudbank-production-readiness-observation-slo-invalid")
        slo = {}
    if not isinstance(slo.get("requests"), int) or slo.get("requests", 0) < 100 \
            or slo.get("errors") != 0 \
            or not isinstance(slo.get("p95_ms"), (int, float)) or slo.get("p95_ms", 501) > 500 \
            or not isinstance(slo.get("duration_seconds"), int) \
            or not 60 <= slo.get("duration_seconds", 0) <= 3600 \
            or set(slo) != {"requests", "errors", "p95_ms", "duration_seconds"}:
        errors.append("cloudbank-production-readiness-observation-slo-invalid")
    required_flags = {
        "synthetic_data_only": True, "raw_output_persisted": False,
        "secret_values_persisted": False, "production_environment": False,
    }
    if any(observation.get(name) is not value for name, value in required_flags.items()):
        errors.append("cloudbank-production-readiness-observation-safety-invalid")
    return sorted(set(errors))


def execute_rehearsal(
    project_root: Path, source_root: Path, ms64_receipt: dict[str, Any],
    image_lock: dict[str, Any], environment: dict[str, Any], observation: dict[str, Any],
    output_root: Path, key: str, signer: str, run_id: str | None = None,
    materializer: Callable[[Path, Path, Path], Path] = materialize_ms64_target,
) -> dict[str, Any]:
    if not key:
        raise ValueError("cloudbank-production-readiness-evidence-key-required")
    if not signer.strip():
        raise ValueError("cloudbank-production-readiness-signer-required")
    if validate_artifacts(project_root):
        raise ValueError("cloudbank-production-readiness-repository-artifacts-invalid")
    if validate_edge_source(source_root):
        raise ValueError("cloudbank-production-readiness-source-invalid")
    if validate_ms64_receipt(ms64_receipt, key, project_root):
        raise ValueError("cloudbank-production-readiness-signed-ms64-receipt-required")
    ms64_sha256 = str(ms64_receipt.get("content_sha256", ""))
    input_errors = validate_image_lock(image_lock, ms64_sha256) + validate_environment(environment)
    if input_errors:
        raise ValueError(";".join(sorted(set(input_errors))))
    try:
        output_root.resolve().relative_to(source_root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("cloudbank-production-readiness-output-inside-source")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("cloudbank-production-readiness-fresh-output-required")
    output_root.mkdir(parents=True, exist_ok=True)
    workspace = materializer(project_root, source_root, output_root / "workspace")
    if any(not (workspace / service / "pom.xml").is_file() for service in SERVICES):
        raise ValueError("cloudbank-production-readiness-eight-service-target-invalid")
    manifest, bundle = render_deployment_bundle(image_lock, environment, ms64_sha256)
    (output_root / MANIFEST_NAME).write_text(manifest, encoding="utf-8")
    write_json(output_root / "deployment-bundle.json", bundle)
    errors = validate_observation(
        observation, key, ms64_sha256=ms64_sha256, image_lock=image_lock,
        environment=environment, bundle=bundle,
    )
    if errors:
        write_json(output_root / FAILURE_NAME, {
            "schema_version": "1.0", "status": "failed", "reason_codes": errors,
            "raw_output_persisted": False, "secret_values_persisted": False,
        })
        raise ValueError("cloudbank-production-readiness-acceptance-failed")
    receipt = {
        "schema_version": "1.0", "receipt_type": RECEIPT_TYPE, "release": RELEASE,
        "run_id": run_id or f"cloudbank-production-readiness-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        "signer": signer,
        "bindings": readiness_receipt()["bindings"],
        "source_ms64_receipt_sha256": ms64_sha256,
        "image_lock_sha256": image_lock["content_sha256"],
        "environment_sha256": environment["content_sha256"],
        "deployment_bundle_sha256": bundle["content_sha256"],
        "observation_sha256": observation["content_sha256"],
        "cluster_identity_sha256": environment["cluster_identity_sha256"],
        "rehearsal": {
            "status": "passed", "contract_sha256": CONTRACT_SHA256,
            "scenario_count": len(SCENARIO_IDS), "scenarios": observation["scenarios"],
            "services": list(SERVICES), "service_rollouts": observation["service_rollouts"],
            "backup_restore": observation["backup_restore"],
            "cutover_states": observation["cutover_states"],
            "slo_window": observation["slo_window"],
            "synthetic_data_only": True, "raw_output_persisted": False,
            "secret_values_persisted": False, "production_environment": False,
        },
        "production_like_rehearsal_complete": True,
        "cutover_rehearsal_complete": True,
        "rollback_rehearsal_complete": True,
        "production_deployed": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    }
    receipt = sign(receipt, key, signer)
    write_json(output_root / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(
    receipt: dict[str, Any], key: str, project_root: Path,
) -> list[str]:
    errors: list[str] = []
    if set(receipt) != {
        "schema_version", "receipt_type", "release", "run_id", "signer", "bindings",
        "source_ms64_receipt_sha256", "image_lock_sha256", "environment_sha256",
        "deployment_bundle_sha256", "observation_sha256", "cluster_identity_sha256",
        "rehearsal", "production_like_rehearsal_complete", "cutover_rehearsal_complete",
        "rollback_rehearsal_complete", "production_deployed", "whole_application_equivalent",
        "migration_complete", "production_ready", "content_sha256", "signature",
    }:
        errors.append("cloudbank-production-readiness-receipt-fields-invalid")
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE:
        errors.append("cloudbank-production-readiness-receipt-identity-invalid")
    if receipt.get("content_sha256") != content_hash(receipt):
        errors.append("cloudbank-production-readiness-receipt-content-hash-invalid")
    if not verify_signature(receipt, key):
        errors.append("cloudbank-production-readiness-receipt-signature-invalid")
    signature = receipt.get("signature") or {}
    if not isinstance(signature, dict) or not str(receipt.get("signer", "")).strip() \
            or signature.get("signer") != receipt.get("signer"):
        errors.append("cloudbank-production-readiness-receipt-signer-invalid")
    if receipt.get("bindings") != readiness_receipt()["bindings"]:
        errors.append("cloudbank-production-readiness-receipt-binding-invalid")
    for name in (
        "source_ms64_receipt_sha256", "image_lock_sha256", "environment_sha256",
        "deployment_bundle_sha256", "observation_sha256", "cluster_identity_sha256",
    ):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-production-readiness-receipt-{name}-invalid")
    lane = receipt.get("rehearsal") or {}
    if not isinstance(lane, dict):
        errors.append("cloudbank-production-readiness-receipt-rehearsal-invalid")
        lane = {}
    if set(lane) != {
        "status", "contract_sha256", "scenario_count", "scenarios", "services",
        "service_rollouts", "backup_restore", "cutover_states", "slo_window",
        "synthetic_data_only", "raw_output_persisted", "secret_values_persisted",
        "production_environment",
    }:
        errors.append("cloudbank-production-readiness-receipt-rehearsal-invalid")
    scenarios = lane.get("scenarios") or []
    if not isinstance(scenarios, list) or any(not isinstance(item, dict) for item in scenarios):
        scenarios = []
    rollouts = lane.get("service_rollouts") or []
    if not isinstance(rollouts, list) or any(not isinstance(item, dict) for item in rollouts):
        rollouts = []
    backup = lane.get("backup_restore") or {}
    if not isinstance(backup, dict):
        backup = {}
    slo = lane.get("slo_window") or {}
    if not isinstance(slo, dict):
        slo = {}
    image_pattern = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")
    if lane.get("status") != "passed" or lane.get("contract_sha256") != CONTRACT_SHA256 \
            or lane.get("scenario_count") != len(SCENARIO_IDS) \
            or [item.get("id") for item in scenarios] != SCENARIO_IDS \
            or any(item.get("status") != "passed" for item in scenarios) \
            or any(not HEX_64.fullmatch(str(item.get("evidence_sha256", "")))
                   or set(item) != {"id", "status", "evidence_sha256"} for item in scenarios) \
            or lane.get("services") != list(SERVICES) \
            or [item.get("service") for item in rollouts] != list(SERVICES) \
            or any(not image_pattern.fullmatch(str(item.get("image", "")))
                   or item.get("desired_replicas") != 2 or item.get("ready_replicas") != 2
                   or set(item) != {"service", "image", "desired_replicas", "ready_replicas"}
                   for item in rollouts) \
            or set(backup) != {
                "pre_cutover_state_sha256", "backup_sha256", "restored_state_sha256",
            } \
            or any(not HEX_64.fullmatch(str(backup.get(name, ""))) for name in backup) \
            or backup.get("restored_state_sha256") != backup.get("pre_cutover_state_sha256") \
            or lane.get("cutover_states") != cutover_contract()["required_state_sequence"] \
            or set(slo) != {"requests", "errors", "p95_ms", "duration_seconds"} \
            or not isinstance(slo.get("requests"), int) or slo.get("requests", 0) < 100 \
            or slo.get("errors") != 0 \
            or not isinstance(slo.get("p95_ms"), (int, float)) or slo.get("p95_ms", 501) > 500 \
            or not isinstance(slo.get("duration_seconds"), int) \
            or not 60 <= slo.get("duration_seconds", 0) <= 3600 \
            or lane.get("synthetic_data_only") is not True \
            or lane.get("raw_output_persisted") is not False \
            or lane.get("secret_values_persisted") is not False \
            or lane.get("production_environment") is not False:
        errors.append("cloudbank-production-readiness-receipt-rehearsal-invalid")
    expected = {
        "production_like_rehearsal_complete": True,
        "cutover_rehearsal_complete": True,
        "rollback_rehearsal_complete": True,
        "production_deployed": False,
        "whole_application_equivalent": False,
        "migration_complete": False,
        "production_ready": False,
    }
    if any(receipt.get(name) is not value for name, value in expected.items()):
        errors.append("cloudbank-production-readiness-receipt-claims-invalid")
    if validate_artifacts(project_root):
        errors.append("cloudbank-production-readiness-repository-artifacts-invalid")
    return sorted(set(errors))
