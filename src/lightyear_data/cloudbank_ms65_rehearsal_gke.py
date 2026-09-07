"""Live, fail-closed MS65 deployment rehearsal for the GKE PostgreSQL target.

The generic MS65 controller admits an operator observation; this module produces
that observation from bounded live checks.  It deliberately reuses independently
signed shared-journey and isolated-backup observations instead of pretending a
Kubernetes readiness response proves business behavior or database recovery.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Callable

from .cloudbank_journeys import (
    OBSERVATION_TYPE as JOURNEY_OBSERVATION_TYPE,
    SCENARIOS as JOURNEY_SCENARIOS,
    JourneyFailure,
    hashed,
    journey_contract,
    require,
)
from .cloudbank_journeys_gke import GkeRuntime, command
from .cloudbank_production_readiness import (
    CONTRACT_SHA256,
    RELEASE,
    SCENARIO_IDS,
    SERVICES,
    cutover_contract,
)
from .cloudbank_sql_recovery import OBSERVATION_TYPE as SQL_RECOVERY_OBSERVATION_TYPE
from .contracts import sign, verify_signature


STATE_TYPE = "lightyear-cloudbank-ms65-gke-recovery"
DETAIL_TYPE = "lightyear-cloudbank-ms65-gke-rehearsal-details"
OBSERVATION_TYPE = "lightyear-cloudbank-ms65-rehearsal-observation"
CANARY_SERVICE = "creditscore"
CANARY_NAME = "ly-ms65-creditscore-canary"
MINIMUM_SLO_REQUESTS = 100
MINIMUM_SLO_SECONDS = 60
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def verified(value: dict[str, Any], key: str, code: str) -> dict[str, Any]:
    require(value.get("content_sha256") == hashed_without_signature(value), code)
    require(verify_signature(value, key), code)
    require(bool(str((value.get("signature") or {}).get("signer", "")).strip()), code)
    return value


def hashed_without_signature(value: dict[str, Any]) -> str:
    """Return the repository contract hash without importing private helpers."""
    from .contracts import content_hash

    return content_hash(value)


def validate_shared_journeys(
    value: dict[str, Any], key: str, *, ms64_sha256: str,
    image_lock_sha256: str, environment: dict[str, Any],
) -> dict[str, Any]:
    verified(value, key, "passed-signed-shared-journeys-required")
    rows = value.get("scenarios") or []
    expected = [identifier for identifier, _ in JOURNEY_SCENARIOS]
    bindings = value.get("bindings") or {}
    recovery = value.get("recovery") or {}
    require(
        value.get("observation_type") == JOURNEY_OBSERVATION_TYPE
        and value.get("status") == "passed-shared-journeys"
        and value.get("scenario_count") == len(expected)
        and [row.get("id") for row in rows] == expected
        and all(
            row.get("status") == "passed"
            and row.get("normalized_result") == normalized
            and row.get("evidence_sha256") == hashed(row.get("evidence"))
            for row, (_, normalized) in zip(rows, JOURNEY_SCENARIOS, strict=True)
        )
        and recovery.get("status") == "restored"
        and not recovery.get("errors")
        and not recovery.get("remaining_stopped_services")
        and bindings.get("journey_contract_sha256") == journey_contract()["content_sha256"]
        and bindings.get("ms64_receipt_sha256") == ms64_sha256
        and bindings.get("image_lock_sha256") == image_lock_sha256
        and bindings.get("environment") == environment
        and value.get("synthetic_data_only") is True
        and value.get("raw_output_persisted") is False
        and value.get("credentials_persisted") is False
        and value.get("production_environment") is False
        and value.get("whole_application_equivalent") is False
        and value.get("ms65_complete") is False
        and value.get("ms66_complete") is False
        and value.get("ms67_complete") is False,
        "passed-bound-shared-journeys-required",
    )
    return {
        "content_sha256": value["content_sha256"],
        "scenario_count": len(rows),
        "recovery_status": "restored",
    }


def validate_database_recovery(
    value: dict[str, Any], key: str, *, images: dict[str, str],
    environment: dict[str, Any], journeys_sha256: str,
) -> dict[str, str]:
    verified(value, key, "passed-signed-database-recovery-required")
    bindings = value.get("bindings") or {}
    checkpoint = value.get("checkpoint") or {}
    backup = value.get("backup") or {}
    pitr = value.get("pitr") or {}
    restored = value.get("backup_restore") or {}
    restored_state = restored.get("restored_state") or {}
    pitr_state = pitr.get("restored_state") or {}
    recovery = value.get("recovery") or {}
    before_sha = checkpoint.get("state_sha256")
    restored_sha = restored_state.get("state_sha256")
    backup_sha = backup.get("metadata_sha256")
    backup_record = {name: backup.get(name) for name in (
        "id", "instance", "startTime", "endTime", "status", "type",
    )}
    require(
        value.get("observation_type") == SQL_RECOVERY_OBSERVATION_TYPE
        and value.get("status") == "passed-isolated-database-recovery"
        and bindings.get("environment") == environment
        and bindings.get("images_sha256") == hashed(images)
        and bindings.get("journeys_content_sha256") == journeys_sha256
        and all(HEX_64.fullmatch(str(item or "")) for item in (before_sha, restored_sha, backup_sha))
        and isinstance(checkpoint.get("databases"), dict)
        and bool(checkpoint["databases"])
        and checkpoint.get("state_sha256") == hashed(checkpoint.get("databases"))
        and pitr_state == checkpoint
        and restored_state == checkpoint
        and restored_sha == before_sha
        and all(item not in (None, "") for item in backup_record.values())
        and backup_sha == hashed(backup_record)
        and pitr.get("state_matches") is True
        and pitr.get("rpo_within_limit") is True
        and pitr.get("rto_within_limit") is True
        and type(pitr.get("recovery_point_age_seconds")) in {int, float}
        and 0 <= pitr["recovery_point_age_seconds"] <= 60
        and type(pitr.get("database_rto_seconds")) in {int, float}
        and 0 <= pitr["database_rto_seconds"] <= 600
        and restored.get("state_matches") is True
        and restored.get("rto_within_limit") is True
        and type(restored.get("database_rto_seconds")) in {int, float}
        and 0 <= restored["database_rto_seconds"] <= 600
        and backup.get("status") == "SUCCESSFUL"
        and backup.get("type") == "ON_DEMAND"
        and backup.get("retained") is True
        and backup.get("managed_backup_bytes_sha256") is None
        and recovery.get("status") == "restored"
        and not recovery.get("errors")
        and recovery.get("validation_instance_deleted") is True
        and recovery.get("validation_instance_state") == "deleted"
        and not recovery.get("remaining_stopped_services")
        and value.get("credentials_persisted") is False
        and value.get("raw_database_rows_persisted") is False
        and value.get("ms65_complete") is False
        and value.get("ms66_complete") is False
        and value.get("ms67_complete") is False,
        "passed-bound-database-recovery-required",
    )
    return {
        "pre_cutover_state_sha256": before_sha,
        # This is the content hash of the bounded provider backup identity and
        # timestamps, not a claim that Cloud SQL exposed raw backup bytes.
        "backup_sha256": backup_sha,
        "restored_state_sha256": restored_sha,
    }


class DurableJournal:
    """Persist signed mutation intent locally and to private GCS before acting."""

    def __init__(self, path: Path, key: str, signer: str, destination: str | None = None,
                 invoke: Callable[..., str] = command, project: str | None = None):
        self.path, self.key, self.signer = path, key, signer
        self.destination, self.invoke, self.project = destination, invoke, project

    def write(self, value: dict[str, Any]) -> dict[str, Any]:
        sealed = sign(value, self.key, self.signer)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.path)
        if self.destination:
            require(bool(self.project), "ms65-journal-project-required")
            self.invoke(["gcloud", "storage", "cp", str(self.path), self.destination,
                         "--project", self.project], timeout=180)
        return sealed


class Ms65GkeRehearsal:
    def __init__(
        self, runtime: GkeRuntime, environment: dict[str, Any], bundle: dict[str, Any],
        manifest: str, key: str, signer: str, journal: DurableJournal,
        *, clock: Callable[[], float] = time.monotonic,
        pause: Callable[[float], None] = time.sleep,
    ):
        self.runtime, self.environment, self.bundle, self.manifest = runtime, environment, bundle, manifest
        self.key, self.signer, self.journal = key, signer, journal
        self.clock, self.pause = clock, pause
        token = hashed(runtime.run_id)[:12]
        # The fixed object name is also an atomic cluster-side lock. A unique
        # run label and UID still bind cleanup to the creating execution.
        self.canary_name = CANARY_NAME
        self.canary_label = token
        self.state: dict[str, Any] = {
            "schema_version": "1.0", "state_type": STATE_TYPE,
            "run_id": runtime.run_id, "context": runtime.context,
            "namespace": runtime.namespace, "service": CANARY_SERVICE,
            "images": runtime.images, "canary_name": self.canary_name,
            "canary_label": self.canary_label, "phase": "initializing",
            "cutover_states": [],
            "service_uid": None, "original_selector": None,
            "canary_absent_before": False, "canary_uid": None,
            "switch_intent": False, "selector_switched": False,
            "cleanup_complete": False, "cleanup_errors": [],
            "canary_preserved": None, "updated_at": utc(),
        }

    def save(self, phase: str) -> None:
        required_states = cutover_contract()["required_state_sequence"]
        if phase in required_states:
            states = self.state.setdefault("cutover_states", [])
            if not states or states[-1] != phase:
                require(states == required_states[:len(states)]
                        and len(states) < len(required_states)
                        and phase == required_states[len(states)],
                        "ms65-cutover-state-transition-invalid")
                states.append(phase)
        self.state.update(phase=phase, updated_at=utc())
        self.journal.write(self.state)

    def _named(self, kind: str) -> dict[str, dict[str, Any]]:
        rows = self.runtime.get(kind).get("items", [])
        return {row.get("metadata", {}).get("name"): row for row in rows}

    @staticmethod
    def _main_container(deployment: dict[str, Any], service: str) -> dict[str, Any]:
        rows = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        matches = [row for row in rows if row.get("name") == service]
        require(len(rows) == 1 and len(matches) == 1, "ms65-main-container-invalid")
        return matches[0]

    def inspect_controls(self, ms64_sha256: str, image_lock_sha256: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        deployments = self._named("deployments")
        services = self._named("services")
        accounts = self._named("serviceaccounts")
        budgets = self._named("poddisruptionbudgets")
        policies = self._named("networkpolicies")
        external = self._named("externalsecrets")
        require(set(SERVICES) <= set(deployments), "ms65-eight-deployments-required")
        require(set(SERVICES) <= set(services), "ms65-eight-services-required")
        require(set(SERVICES) <= set(accounts), "ms65-eight-service-accounts-required")
        require(set(SERVICES) <= set(budgets), "ms65-eight-disruption-budgets-required")
        expected_policies = {
            "default-deny", "cloudbank-bounded-traffic", "chatbot-model-egress",
            "cloudbank-otel-egress", "chatbot-in-cluster-model-egress",
            "cloudbank-acme-http01-ingress",
        }
        require(set(policies) == expected_policies, "ms65-network-policy-set-invalid")
        require({"cloudbank-" + service for service in SERVICES} <= set(external),
                "ms65-external-secrets-required")

        control_rows: dict[str, list[Any]] = {
            "resources": [], "accounts": [], "security": [], "limits": [],
            "probes": [], "rolling": [], "budgets": [], "secrets": [], "configuration": [],
        }
        for service in SERVICES:
            deployment, service_object = deployments[service], services[service]
            spec = deployment.get("spec", {})
            template = spec.get("template", {})
            pod_spec = template.get("spec", {})
            container = self._main_container(deployment, service)
            require(spec.get("replicas") == 2, "ms65-two-replica-deployment-required")
            require(container.get("image") == self.runtime.images[service], "ms65-deployment-image-drift")
            require(service_object.get("spec", {}).get("selector") == {"app.kubernetes.io/name": service},
                    "ms65-service-selector-drift")
            control_rows["resources"].append((service, hashed(deployment["metadata"]["uid"]),
                                               hashed(service_object["metadata"]["uid"])))

            account = accounts[service]
            require(pod_spec.get("serviceAccountName") == service
                    and pod_spec.get("automountServiceAccountToken") is False
                    and account.get("automountServiceAccountToken") is False,
                    "ms65-service-account-control-invalid")
            control_rows["accounts"].append((service, hashed(account["metadata"]["uid"])))

            pod_security, container_security = pod_spec.get("securityContext", {}), container.get("securityContext", {})
            require(pod_security.get("runAsNonRoot") is True
                    and pod_security.get("seccompProfile", {}).get("type") == "RuntimeDefault"
                    and not pod_spec.get("initContainers")
                    and not any(pod_spec.get(name, False) for name in ("hostNetwork", "hostPID", "hostIPC"))
                    and container_security.get("allowPrivilegeEscalation") is False
                    and container_security.get("readOnlyRootFilesystem") is True
                    and container_security.get("privileged", False) is False
                    and container_security.get("capabilities", {}).get("drop") == ["ALL"],
                    "ms65-container-security-invalid")
            control_rows["security"].append(service)

            resources = container.get("resources", {})
            require(all(resources.get(group, {}).get(name) for group in ("requests", "limits")
                        for name in ("cpu", "memory")), "ms65-resource-bounds-invalid")
            control_rows["limits"].append(service)
            require(all(container.get(name, {}).get("httpGet", {}).get("path")
                        for name in ("startupProbe", "livenessProbe", "readinessProbe")),
                    "ms65-health-probes-invalid")
            control_rows["probes"].append(service)
            rolling = spec.get("strategy", {})
            require(rolling.get("type") == "RollingUpdate"
                    and str(rolling.get("rollingUpdate", {}).get("maxUnavailable")) == "0"
                    and str(rolling.get("rollingUpdate", {}).get("maxSurge")) == "1",
                    "ms65-rolling-policy-invalid")
            control_rows["rolling"].append(service)
            budget = budgets[service]
            require(budget.get("spec", {}).get("minAvailable") == 1
                    and budget.get("spec", {}).get("selector", {}).get("matchLabels")
                    == {"app.kubernetes.io/name": service}, "ms65-disruption-budget-invalid")
            control_rows["budgets"].append((service, hashed(budget["metadata"]["uid"])))

            env_from = container.get("envFrom", [])
            secret_names = [row.get("secretRef", {}).get("name") for row in env_from if row.get("secretRef")]
            config_names = [row.get("configMapRef", {}).get("name") for row in env_from if row.get("configMapRef")]
            expected_secret = self.environment["service_secret_names"][service]
            secret_observation = external["cloudbank-" + service]
            secret_spec = secret_observation.get("spec", {})
            data_from = secret_spec.get("dataFrom") or []
            target = secret_spec.get("target", {})
            store = secret_spec.get("secretStoreRef", {})
            secret_ready = any(
                row.get("type") == "Ready" and row.get("status") == "True"
                for row in secret_observation.get("status", {}).get("conditions", [])
            )
            require(config_names == ["cloudbank-runtime"]
                    and secret_names == [expected_secret]
                    and store == {"name": "cloudbank-gcp-secret-manager", "kind": "SecretStore"}
                    and target.get("name") == expected_secret
                    and target.get("creationPolicy") == "Owner"
                    and "template" not in target
                    and not secret_spec.get("data")
                    and len(data_from) == 1
                    and set(data_from[0]) == {"extract"}
                    and data_from[0].get("extract", {}).get("key") == expected_secret
                    and secret_ready,
                    "ms65-external-secret-binding-invalid")
            control_rows["secrets"].append((service, expected_secret,
                                             hashed(secret_observation["metadata"]["uid"])))
            require(template.get("metadata", {}).get("annotations", {}).get(
                    "lightyear.ai/configuration-sha256") == self.environment["content_sha256"],
                    "ms65-configuration-hash-not-projected")
            control_rows["configuration"].append(service)

        part_of = {"matchLabels": {"app.kubernetes.io/part-of": "cloudbank"}}
        default_deny = {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}
        bounded = {
            "podSelector": part_of,
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [{"from": [
                {"podSelector": part_of},
                {"namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": self.environment["ingress_namespace"]}}},
            ]}],
            "egress": [
                {"to": [{"podSelector": part_of}]},
                {"to": [{"namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": "kube-system"}}}],
                 "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
                {"to": [{"ipBlock": {"cidr": self.environment["database_egress_cidr"]}}],
                 "ports": [{"protocol": "TCP", "port": 5432}]},
            ],
        }
        model = {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "chatbot"}},
            "policyTypes": ["Egress"],
            "egress": [{"to": [{"ipBlock": {"cidr": self.environment["model_egress_cidr"]}}],
                        "ports": [{"protocol": "TCP", "port": 443}]}],
        }
        require(policies["default-deny"].get("spec") == default_deny, "ms65-default-deny-invalid")
        require(policies["cloudbank-bounded-traffic"].get("spec") == bounded,
                "ms65-bounded-network-policy-invalid")
        require(policies["chatbot-model-egress"].get("spec") == model,
                "ms65-model-network-policy-invalid")
        otel = {
            "podSelector": part_of,
            "policyTypes": ["Egress"],
            "egress": [{"to": [{
                "namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": "observability"}},
                "podSelector": {"matchLabels": {"app": "otel-collector"}},
            }], "ports": [{"protocol": "TCP", "port": 4317}]}],
        }
        require(policies["cloudbank-otel-egress"].get("spec") == otel,
                "ms65-otel-network-policy-invalid")
        cluster_model = policies["chatbot-in-cluster-model-egress"].get("spec", {})
        try:
            model_namespace = cluster_model["egress"][0]["to"][0]["namespaceSelector"][
                "matchLabels"]["kubernetes.io/metadata.name"]
        except (KeyError, IndexError, TypeError):
            model_namespace = ""
        require(re.fullmatch(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?", str(model_namespace)) is not None
                and model_namespace not in {self.runtime.namespace, "kube-system", "observability"},
                "ms65-model-namespace-invalid")
        expected_cluster_model = {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "chatbot"}},
            "policyTypes": ["Egress"],
            "egress": [{"to": [{
                "namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": model_namespace}},
                "podSelector": {"matchLabels": {"app.kubernetes.io/name": "ollama"}},
            }], "ports": [{"protocol": "TCP", "port": 11434}]}],
        }
        require(cluster_model == expected_cluster_model, "ms65-cluster-model-network-policy-invalid")
        acme = {
            "podSelector": {"matchLabels": {"acme.cert-manager.io/http01-solver": "true"}},
            "policyTypes": ["Ingress"],
            "ingress": [{"from": [{
                "namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": self.environment["ingress_namespace"]}},
                "podSelector": {"matchLabels": {
                    "app.kubernetes.io/name": "ingress-nginx",
                    "app.kubernetes.io/instance": "ingress-nginx",
                    "app.kubernetes.io/component": "controller",
                }},
            }], "ports": [{"protocol": "TCP", "port": 8089}]}],
        }
        require(policies["cloudbank-acme-http01-ingress"].get("spec") == acme,
                "ms65-acme-network-policy-invalid")
        config = self.runtime.get("configmap", "cloudbank-runtime").get("data", {})
        require(config.get("LIGHTYEAR_RELEASE") == RELEASE
                and config.get("LIGHTYEAR_CONFIGURATION_SHA256") == self.environment["content_sha256"],
                "ms65-runtime-configuration-invalid")

        ready = self.runtime.ready()
        rollouts = [{"service": service, "image": self.runtime.images[service],
                     "desired_replicas": 2, "ready_replicas": ready[service]["ready_replicas"]}
                    for service in SERVICES]
        details = {
            "signed_ms64": {"content_sha256": ms64_sha256},
            "image_lock": {"content_sha256": image_lock_sha256, "services": list(SERVICES)},
            "manifest": {"sha256": self.bundle["manifest_sha256"],
                         "placeholder_free": "{{" not in self.manifest and "}}" not in self.manifest},
            "resources": control_rows["resources"], "accounts": control_rows["accounts"],
            "security": control_rows["security"], "limits": control_rows["limits"],
            "probes": control_rows["probes"], "rolling": control_rows["rolling"],
            "budgets": control_rows["budgets"],
            "network": {"policies": {name: hashed(policies[name]["metadata"]["uid"])
                                      for name in sorted(expected_policies)},
                        "model_namespace_sha256": hashed(model_namespace),
                        "default_deny_uid_sha256": hashed(policies["default-deny"]["metadata"]["uid"])},
            "secrets": control_rows["secrets"], "configuration": control_rows["configuration"],
            "rollouts": ready,
        }
        return details, rollouts

    def _canary(self) -> dict[str, Any] | None:
        raw = self.runtime.kubectl("get", "deployment/" + self.canary_name, "--ignore-not-found", "-o", "json")
        return json.loads(raw) if raw.strip() else None

    def _canary_pod(self) -> tuple[dict[str, Any], dict[str, Any]]:
        deployment = self._canary()
        require(deployment is not None
                and deployment["metadata"]["uid"] == self.state.get("canary_uid")
                and deployment.get("status", {}).get("readyReplicas") == 1,
                "ms65-canary-identity-or-readiness-invalid")
        selector = "lightyear.ai/ms65-canary=" + self.canary_label
        replicasets = self.runtime.get("replicasets", selector=selector).get("items", [])
        owned_sets = {row["metadata"]["uid"] for row in replicasets if any(
            reference.get("uid") == deployment["metadata"]["uid"] and reference.get("controller") is True
            for reference in row.get("metadata", {}).get("ownerReferences", [])
        )}
        selected = self.runtime.get("pods", selector=selector).get("items", [])
        owned = [pod for pod in selected if any(
            reference.get("uid") in owned_sets and reference.get("controller") is True
            for reference in pod.get("metadata", {}).get("ownerReferences", [])
        )]
        require(len(selected) == 1 and len(owned) == 1
                and not owned[0]["metadata"].get("deletionTimestamp"), "ms65-canary-pod-invalid")
        status = next((row for row in owned[0].get("status", {}).get("containerStatuses", [])
                       if row.get("name") == CANARY_SERVICE), {})
        expected_digest = self.runtime.images[CANARY_SERVICE].split("@sha256:", 1)[1]
        require(status.get("ready") is True and "running" in status.get("state", {})
                and status.get("imageID", "").endswith("sha256:" + expected_digest),
                "ms65-canary-image-or-readiness-invalid")
        return deployment, owned[0]

    def create_canary(self) -> dict[str, Any]:
        original = self.runtime.deployment(CANARY_SERVICE)
        service = self.runtime.get("service", CANARY_SERVICE)
        require(self._canary() is None, "ms65-canary-name-already-exists")
        self.state.update(service_uid=service["metadata"]["uid"],
                          original_selector=service["spec"]["selector"], canary_absent_before=True)
        self.save("canary-create-intent-saved")
        source_template = original["spec"]["template"]
        labels = copy.deepcopy(source_template.get("metadata", {}).get("labels", {}))
        labels["app.kubernetes.io/name"] = self.canary_name
        labels["lightyear.ai/ms65-canary"] = self.canary_label
        annotations = copy.deepcopy(source_template.get("metadata", {}).get("annotations", {}))
        candidate = {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": self.canary_name, "namespace": self.runtime.namespace,
                         "labels": {"lightyear.ai/ms65-canary": self.canary_label}},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"lightyear.ai/ms65-canary": self.canary_label}},
                     "strategy": {"type": "Recreate"},
                     "template": {"metadata": {"labels": labels, "annotations": annotations},
                                  "spec": copy.deepcopy(source_template["spec"])}}
        }
        created = json.loads(self.runtime.kubectl("create", "-f", "-", "-o", "json", data=json.dumps(candidate)))
        self.state["canary_uid"] = created["metadata"]["uid"]
        self.save("canary-created")
        self.runtime.kubectl("rollout", "status", "deployment/" + self.canary_name,
                             "--timeout=300s", timeout=320)
        _, pod = self._canary_pod()
        self.save("candidate-ready")
        return {"service": CANARY_SERVICE, "deployment_uid_sha256": hashed(self.state["canary_uid"]),
                "pod_uid_sha256": hashed(pod["metadata"]["uid"]),
                "image": self.runtime.images[CANARY_SERVICE], "ready_replicas": 1}

    def _patch_selector(self, before: dict[str, str], after: dict[str, str]) -> None:
        service = self.runtime.get("service", CANARY_SERVICE)
        require(service["metadata"]["uid"] == self.state["service_uid"]
                and service["spec"].get("selector") == before, "ms65-service-selector-or-identity-drift")
        patch = [
            {"op": "test", "path": "/metadata/uid", "value": self.state["service_uid"]},
            {"op": "test", "path": "/metadata/resourceVersion", "value": service["metadata"]["resourceVersion"]},
            {"op": "test", "path": "/spec/selector", "value": before},
            {"op": "replace", "path": "/spec/selector", "value": after},
        ]
        self.runtime.close_forward(CANARY_SERVICE)
        self.runtime.kubectl("patch", "service/" + CANARY_SERVICE, "--type=json", "--patch", json.dumps(patch))

    def _endpoint_uids(self) -> set[str]:
        endpoint = self.runtime.get("endpoints", CANARY_SERVICE)
        return {address.get("targetRef", {}).get("uid")
                for subset in endpoint.get("subsets", []) for address in subset.get("addresses", [])
                if address.get("targetRef", {}).get("uid")}

    def _wait_endpoints(self, expected: set[str], timeout: int = 90) -> None:
        deadline = self.clock() + timeout
        while True:
            if self._endpoint_uids() == expected:
                return
            require(self.clock() < deadline, "ms65-service-endpoint-switch-timeout")
            self.pause(1)

    def switch_to_canary(self) -> dict[str, Any]:
        _, pod = self._canary_pod()
        expected = {pod["metadata"]["uid"]}
        selector = {"lightyear.ai/ms65-canary": self.canary_label}
        self.state["switch_intent"] = True
        self.save("traffic-switch-intent-saved")
        self._patch_selector(self.state["original_selector"], selector)
        self.state["selector_switched"] = True
        self.save("traffic-switch-applied")
        self._wait_endpoints(expected)
        self.save("traffic-switched")
        return {"service": CANARY_SERVICE, "service_uid_sha256": hashed(self.state["service_uid"]),
                "endpoint_pod_uids_sha256": hashed(sorted(expected)), "selector_sha256": hashed(selector)}

    def credit_check(self) -> dict[str, Any]:
        response = self.runtime.request(CANARY_SERVICE, "GET", "/api/v1/creditscore", "credit")
        require(response.status == 200, "ms65-credit-check-failed")
        payload = response.json()
        require(isinstance(payload, dict) and re.fullmatch(r"[0-9]{3}", str(payload.get("Credit Score", "")))
                and 500 <= int(payload["Credit Score"]) <= 899, "ms65-credit-contract-invalid")
        return {"http_status": 200, "score_in_declared_range": True}

    def measure_slo(self, requests: int = MINIMUM_SLO_REQUESTS,
                    duration: int = MINIMUM_SLO_SECONDS) -> dict[str, Any]:
        require(requests >= MINIMUM_SLO_REQUESTS and duration >= MINIMUM_SLO_SECONDS,
                "ms65-slo-limits-cannot-be-reduced")
        began, latencies, errors = self.clock(), [], 0
        completed = 0
        while completed < requests or self.clock() - began < duration:
            request_began = self.clock()
            try:
                self.credit_check()
            except Exception:
                errors += 1
            latencies.append((self.clock() - request_began) * 1000)
            completed += 1
            target = began + (completed * duration / requests)
            if completed <= requests and self.clock() < target:
                self.pause(target - self.clock())
            require(completed <= 10_000, "ms65-slo-request-bound-exceeded")
        elapsed = max(duration, math.ceil(self.clock() - began))
        ordered = sorted(latencies)
        p95 = round(ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)], 3)
        result = {"requests": completed, "errors": errors, "p95_ms": p95, "duration_seconds": elapsed}
        require(errors == 0 and p95 <= 500 and 60 <= elapsed <= 3600, "ms65-slo-window-failed")
        return result

    def rollback(self) -> dict[str, Any]:
        selector = {"lightyear.ai/ms65-canary": self.canary_label}
        original_pods = {row["metadata"]["uid"] for row in self.runtime.pods(CANARY_SERVICE)}
        self.save("rollback-intent-saved")
        self._patch_selector(selector, self.state["original_selector"])
        self.state["selector_switched"] = False
        self.save("rollback-applied")
        self._wait_endpoints(original_pods)
        self.runtime.close_forward(CANARY_SERVICE)
        check = self.credit_check()
        self.save("rollback-exercised")
        return {"service": CANARY_SERVICE, "restored_selector_sha256": hashed(self.state["original_selector"]),
                "restored_endpoint_uids_sha256": hashed(sorted(original_pods)), "business_check": check}

    def cleanup(self) -> dict[str, Any]:
        errors: list[str] = []
        service_restored = False
        canary_preserved: bool | None = None
        try:
            service = self.runtime.get("service", CANARY_SERVICE)
            if self.state.get("service_uid"):
                require(service["metadata"]["uid"] == self.state["service_uid"], "ms65-service-identity-drift")
                current = service.get("spec", {}).get("selector")
                injected = {"lightyear.ai/ms65-canary": self.canary_label}
                original_pods = {row["metadata"]["uid"] for row in self.runtime.pods(CANARY_SERVICE)}
                if current == injected:
                    self._patch_selector(injected, self.state["original_selector"])
                    self.state["selector_switched"] = False
                else:
                    require(current == self.state.get("original_selector"), "ms65-service-selector-drift")
                self._wait_endpoints(original_pods)
            service_restored = True
        except Exception:
            errors.append("service-selector-restoration-failed")
        try:
            candidate = self._canary()
            canary_preserved = candidate is not None
            if candidate is not None:
                labels = candidate.get("metadata", {}).get("labels", {})
                require(self.state.get("canary_absent_before") is True
                        and labels.get("lightyear.ai/ms65-canary") == self.canary_label
                        and (self.state.get("canary_uid") is None
                             or candidate["metadata"]["uid"] == self.state["canary_uid"]),
                        "ms65-canary-cleanup-identity-drift")
                # Keep the canary alive if the Service cannot be proved restored.
                # Deleting it while the selector may still point at the canary
                # would turn a failed cleanup into an avoidable outage.
                require(service_restored, "ms65-canary-preserved-for-service-recovery")
                self.runtime.kubectl("delete", "deployment/" + self.canary_name, "--wait=true", "--timeout=180s",
                                     timeout=200)
                canary_preserved = False
        except Exception:
            errors.append("canary-cleanup-failed")
        for service in list(self.runtime.forwards):
            try:
                self.runtime.close_forward(service)
            except Exception:
                errors.append("port-forward-cleanup-failed")
        self.state["cleanup_complete"] = not errors
        self.state["cleanup_errors"] = sorted(set(errors))
        self.state["canary_preserved"] = canary_preserved
        try:
            self.save("cleanup-complete" if not errors else "cleanup-failed")
        except Exception:
            errors.append("recovery-journal-update-failed")
        return {"status": "restored" if not errors else "failed", "errors": sorted(set(errors)),
                "canary_preserved": canary_preserved}


def build_observation(
    *, ms64_sha256: str, image_lock_sha256: str, environment: dict[str, Any],
    bundle: dict[str, Any], control_details: dict[str, Any], rollouts: list[dict[str, Any]],
    journeys: dict[str, Any], backup_restore: dict[str, str], canary: dict[str, Any],
    traffic: dict[str, Any], business: dict[str, Any], rollback: dict[str, Any],
    slo: dict[str, Any], cutover_states: list[str], key: str, signer: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    require(cutover_states == cutover_contract()["required_state_sequence"],
            "ms65-cutover-state-sequence-invalid")
    evidence = {
        SCENARIO_IDS[0]: control_details["signed_ms64"],
        SCENARIO_IDS[1]: control_details["image_lock"],
        SCENARIO_IDS[2]: control_details["manifest"],
        SCENARIO_IDS[3]: control_details["resources"],
        SCENARIO_IDS[4]: control_details["accounts"],
        SCENARIO_IDS[5]: control_details["security"],
        SCENARIO_IDS[6]: control_details["limits"],
        SCENARIO_IDS[7]: control_details["probes"],
        SCENARIO_IDS[8]: control_details["rolling"],
        SCENARIO_IDS[9]: control_details["budgets"],
        SCENARIO_IDS[10]: control_details["network"]["default_deny_uid_sha256"],
        SCENARIO_IDS[11]: control_details["network"],
        SCENARIO_IDS[12]: control_details["secrets"],
        SCENARIO_IDS[13]: control_details["configuration"],
        SCENARIO_IDS[14]: control_details["rollouts"],
        SCENARIO_IDS[15]: {"backup_evidence_sha256": backup_restore["backup_sha256"]},
        SCENARIO_IDS[16]: backup_restore,
        SCENARIO_IDS[17]: journeys,
        SCENARIO_IDS[18]: canary,
        SCENARIO_IDS[19]: traffic,
        SCENARIO_IDS[20]: business,
        SCENARIO_IDS[21]: rollback,
        SCENARIO_IDS[22]: slo,
        SCENARIO_IDS[23]: {"synthetic_data_only": True, "raw_output_persisted": False,
                           "secret_values_persisted": False, "production_environment": False},
    }
    require(set(evidence) == set(SCENARIO_IDS), "ms65-scenario-evidence-incomplete")
    observation = sign({
        "schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "release": RELEASE,
        "bindings": {"source_ms64_receipt_sha256": ms64_sha256,
                     "image_lock_sha256": image_lock_sha256,
                     "environment_sha256": environment["content_sha256"],
                     "deployment_bundle_sha256": bundle["content_sha256"],
                     "cluster_identity_sha256": environment["cluster_identity_sha256"]},
        "scenarios": [{"id": identifier, "status": "passed", "evidence_sha256": hashed(evidence[identifier])}
                      for identifier in SCENARIO_IDS],
        "service_rollouts": rollouts, "backup_restore": backup_restore,
        "cutover_states": cutover_states, "slo_window": slo,
        "synthetic_data_only": True, "raw_output_persisted": False,
        "secret_values_persisted": False, "production_environment": False,
    }, key, signer)
    details = sign({
        "schema_version": "1.0", "details_type": DETAIL_TYPE, "release": RELEASE,
        "contract_sha256": CONTRACT_SHA256,
        "observation_sha256": observation["content_sha256"],
        "scenario_evidence": evidence, "raw_output_persisted": False,
        "secret_values_persisted": False, "production_environment": False,
    }, key, signer)
    return observation, details
