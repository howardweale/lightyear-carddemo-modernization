"""Durable, isolated GKE execution of the governed MS66 dual lane.

The source lane is created in a fresh namespace and uses native Oracle Free,
Oracle AQ/JMS, and Oracle MicroTx LRA.  Every mutation is preceded or followed
by a signed recovery checkpoint uploaded to the configured evidence prefix.
Cleanup validates Kubernetes UIDs and run labels before deleting anything.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from typing import Any, Callable, Mapping

from lightyear_common.io import write_json

from .cloudbank_edge_ai import validate_execution_receipt as validate_ms64_receipt
from .cloudbank_baseline import validate_source_checkout
from .cloudbank_journeys import JourneyFailure, execute_journeys, hashed, require
from .cloudbank_journeys_gke import GkeRuntime, command
from .cloudbank_ms66_dual_lane import (
    build_lane_observation,
    image_rows,
    recovery_state,
    validate_governed_source_lock,
    validate_recovery_state,
    validate_shared_journey,
)
from .cloudbank_ms66_hardening import (
    HARDENING_CONTRACT_SHA256,
    IMMUTABLE_IMAGE,
    PATCH_SHA256,
)
from .cloudbank_oracle_equivalence import validate_execution_receipt as validate_ms61_receipt
from .cloudbank_production_readiness import validate_image_lock
from .cloudbank_whole_application_equivalence import (
    RECEIPT_NAME,
    SERVICES,
    execute_equivalence,
    validate_artifacts,
)
from .contracts import content_hash, sign


DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
AUTH_SECRET = "cloudbank-azn-server-external"
APP_ORDER = (
    "azn-server", "customer", "account", "transfer", "checks", "testrunner",
    "creditscore", "chatbot",
)
SCHEMA_BY_SERVICE = {
    "azn-server": "USER_REPO",
    "customer": "CUSTOMER",
    "account": "ACCOUNT",
    "transfer": "TRANSFER",
    "checks": "ACCOUNT",
    "testrunner": "ACCOUNT",
    "creditscore": "CREDITSCORE",
    "chatbot": "CHATBOT",
}
ORACLE_RUNTIME = {
    "database": "oracle-free",
    "messaging": "oracle-aq-jms",
    "transactions": "oracle-microtx-lra",
}


def _bounded_write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_json(temporary, dict(payload))
    temporary.chmod(0o600)
    temporary.replace(path)


class EvidenceStore:
    """Persist only bounded JSON evidence locally and, optionally, in GCS."""

    def __init__(self, output: Path, project: str, prefix: str | None):
        require(DNS_LABEL.fullmatch(project) is not None and len(project) <= 63,
                "ms66-evidence-project-invalid")
        if prefix:
            require(re.fullmatch(r"gs://[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]"
                                   r"(?:/[A-Za-z0-9._-]+)*", prefix.rstrip("/")) is not None,
                    "ms66-evidence-prefix-invalid")
        self.output = output
        self.project = project
        self.prefix = prefix.rstrip("/") if prefix else None
        self.output.mkdir(parents=True, exist_ok=False, mode=0o700)

    def put(self, name: str, payload: Mapping[str, Any]) -> Path:
        require(re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,100}\.json", name) is not None,
                "ms66-evidence-name-invalid")
        path = self.output / name
        _bounded_write(path, payload)
        require(path.stat().st_size <= 4 * 1024 * 1024, "ms66-evidence-file-too-large")
        if self.prefix:
            command(["gcloud", "storage", "cp", str(path), self.prefix + "/" + name,
                     "--project", self.project], timeout=180)
        return path

    def sums(self) -> Path:
        rows = []
        for path in sorted(self.output.glob("*.json")):
            rows.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  ./" + path.name + "\n")
        target = self.output / "SHA256SUMS"
        target.write_text("".join(rows), encoding="utf-8")
        target.chmod(0o600)
        if self.prefix:
            command(["gcloud", "storage", "cp", str(target), self.prefix + "/SHA256SUMS",
                     "--project", self.project], timeout=180)
        return target


def _metadata(name: str, namespace: str | None, run_id: str, **labels: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "name": name,
        "labels": {
            "app.kubernetes.io/managed-by": "lightyear-ms66",
            "lightyear.ai/ms66-run": run_id,
            **labels,
        },
    }
    if namespace:
        metadata["namespace"] = namespace
    return metadata


def _env(name: str, value: str | None = None, *, secret_key: str | None = None,
         secret_name: str = "ms66-oracle-credentials") -> dict[str, Any]:
    row: dict[str, Any] = {"name": name}
    if secret_key:
        row["valueFrom"] = {"secretKeyRef": {"name": secret_name, "key": secret_key}}
    else:
        row["value"] = value
    return row


def _service_environment(service: str, namespace: str, model_namespace: str,
                         model_name: str) -> list[dict[str, Any]]:
    jdbc = "jdbc:oracle:thin:@//oracle:1521/FREEPDB1"
    issuer = f"http://azn-server.{namespace}.svc.cluster.local:8080"
    token_uri = issuer + "/oauth2/token"
    rows = [
        _env("SERVER_PORT", "8080"),
        _env("SERVER_ADDRESS", "0.0.0.0"),
        _env("EUREKA_CLIENT_ENABLED", "false"),
        _env("SPRING_CLOUD_DISCOVERY_ENABLED", "false"),
        _env("SPRING_CLOUD_CONFIG_ENABLED", "false"),
        _env("SPRING_SECURITY_OAUTH2_RESOURCESERVER_JWT_JWK_SET_URI", issuer + "/oauth2/jwks"),
        _env("CLOUDBANK_SECURITY_JWK_SET_URI", issuer + "/oauth2/jwks"),
        _env("CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN", "true"),
        _env("CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED", "true"),
        _env("CLOUDBANK_SECURITY_SERVICE_TOKEN_URI", token_uri),
        _env("CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_ID", secret_key="service-client-id",
             secret_name="ms66-authorization"),
        _env("CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_SECRET", secret_key="service-client-secret",
             secret_name="ms66-authorization"),
        _env("CLOUDBANK_SECURITY_SERVICE_TOKEN_SCOPE", "cloudbank.internal"),
        _env("SPRING_DATASOURCE_URL", jdbc),
        _env("SPRING_DATASOURCE_USERNAME", SCHEMA_BY_SERVICE[service]),
        _env("SPRING_DATASOURCE_USER", SCHEMA_BY_SERVICE[service]),
        _env("SPRING_DATASOURCE_PASSWORD", secret_key="schema-password"),
        _env("SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT", "org.hibernate.dialect.OracleDialect"),
        _env("LIQUIBASE_DATASOURCE_URL", jdbc),
        _env("LIQUIBASE_DATASOURCE_USERNAME", SCHEMA_BY_SERVICE[service]),
        _env("LIQUIBASE_DATASOURCE_PASSWORD", secret_key="schema-password"),
        _env("LIQUIBASE_ENABLED", "true" if service in {"account", "customer"} else "false"),
    ]
    if service == "azn-server":
        rows.extend([
            _env("RUN_LIQUIBASE", "true"),
            _env("AZN_DATASOURCE_URL", jdbc),
            _env("AZN_USER_REPO_USERNAME", "USER_REPO"),
            _env("AZN_USER_REPO_PASSWORD", secret_key="schema-password"),
            _env("AZN_LIQUIBASE_URL", jdbc),
            _env("AZN_LIQUIBASE_USERNAME", "SYSTEM"),
            _env("AZN_LIQUIBASE_PASSWORD", secret_key="oracle-password"),
            _env("AZN_AUTHORIZATION_SERVER_ISSUER", issuer),
            _env("AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_ENABLED", "true"),
            _env("AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_ID",
                 secret_key="AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_ID",
                 secret_name="ms66-authorization"),
            _env("AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SECRET",
                 secret_key="AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SECRET",
                 secret_name="ms66-authorization"),
            _env("AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SCOPES",
                 "cloudbank.read,cloudbank.write,cloudbank.transfer"),
            _env("AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_ID",
                 secret_key="AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_ID",
                 secret_name="ms66-authorization"),
            _env("AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SECRET",
                 secret_key="AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SECRET",
                 secret_name="ms66-authorization"),
            _env("AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SCOPES", "cloudbank.internal"),
            _env("AZN_AUTHORIZATION_SERVER_TEST_CLIENT_ID",
                 secret_key="AZN_AUTHORIZATION_SERVER_TEST_CLIENT_ID",
                 secret_name="ms66-authorization"),
            _env("AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SECRET",
                 secret_key="AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SECRET",
                 secret_name="ms66-authorization"),
            _env("AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SCOPES", "cloudbank.test"),
            _env("AZN_AUTHORIZATION_SERVER_SIGNING_KEY_PRIVATE_KEY_PATH",
                 "/var/run/secrets/cloudbank/signing/private.pem"),
            _env("AZN_AUTHORIZATION_SERVER_SIGNING_KEY_PUBLIC_KEY_PATH",
                 "/var/run/secrets/cloudbank/signing/public.pem"),
            _env("AZN_AUTHORIZATION_SERVER_SIGNING_KEY_KEY_ID", "cloudbank-ms66"),
            _env("AZN_BOOTSTRAP_USERS_ENABLED", "false"),
        ])
    if service in {"account", "transfer"}:
        rows.append(_env("MP_LRA_COORDINATOR_URL", "http://microtx:9000/api/v1/lra-coordinator"))
    if service == "checks":
        rows.append(_env("ACCOUNT_BASE_URL", "http://account:8080"))
    if service == "chatbot":
        rows.extend([
            _env("SPRING_AI_OLLAMA_BASE_URL",
                 f"http://ollama.{model_namespace}.svc.cluster.local:11434"),
            _env("SPRING_AI_OLLAMA_CHAT_OPTIONS_MODEL", model_name),
        ])
    return rows


def _application_resources(service: str, image: str, namespace: str, run_id: str,
                           model_namespace: str, model_name: str) -> list[dict[str, Any]]:
    labels = {"app.kubernetes.io/name": service, "app.kubernetes.io/part-of": "cloudbank-ms66-source"}
    volumes: list[dict[str, Any]] = [{"name": "tmp", "emptyDir": {"sizeLimit": "128Mi"}}]
    mounts: list[dict[str, Any]] = [{"name": "tmp", "mountPath": "/tmp"}]
    if service == "azn-server":
        volumes.append({
            "name": "signing-keys",
            "secret": {
                "secretName": "ms66-authorization",
                "items": [
                    {"key": "private.pem", "path": "private.pem"},
                    {"key": "public.pem", "path": "public.pem"},
                ],
            },
        })
        mounts.append({
            "name": "signing-keys",
            "mountPath": "/var/run/secrets/cloudbank/signing",
            "readOnly": True,
        })
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": _metadata(service, namespace, run_id, **labels),
        "spec": {
            "replicas": 1,
            "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}},
            "selector": {"matchLabels": {"app.kubernetes.io/name": service}},
            "template": {
                "metadata": {"labels": {**labels, "lightyear.ai/ms66-run": run_id}},
                "spec": {
                    "serviceAccountName": service,
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532,
                        "fsGroup": 65532, "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [{
                        "name": service,
                        "image": image,
                        "imagePullPolicy": "IfNotPresent",
                        "ports": [{"name": "http", "containerPort": 8080}],
                        "env": _service_environment(service, namespace, model_namespace, model_name),
                        "startupProbe": {
                            "httpGet": {"path": "/actuator/health/liveness", "port": "http"},
                            "failureThreshold": 60, "periodSeconds": 10,
                        },
                        "livenessProbe": {
                            "httpGet": {"path": "/actuator/health/liveness", "port": "http"},
                            "periodSeconds": 15, "timeoutSeconds": 3, "failureThreshold": 4,
                        },
                        "readinessProbe": {
                            "httpGet": {"path": "/actuator/health/readiness", "port": "http"},
                            "periodSeconds": 5, "timeoutSeconds": 3, "failureThreshold": 6,
                        },
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "384Mi"},
                            "limits": {"cpu": "1", "memory": "1Gi"},
                        },
                        "securityContext": {
                            "allowPrivilegeEscalation": False,
                            "readOnlyRootFilesystem": True,
                            "capabilities": {"drop": ["ALL"]},
                        },
                        "volumeMounts": mounts,
                    }],
                    "volumes": volumes,
                },
            },
        },
    }
    return [
        {"apiVersion": "v1", "kind": "ServiceAccount",
         "metadata": _metadata(service, namespace, run_id, **labels),
         "automountServiceAccountToken": False},
        {"apiVersion": "v1", "kind": "Service", "metadata": _metadata(service, namespace, run_id, **labels),
         "spec": {"selector": {"app.kubernetes.io/name": service},
                  "ports": [{"name": "http", "port": 8080, "targetPort": "http"}]}},
        deployment,
        {"apiVersion": "policy/v1", "kind": "PodDisruptionBudget",
         "metadata": _metadata(service, namespace, run_id, **labels),
         "spec": {"minAvailable": 1, "selector": {"matchLabels": {"app.kubernetes.io/name": service}}}},
    ]


def isolated_lane_resources(
    *, namespace: str, run_id: str, images: Mapping[str, str], oracle_image: str,
    microtx_image: str, authorization: Mapping[str, str], oracle_password: str,
    schema_password: str, model_namespace: str, model_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build namespace-scoped resources; secret values must never be persisted as evidence."""
    if any(not DNS_LABEL.fullmatch(value) or len(value) > 63
           for value in (namespace, model_namespace)) \
            or set(images) != set(SERVICES) \
            or any(not IMMUTABLE_IMAGE.fullmatch(value)
                   for value in (*images.values(), oracle_image, microtx_image)) \
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model_name) is None \
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{19,63}", oracle_password) \
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{19,63}", schema_password):
        raise ValueError("cloudbank-ms66-isolated-lane-input-invalid")
    required_auth = {
        "private.pem", "public.pem", "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_ID",
        "AZN_AUTHORIZATION_SERVER_DEFAULT_CLIENT_SECRET",
        "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_ID",
        "AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SECRET",
        "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_ID",
        "AZN_AUTHORIZATION_SERVER_TEST_CLIENT_SECRET",
    }
    if not required_auth <= set(authorization) \
            or any(not isinstance(authorization[name], str) or not authorization[name]
                   for name in required_auth):
        raise ValueError("cloudbank-ms66-authorization-secret-shape-invalid")
    auth_data = {name: authorization[name] for name in required_auth}
    auth_data.update({
        "service-client-id": authorization["AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_ID"],
        "service-client-secret": authorization["AZN_AUTHORIZATION_SERVER_SERVICE_CLIENT_SECRET"],
    })
    resources: list[dict[str, Any]] = [
        {"apiVersion": "v1", "kind": "Secret",
         "metadata": _metadata("ms66-oracle-credentials", namespace, run_id),
         "type": "Opaque",
         "stringData": {"oracle-password": oracle_password, "schema-password": schema_password}},
        {"apiVersion": "v1", "kind": "Secret",
         "metadata": _metadata("ms66-authorization", namespace, run_id),
         "type": "Opaque", "stringData": auth_data},
        {"apiVersion": "v1", "kind": "Service",
         "metadata": _metadata("oracle", namespace, run_id,
                               **{"app.kubernetes.io/name": "oracle", "app.kubernetes.io/part-of": "cloudbank-ms66-source"}),
         "spec": {"clusterIP": "None", "selector": {"app.kubernetes.io/name": "oracle"},
                  "ports": [{"name": "oracle", "port": 1521, "targetPort": 1521}]}},
        {
            "apiVersion": "apps/v1", "kind": "StatefulSet",
            "metadata": _metadata("oracle", namespace, run_id,
                                  **{"app.kubernetes.io/name": "oracle", "app.kubernetes.io/part-of": "cloudbank-ms66-source"}),
            "spec": {
                "serviceName": "oracle", "replicas": 1,
                "selector": {"matchLabels": {"app.kubernetes.io/name": "oracle"}},
                "template": {
                    "metadata": {"labels": {"app.kubernetes.io/name": "oracle",
                                            "app.kubernetes.io/part-of": "cloudbank-ms66-source",
                                            "lightyear.ai/ms66-run": run_id}},
                    "spec": {"containers": [{
                        "name": "oracle", "image": oracle_image, "imagePullPolicy": "IfNotPresent",
                        "ports": [{"name": "oracle", "containerPort": 1521}],
                        "env": [
                            _env("ORACLE_PASSWORD", secret_key="oracle-password"),
                            _env("ENABLE_ARCHIVELOG", "false"),
                        ],
                        "readinessProbe": {"tcpSocket": {"port": "oracle"},
                                           "initialDelaySeconds": 20, "periodSeconds": 10,
                                           "failureThreshold": 60},
                        "resources": {"requests": {"cpu": "1", "memory": "2Gi"},
                                      "limits": {"cpu": "2", "memory": "4Gi"}},
                        "volumeMounts": [{"name": "data", "mountPath": "/opt/oracle/oradata"}],
                    }], "volumes": [{"name": "data", "emptyDir": {"sizeLimit": "8Gi"}}]},
                },
            },
        },
        {"apiVersion": "v1", "kind": "Service",
         "metadata": _metadata("microtx", namespace, run_id,
                               **{"app.kubernetes.io/name": "microtx", "app.kubernetes.io/part-of": "cloudbank-ms66-source"}),
         "spec": {"selector": {"app.kubernetes.io/name": "microtx"},
                  "ports": [{"name": "http", "port": 9000, "targetPort": "http"}]}},
        {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": _metadata("microtx", namespace, run_id,
                                  **{"app.kubernetes.io/name": "microtx", "app.kubernetes.io/part-of": "cloudbank-ms66-source"}),
            "spec": {
                "replicas": 1, "selector": {"matchLabels": {"app.kubernetes.io/name": "microtx"}},
                "template": {
                    "metadata": {"labels": {"app.kubernetes.io/name": "microtx",
                                            "app.kubernetes.io/part-of": "cloudbank-ms66-source",
                                            "lightyear.ai/ms66-run": run_id}},
                    "spec": {"containers": [{
                        "name": "microtx", "image": microtx_image, "imagePullPolicy": "IfNotPresent",
                        "ports": [{"name": "http", "containerPort": 9000}],
                        "env": [
                            _env("TMM_APPNAME", "microtx"), _env("PORT", "9000"),
                            _env("ID", "MS066"), _env("APPLICATION_NAMESPACE", namespace),
                            _env("LISTEN_ADDR", "0.0.0.0:9000"),
                            _env("INTERNAL_ADDR", "http://microtx:9000"),
                            _env("EXTERNAL_ADDR", "http://microtx:9000"),
                            _env("XA_COORDINATOR_ENABLED", "false"),
                            _env("LRA_COORDINATOR_ENABLED", "true"),
                            _env("TCC_COORDINATOR_ENABLED", "false"),
                            _env("NARAYANA_LRA_COMPATIBILITY_MODE", "false"),
                            _env("AUTHENTICATION_ENABLED", "false"),
                            _env("AUTHORIZATION_ENABLED", "false"),
                            _env("SERVE_TLS_ENABLED", "false"),
                            _env("LOGGING_LEVEL", "info"), _env("LOGGING_DEV_MODE", "false"),
                        ],
                        "readinessProbe": {"httpGet": {"path": "/health", "port": "http"},
                                           "initialDelaySeconds": 10, "periodSeconds": 5,
                                           "failureThreshold": 60},
                        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"},
                                      "limits": {"cpu": "1", "memory": "1Gi"}},
                    }]},
                },
            },
        },
        {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
         "metadata": _metadata("default-deny", namespace, run_id),
         "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}},
        {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
         "metadata": _metadata("source-lane-traffic", namespace, run_id),
         "spec": {
             "podSelector": {}, "policyTypes": ["Ingress", "Egress"],
             "ingress": [{"from": [{"podSelector": {}}]}],
             "egress": [
                 {"to": [{"podSelector": {}}]},
                 {"to": [{"namespaceSelector": {"matchLabels": {
                     "kubernetes.io/metadata.name": "kube-system"}}}],
                  "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
             ],
         }},
        {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
         "metadata": _metadata("chatbot-model-egress", namespace, run_id),
         "spec": {
             "podSelector": {"matchLabels": {"app.kubernetes.io/name": "chatbot"}},
             "policyTypes": ["Egress"],
             "egress": [{"to": [{
                 "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": model_namespace}},
                 "podSelector": {"matchLabels": {"app.kubernetes.io/name": "ollama"}},
             }], "ports": [{"protocol": "TCP", "port": 11434}]}],
         }},
    ]
    for service in APP_ORDER:
        resources.extend(_application_resources(
            service, images[service], namespace, run_id, model_namespace, model_name,
        ))
    policy = {
        "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": _metadata("ms66-" + hashed(run_id)[:12], model_namespace, run_id),
        "spec": {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "ollama"}},
            "policyTypes": ["Ingress"],
            "ingress": [{"from": [{
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": namespace}},
                "podSelector": {"matchLabels": {"app.kubernetes.io/name": "chatbot"}},
            }], "ports": [{"protocol": "TCP", "port": 11434}]}],
        },
    }
    return resources, policy


class IsolatedOracleLane:
    """Provision and identity-safely remove one isolated source lane."""

    def __init__(self, *, project: str, region: str, cluster: str, namespace: str,
                 model_namespace: str, model_name: str, run_id: str,
                 source_lock: Mapping[str, Any], key: str, signer: str,
                 evidence: EvidenceStore, progress: Callable[[str], None] = lambda _: None):
        for value in (project, region, cluster, namespace, model_namespace, run_id):
            require(isinstance(value, str) and value and not any(c.isspace() for c in value),
                    "ms66-isolated-lane-identity-invalid")
        require(DNS_LABEL.fullmatch(namespace) is not None and len(namespace) <= 63
                and DNS_LABEL.fullmatch(model_namespace) is not None and len(model_namespace) <= 63,
                "ms66-isolated-lane-namespace-invalid")
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model_name) is not None,
                "ms66-isolated-lane-model-name-invalid")
        require(not validate_governed_source_lock(source_lock, key), "ms66-governed-source-lock-invalid")
        self.project, self.region, self.cluster = project, region, cluster
        self.namespace, self.model_namespace, self.model_name = namespace, model_namespace, model_name
        self.run_id, self.source_lock = run_id, dict(source_lock)
        self.key, self.signer, self.evidence, self.progress = key, signer, evidence, progress
        self.context = f"gke_{project}_{region}_{cluster}"
        self.namespace_uid: str | None = None
        self.policy_name = "ms66-" + hashed(run_id)[:12]
        self.policy_uid: str | None = None
        self.phase = "planned"
        self.checkpoint()

    def kubectl(self, *args: str, data: str | None = None, timeout=90) -> str:
        return command(["kubectl", "--context", self.context, "--request-timeout=60s", *args],
                       data=data, timeout=timeout)

    def apply(self, resources: list[dict[str, Any]], *, namespace: str | None = None) -> None:
        body = {"apiVersion": "v1", "kind": "List", "items": resources}
        args = ["apply", "-f", "-"]
        if namespace:
            args = ["-n", namespace, *args]
        self.kubectl(*args, data=json.dumps(body), timeout=180)

    def checkpoint(self) -> dict[str, Any]:
        state = recovery_state(
            run_id=self.run_id, context=self.context, namespace=self.namespace,
            source_image_lock_sha256=str(self.source_lock["content_sha256"]), phase=self.phase,
            namespace_uid=self.namespace_uid, model_namespace=self.model_namespace,
            model_policy_name=self.policy_name, model_policy_uid=self.policy_uid,
            cleanup_required=self.phase not in {"planned", "restored"},
            key=self.key, signer=self.signer,
        )
        self.evidence.put("recovery-state.json", state)
        return state

    def _authorization(self) -> dict[str, str]:
        raw = command(["gcloud", "secrets", "versions", "access", "latest", "--secret", AUTH_SECRET,
                       "--project", self.project])
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise JourneyFailure("ms66-authorization-secret-json-invalid") from None
        require(isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                for k, v in value.items()),
                "ms66-authorization-secret-json-invalid")
        return value

    def _wait_oracle(self) -> None:
        self.kubectl("-n", self.namespace, "rollout", "status", "statefulset/oracle",
                     "--timeout=15m", timeout=930)
        sql = "whenever sqlerror exit failure\nselect 1 from dual;\nexit\n"
        deadline = time.monotonic() + 300
        while True:
            try:
                self.kubectl("-n", self.namespace, "exec", "-i", "pod/oracle-0", "--",
                             "sqlplus", "-L", "-S", "/", "as", "sysdba", data=sql, timeout=45)
                return
            except JourneyFailure:
                require(time.monotonic() < deadline, "ms66-oracle-readiness-timeout")
                time.sleep(5)

    def _bootstrap_oracle(self) -> None:
        schema_password = self._schema_password
        users = ("ACCOUNT", "CUSTOMER", "TRANSFER", "CREDITSCORE", "CHATBOT")
        statements = [
            "whenever sqlerror exit failure",
            "alter session set container=FREEPDB1;",
        ]
        for user in users:
            statements.extend([
                f'create user "{user}" identified by "{schema_password}";',
                f'grant create session, create table, create sequence, create procedure, create trigger to "{user}";',
                f'alter user "{user}" quota unlimited on users;',
            ])
        statements.extend([
            "grant execute on dbms_aq to account;",
            "grant execute on dbms_aqadm to account;",
            "grant execute on dbms_aqin to account;",
            "grant execute on dbms_aqjms to account;",
            "grant execute on dbms_aqjms_internal to account;",
            "exit",
        ])
        self.kubectl("-n", self.namespace, "exec", "-i", "pod/oracle-0", "--",
                     "sqlplus", "-L", "-S", "/", "as", "sysdba",
                     data="\n".join(statements) + "\n", timeout=180)

    def provision(self) -> None:
        self.progress("Validating fresh isolated namespace and model namespace")
        existing = self.kubectl("get", "namespace", self.namespace, "--ignore-not-found", "-o", "json")
        require(not existing.strip(), "ms66-isolated-namespace-already-exists")
        model = json.loads(self.kubectl("get", "namespace", self.model_namespace, "-o", "json"))
        require(model.get("metadata", {}).get("labels", {}).get("environment") in
                {"non-production", "nonprod", "test", "sandbox"},
                "ms66-model-namespace-not-non-production")
        self.phase = "namespace-create-pending"
        self.checkpoint()
        namespace = {
            "apiVersion": "v1", "kind": "Namespace",
            "metadata": _metadata(self.namespace, None, self.run_id,
                                  environment="non-production",
                                  **{"pod-security.kubernetes.io/enforce": "baseline"}),
        }
        self.apply([namespace])
        current = json.loads(self.kubectl("get", "namespace", self.namespace, "-o", "json"))
        self.namespace_uid = current["metadata"]["uid"]
        self.phase = "namespace-created"
        self.checkpoint()

        self._oracle_password = "L" + secrets.token_hex(16)
        self._schema_password = "S" + secrets.token_hex(16)
        images = image_rows(self.source_lock)
        native = self.source_lock["native_runtime_images"]
        resources, policy = isolated_lane_resources(
            namespace=self.namespace, run_id=self.run_id, images=images,
            oracle_image=native["oracle"], microtx_image=native["microtx"],
            authorization=self._authorization(), oracle_password=self._oracle_password,
            schema_password=self._schema_password, model_namespace=self.model_namespace,
            model_name=self.model_name,
        )
        self.phase = "model-policy-create-pending"
        self.checkpoint()
        self.apply([policy], namespace=self.model_namespace)
        created_policy = json.loads(self.kubectl("-n", self.model_namespace, "get", "networkpolicy",
                                                self.policy_name, "-o", "json"))
        self.policy_uid = created_policy["metadata"]["uid"]
        self.phase = "model-policy-created"
        self.checkpoint()

        application = [
            row for row in resources
            if row.get("metadata", {}).get("name") in APP_ORDER
        ]
        infrastructure = [row for row in resources if row not in application]
        self.progress("Starting isolated native Oracle Free")
        self.apply(infrastructure, namespace=self.namespace)
        self._wait_oracle()
        self._bootstrap_oracle()
        self.kubectl("-n", self.namespace, "rollout", "status", "deployment/microtx",
                     "--timeout=10m", timeout=630)
        self.phase = "native-runtime-ready"
        self.checkpoint()

        for service in APP_ORDER:
            self.progress("Starting governed Oracle source service: " + service)
            rows = [row for row in application if row.get("metadata", {}).get("name") == service]
            require(len(rows) == 4, "ms66-source-service-resource-set-invalid")
            self.apply(rows, namespace=self.namespace)
            self.kubectl("-n", self.namespace, "rollout", "status", "deployment/" + service,
                         "--timeout=10m", timeout=630)
        for service in APP_ORDER:
            self.kubectl("-n", self.namespace, "scale", "deployment/" + service, "--replicas=2")
        for service in APP_ORDER:
            self.kubectl("-n", self.namespace, "rollout", "status", "deployment/" + service,
                         "--timeout=10m", timeout=630)
        self.phase = "eight-source-services-ready"
        self.checkpoint()
        self._oracle_password = self._schema_password = ""

    def cleanup(self) -> dict[str, Any]:
        errors: list[str] = []
        if self.phase == "planned" and self.namespace_uid is None and self.policy_uid is None:
            self.phase = "restored"
            self.checkpoint()
            return {"status": "restored", "errors": [],
                    "remaining_isolated_namespace": None, "remaining_model_policy": None}
        try:
            self.phase = "cleanup-pending"
            self.checkpoint()
        except Exception:
            return {"status": "failed", "errors": ["cleanup-checkpoint-failed"],
                    "remaining_isolated_namespace": self.namespace,
                    "remaining_model_policy": self.policy_name}
        if self.phase != "planned":
            try:
                raw = self.kubectl("-n", self.model_namespace, "get", "networkpolicy", self.policy_name,
                                   "--ignore-not-found", "-o", "json")
                if raw.strip():
                    policy = json.loads(raw)
                    require((self.policy_uid is None
                             or policy["metadata"]["uid"] == self.policy_uid)
                            and policy["metadata"].get("labels", {}).get("lightyear.ai/ms66-run") == self.run_id
                            and policy["metadata"].get("labels", {}).get(
                                "app.kubernetes.io/managed-by") == "lightyear-ms66",
                            "ms66-model-policy-cleanup-identity-drift")
                    self.kubectl("-n", self.model_namespace, "delete", "networkpolicy", self.policy_name,
                                 "--wait=true", "--timeout=2m", timeout=150)
                self.policy_uid = None
            except Exception:
                errors.append("model-policy-cleanup-failed")
        if self.phase != "planned":
            try:
                raw = self.kubectl("get", "namespace", self.namespace, "--ignore-not-found", "-o", "json")
                if raw.strip():
                    namespace = json.loads(raw)
                    labels = namespace["metadata"].get("labels", {})
                    require((self.namespace_uid is None
                             or namespace["metadata"]["uid"] == self.namespace_uid)
                            and labels.get("lightyear.ai/ms66-run") == self.run_id
                            and labels.get("environment") == "non-production"
                            and labels.get("app.kubernetes.io/managed-by") == "lightyear-ms66",
                            "ms66-namespace-cleanup-identity-drift")
                    self.kubectl("delete", "namespace", self.namespace, "--wait=true", "--timeout=15m",
                                 timeout=930)
                self.namespace_uid = None
            except Exception:
                errors.append("isolated-namespace-cleanup-failed")
        if not errors:
            self.phase = "restored"
            self.checkpoint()
        return {"status": "restored" if not errors else "failed", "errors": errors,
                "remaining_isolated_namespace": self.namespace
                if "isolated-namespace-cleanup-failed" in errors else None,
                "remaining_model_policy": self.policy_name
                if "model-policy-cleanup-failed" in errors else None}


class OracleGkeRuntime(GkeRuntime):
    """Shared-journey adapter for the isolated Oracle/AQ source lane."""

    def __init__(self, **kwargs: Any):
        super().__init__(checks_delivery_env="ACCOUNT_BASE_URL",
                         checks_blocked_url="http://192.0.2.1:8080", probe_image=None, **kwargs)

    def load_credentials(self):
        secret = self.secret_json(AUTH_SECRET)
        prefixes = {"owner": "DEFAULT", "account": "SERVICE", "test": "TEST",
                    "credit": "DEFAULT", "chat": "DEFAULT"}
        for role, prefix in prefixes.items():
            client = secret.get(f"AZN_AUTHORIZATION_SERVER_{prefix}_CLIENT_ID", "")
            password = secret.get(f"AZN_AUTHORIZATION_SERVER_{prefix}_CLIENT_SECRET", "")
            require(bool(client and password), "oauth-client-configuration-missing")
            self.credentials[role] = (client, password)
        self.owner = self.credentials["owner"][0]
        require(re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", self.owner) is not None,
                "synthetic-owner-id-invalid")

    def queue(self, message_id: str) -> dict:
        require(re.fullmatch(r"ly-[0-9a-f]{48}", message_id) is not None,
                "queue-message-identity-invalid")
        sql = (
            "set heading off feedback off pagesize 0 linesize 32767 trimspool on\n"
            "whenever sqlerror exit failure\n"
            "alter session set container=FREEPDB1;\n"
            "select nvl((select json_object('state' value state, 'attempts' value attempts, "
            "'error_code' value last_error_code null on null) from account.ms66_check_messages "
            f"where message_id='{message_id}'), '{{}}') from dual;\nexit\n"
        )
        raw = self.kubectl("exec", "-i", "pod/oracle-0", "--", "sqlplus", "-L", "-S", "/",
                           "as", "sysdba", data=sql, timeout=45).strip()
        try:
            result = json.loads(raw or "{}")
        except (ValueError, UnicodeError):
            raise JourneyFailure("oracle-queue-probe-output-invalid") from None
        require(isinstance(result, dict) and set(result) in (set(), {"state", "attempts", "error_code"}),
                "oracle-queue-probe-fields-invalid")
        if result:
            require(result["state"] in {"READY", "PROCESSING", "PROCESSED"}
                    and type(result["attempts"]) is int and 0 <= result["attempts"] <= 100,
                    "oracle-queue-probe-values-invalid")
            error = result["error_code"]
            require(error is None or (isinstance(error, str)
                    and re.fullmatch(r"[A-Za-z][A-Za-z0-9_$]{0,79}", error) is not None),
                    "oracle-queue-error-code-invalid")
        return result


def cleanup_from_recovery_state(state: Mapping[str, Any], key: str) -> dict[str, Any]:
    """Recover an interrupted lane using only a signed, identity-bound state."""
    errors = validate_recovery_state(state, key)
    if errors:
        raise ValueError(",".join(errors))
    if not state["cleanup_required"]:
        return {"status": "restored", "errors": [], "remaining_isolated_namespace": None,
                "remaining_model_policy": None}
    context = str(state["context"])
    run_id = str(state["run_id"])

    def kubectl(*args: str, timeout=180) -> str:
        return command(["kubectl", "--context", context, "--request-timeout=60s", *args], timeout=timeout)

    failures: list[str] = []
    policy_uid = state.get("model_policy_uid")
    if state["cleanup_required"]:
        try:
            raw = kubectl("-n", str(state["model_namespace"]), "get", "networkpolicy",
                          str(state["model_policy_name"]), "--ignore-not-found", "-o", "json")
            if raw.strip():
                current = json.loads(raw)
                require((policy_uid is None or current["metadata"]["uid"] == policy_uid)
                        and current["metadata"].get("labels", {}).get("lightyear.ai/ms66-run") == run_id
                        and current["metadata"].get("labels", {}).get(
                            "app.kubernetes.io/managed-by") == "lightyear-ms66",
                        "ms66-recovery-model-policy-identity-drift")
                kubectl("-n", str(state["model_namespace"]), "delete", "networkpolicy",
                        str(state["model_policy_name"]), "--wait=true", "--timeout=2m")
        except Exception:
            failures.append("model-policy-cleanup-failed")
    try:
        raw = kubectl("get", "namespace", str(state["namespace"]), "--ignore-not-found", "-o", "json")
        if raw.strip():
            current = json.loads(raw)
            require((state["namespace_uid"] is None
                     or current["metadata"]["uid"] == state["namespace_uid"])
                    and current["metadata"].get("labels", {}).get(
                        "app.kubernetes.io/managed-by") == "lightyear-ms66"
                    and all(current["metadata"].get("labels", {}).get(name) == value
                              for name, value in state["expected_namespace_labels"].items()),
                    "ms66-recovery-namespace-identity-drift")
            kubectl("delete", "namespace", str(state["namespace"]), "--wait=true", "--timeout=15m",
                    timeout=930)
    except Exception:
        failures.append("isolated-namespace-cleanup-failed")
    return {"status": "failed" if failures else "restored", "errors": failures,
            "remaining_isolated_namespace": str(state["namespace"])
            if "isolated-namespace-cleanup-failed" in failures else None,
            "remaining_model_policy": str(state["model_policy_name"])
            if "model-policy-cleanup-failed" in failures else None}


def execute_dual_lane(
    *, project_root: Path, source_root: Path, ms61: Mapping[str, Any], ms64: Mapping[str, Any],
    source_lock: Mapping[str, Any], target_lock: Mapping[str, Any], project: str, region: str,
    cluster: str, target_namespace: str, isolated_namespace: str, model_namespace: str,
    model_name: str, postgres_probe_image: str, output: Path, evidence_prefix: str | None,
    key: str, signer: str, run_id: str,
    progress: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """Run the isolated source and bound deployed target, then emit the MS66 receipt."""
    if not key or not signer.strip():
        raise ValueError("cloudbank-ms66-signing-identity-required")
    if not re.fullmatch(r"ms66-[a-z0-9-]{1,54}", run_id):
        raise ValueError("cloudbank-ms66-run-id-invalid")
    source_images = image_rows(source_lock)
    target_images = image_rows(target_lock)
    preflight_errors = validate_artifacts(project_root)
    preflight_errors += validate_source_checkout(source_root)
    preflight_errors += validate_governed_source_lock(source_lock, key)
    preflight_errors += validate_ms61_receipt(dict(ms61), key, project_root)
    preflight_errors += validate_ms64_receipt(dict(ms64), key, project_root)
    preflight_errors += validate_image_lock(dict(target_lock), str(ms64.get("content_sha256", "")))
    if source_lock.get("controller_commit") != subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=False,
    ).stdout.strip():
        preflight_errors.append("cloudbank-ms66-controller-commit-binding-invalid")
    if preflight_errors:
        raise ValueError(",".join(sorted(set(preflight_errors))))
    oracle_image = str(ms61.get("oracle_image_id_sha256", ""))
    postgres_image = str(ms61.get("postgresql_image_id_sha256", ""))
    if any(not HEX_64.fullmatch(value) for value in (
        str(ms61.get("content_sha256", "")), str(ms64.get("content_sha256", "")),
        oracle_image, postgres_image, str(source_lock.get("content_sha256", "")),
        str(target_lock.get("content_sha256", "")),
    )) or ms64.get("postgresql_image_id_sha256") != postgres_image:
        raise ValueError("cloudbank-ms66-input-chain-invalid")
    resolved_output = output.resolve()
    if resolved_output == project_root.resolve() \
            or resolved_output.is_relative_to(project_root.resolve()) \
            or resolved_output == source_root.resolve() \
            or resolved_output.is_relative_to(source_root.resolve()):
        raise ValueError("cloudbank-ms66-evidence-output-inside-source")
    signature = source_lock.get("signature") or {}
    if not isinstance(signature, Mapping) or signature.get("signer") != signer:
        raise ValueError("cloudbank-ms66-source-lock-signer-invalid")

    store = EvidenceStore(output, project, evidence_prefix)
    store.put("oracle-source-image-lock.json", source_lock)

    provisioner = IsolatedOracleLane(
        project=project, region=region, cluster=cluster, namespace=isolated_namespace,
        model_namespace=model_namespace, model_name=model_name, run_id=run_id,
        source_lock=source_lock, key=key, signer=signer, evidence=store, progress=progress,
    )
    oracle_journey: dict[str, Any] | None = None
    postgres_journey: dict[str, Any] | None = None
    postgres_runtime: GkeRuntime | None = None
    receipt: dict[str, Any] | None = None
    caught: BaseException | None = None
    cleanup = {"status": "failed", "errors": ["isolated-lane-not-cleaned"]}
    target_cleanup = {"status": "not-started", "errors": [],
                      "remaining_stopped_services": []}

    def checkpoint(name: str, payload: dict[str, Any]) -> None:
        store.put(name, sign(payload, key, signer))

    try:
        provisioner.provision()
        progress("Running all 18 shared journeys on native Oracle/AQ/MicroTx")
        oracle_runtime = OracleGkeRuntime(
            project=project, region=region, cluster=cluster, namespace=isolated_namespace,
            images=source_images, run_id=run_id + "-oracle", output=output / "oracle-runtime",
            progress=progress, signing_key=key, signer=signer,
        )
        oracle_runtime.output.mkdir(parents=True, exist_ok=True)
        oracle_bindings = {
            "lane": "gke-oracle-governed-source",
            "source_image_lock_sha256": source_lock["content_sha256"],
            "hardening_contract_sha256": HARDENING_CONTRACT_SHA256,
            "hardening_patch_sha256": PATCH_SHA256,
            "environment": oracle_runtime.environment(),
        }
        oracle_journey = execute_journeys(
            oracle_runtime, oracle_bindings, key, signer, run_id=run_id + "-oracle",
            progress=progress, checkpoint=lambda value: checkpoint("oracle-journeys.json", value),
        )
        errors = validate_shared_journey(
            oracle_journey, key, "oracle", image_lock_sha256=source_lock["content_sha256"],
            expected_images=source_images,
        )
        if errors:
            raise ValueError(",".join(errors))
        provisioner.phase = "journeys-complete"
        provisioner.checkpoint()
        cleanup = provisioner.cleanup()
        if cleanup["status"] != "restored":
            raise ValueError("cloudbank-ms66-isolated-lane-restoration-failed")

        progress("Running all 18 shared journeys on the bound deployed PostgreSQL target lane")
        postgres_runtime = GkeRuntime(
            project=project, region=region, cluster=cluster, namespace=target_namespace,
            images=target_images, run_id=run_id + "-postgresql", output=output / "postgres-runtime",
            probe_image=postgres_probe_image, progress=progress, signing_key=key, signer=signer,
            recovery_sink=lambda value: store.put("postgresql-recovery-state.json", value),
        )
        postgres_runtime.output.mkdir(parents=True, exist_ok=True)
        postgres_runtime.create_probe()
        postgres_bindings = {
            "lane": "gke-postgresql-target",
            "ms64_receipt_sha256": ms64["content_sha256"],
            "image_lock_sha256": target_lock["content_sha256"],
            "environment": postgres_runtime.environment(),
        }
        postgres_journey = execute_journeys(
            postgres_runtime, postgres_bindings, key, signer, run_id=run_id + "-postgresql",
            progress=progress, checkpoint=lambda value: checkpoint("postgresql-journeys.json", value),
        )
        errors = validate_shared_journey(
            postgres_journey, key, "postgresql", image_lock_sha256=target_lock["content_sha256"],
            expected_images=target_images,
        )
        if errors:
            raise ValueError(",".join(errors))

        oracle_journey_sha = str(oracle_journey["content_sha256"])
        postgres_journey_sha = str(postgres_journey["content_sha256"])
        shared = {
            "ms61_sha256": str(ms61["content_sha256"]),
            "ms64_sha256": str(ms64["content_sha256"]),
            "oracle_image_id_sha256": oracle_image,
            "postgresql_image_id_sha256": postgres_image,
            "comparison_run_id": run_id,
            "oracle_source_image_lock_sha256": str(source_lock["content_sha256"]),
            "postgresql_image_lock_sha256": str(target_lock["content_sha256"]),
            "oracle_journey_sha256": oracle_journey_sha,
            "postgresql_journey_sha256": postgres_journey_sha,
        }
        oracle_observation = build_lane_observation(
            oracle_journey, key, signer, "oracle", expected_images=source_images,
            recovery={"status": "restored", "errors": []}, **shared,
        )
        postgres_observation = build_lane_observation(
            postgres_journey, key, signer, "postgresql", expected_images=target_images,
            recovery={"status": "restored", "errors": []}, **shared,
        )
        store.put("oracle-lane-observation.json", oracle_observation)
        store.put("postgresql-lane-observation.json", postgres_observation)
        receipt_dir = output / "receipt"
        receipt = execute_equivalence(
            project_root, source_root, ms61, ms64, oracle_observation, postgres_observation,
            receipt_dir, key, signer, run_id,
        )
    except (Exception, KeyboardInterrupt) as exc:
        caught = exc
    finally:
        if postgres_runtime is not None:
            try:
                target_cleanup = postgres_runtime.close()
                if target_cleanup.get("status") != "restored" and caught is None:
                    caught = ValueError("cloudbank-ms66-postgresql-lane-restoration-failed")
            except Exception:
                target_cleanup = {"status": "failed",
                                  "errors": ["postgresql-runtime-restoration-failed"],
                                  "remaining_stopped_services": sorted(postgres_runtime.stopped)}
                if caught is None:
                    caught = ValueError("cloudbank-ms66-postgresql-lane-restoration-failed")
        if provisioner.namespace_uid is not None or provisioner.policy_uid is not None:
            cleanup = provisioner.cleanup()
        if cleanup.get("status") != "restored":
            caught = ValueError("cloudbank-ms66-isolated-lane-restoration-failed")
    if caught is not None:
        raw_reason = str(caught)
        reason_codes = sorted(set(
            item for item in raw_reason.split(",")
            if re.fullmatch(r"[a-z0-9-]{1,120}", item)
        ))
        failure = sign({
            "schema_version": "1.0",
            "failure_type": "lightyear-cloudbank-ms66-dual-lane-failure",
            "run_id": run_id,
            "reason_codes": reason_codes or [
                "operator-interrupted" if isinstance(caught, KeyboardInterrupt)
                else "bounded-ms66-execution-failed"
            ],
            "recovery": {
                "isolated_oracle_lane": cleanup,
                "postgresql_target_lane": target_cleanup,
            },
            "ms66_complete": False,
            "ms67_complete": False,
            "credentials_persisted": False,
            "raw_output_persisted": False,
        }, key, signer)
        store.put("ms66-failure.json", failure)
        store.sums()
        raise ValueError("cloudbank-ms66-dual-lane-execution-failed") from None
    if receipt is None:
        raise ValueError("cloudbank-ms66-receipt-not-produced")
    store.put(RECEIPT_NAME, receipt)
    store.sums()
    return receipt
