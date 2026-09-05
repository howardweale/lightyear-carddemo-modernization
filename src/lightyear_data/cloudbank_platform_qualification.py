from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from lightyear_common.io import write_json

from .cloudbank_production_readiness import (
    RECEIPT_TYPE as MS65_RECEIPT_TYPE,
    SERVICES,
    validate_execution_receipt as validate_ms65_receipt,
)
from .cloudbank_whole_application_equivalence import (
    RECEIPT_TYPE as MS66_RECEIPT_TYPE,
    validate_execution_receipt as validate_ms66_receipt,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.67.0"
OUTPUT_ROOT = Path("factory/cloudbank/platform-qualification")
RECEIPT_TYPE = "lightyear-cloudbank-non-production-platform-qualification-execution"
RECEIPT_NAME = "cloudbank-platform-qualification.receipt.json"
FAILURE_NAME = "cloudbank-platform-qualification.failure.json"
PREFLIGHT_NAME = "cloudbank-platform-preflight.observation.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
DNS_NAME = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")

TOOLS = ("kubectl", "helm", "cosign", "trivy", "k6")
MINIMUM_KUBERNETES = (1, 28)
MINIMUM_NODES = 3
MINIMUM_FAILURE_DOMAINS = 2
MINIMUM_CERTIFICATE_DAYS = 30
MINIMUM_LOAD_REQUESTS = 1_000
MINIMUM_LOAD_SECONDS = 300
MINIMUM_LOAD_CONCURRENCY = 10
MAXIMUM_LOAD_ERRORS = 0
MAXIMUM_P95_MS = 500
MAXIMUM_RPO_SECONDS = 60
MAXIMUM_RTO_SECONDS = 600

SCENARIO_IDS = [
    "signed-ms65-deployment-rehearsal-admitted",
    "signed-ms66-whole-application-equivalence-admitted",
    "explicit-non-production-context-selected",
    "live-kubernetes-api-and-cluster-identity-observed",
    "minimum-kubernetes-version-observed",
    "three-node-two-failure-domain-capacity-observed",
    "ms65-deployment-bundle-applied",
    "eight-immutable-image-digests-running",
    "sixteen-service-replicas-ready",
    "trusted-hostname-valid-tls-certificate-observed",
    "tls12-or-newer-and-plaintext-rejection-observed",
    "external-secrets-controller-and-store-ready",
    "eight-service-secrets-synchronized",
    "external-secret-rotation-propagated",
    "all-service-metrics-scraped",
    "all-service-logs-and-traces-correlated",
    "alert-fire-and-recovery-observed",
    "bounded-sustained-load-threshold-passed",
    "eight-image-signatures-and-provenance-verified",
    "eight-image-vulnerability-scans-passed",
    "manifest-and-runtime-policy-scans-passed",
    "default-deny-and-bounded-egress-observed",
    "content-addressed-backup-created-and-verified",
    "exact-restore-within-rpo-rto-observed",
    "node-and-failure-domain-disruption-recovered",
    "zero-unavailable-eight-service-rolling-deployment-observed",
    "canary-cutover-business-journeys-passed",
    "rollback-and-post-rollback-recovery-observed",
]
CONTRACT_SHA256 = hashlib.sha256(";".join(SCENARIO_IDS).encode()).hexdigest()
CUTOVER_STATES = [
    "baseline-ready", "canary-ready", "canary-traffic-observed",
    "target-traffic-100-percent", "business-journeys-passed",
    "rollback-triggered", "previous-release-restored", "post-rollback-recovered",
]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def platform_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-real-non-production-kubernetes-platform",
        "release": RELEASE,
        "services": list(SERVICES),
        "orchestrator": "kubernetes",
        "minimum_kubernetes": "1.28",
        "minimum_nodes": MINIMUM_NODES,
        "minimum_failure_domains": MINIMUM_FAILURE_DOMAINS,
        "required_tools": list(TOOLS),
        "controls": {
            "tls": {"minimum_protocol": "TLSv1.2", "minimum_certificate_days": 30,
                    "trusted_chain": True, "hostname_match": True, "plaintext_rejected": True},
            "external_secrets": {"controller_ready": True, "all_services_synced": True,
                                 "rotation_observed": True, "values_persisted": False},
            "observability": {"metrics_logs_traces_all_services": True,
                              "alert_fire_and_recovery": True},
            "load": {"minimum_requests": MINIMUM_LOAD_REQUESTS,
                     "minimum_duration_seconds": MINIMUM_LOAD_SECONDS,
                     "minimum_concurrency": MINIMUM_LOAD_CONCURRENCY,
                     "maximum_errors": MAXIMUM_LOAD_ERRORS,
                     "maximum_p95_ms": MAXIMUM_P95_MS},
            "security": {"signed_images": True, "provenance": True,
                         "critical_vulnerabilities": 0, "high_vulnerabilities": 0,
                         "runtime_policy_violations": 0, "network_policy_observed": True},
            "in_cluster_model": {"runtime": "ollama", "model": "qwen2.5:0.5b",
                                 "immutable_image": True, "external_egress": False,
                                 "chatbot_only_ingress": True},
            "backup_restore": {"exact_normalized_restore": True,
                               "maximum_rpo_seconds": MAXIMUM_RPO_SECONDS,
                               "maximum_rto_seconds": MAXIMUM_RTO_SECONDS},
            "availability": {"node_disruption": True, "failure_domain_disruption": True,
                             "zero_data_loss": True},
            "rolling_deployment": {"all_services": True, "maximum_unavailable": 0},
            "cutover_rollback": {"canary": True, "target_traffic_percent": 100,
                                 "business_journeys": 18, "rollback_mandatory": True},
        },
        "environment_class": "authorized-real-non-production",
        "production_environment": False,
        "production_ready": False,
    })


def execution_plan() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "plan_type": "lightyear-cloudbank-real-platform-qualification",
        "release": RELEASE,
        "requires": [
            "passing-signed-ms65-rehearsal-receipt",
            "passing-signed-ms66-equivalence-receipt",
            "same-operator-evidence-key",
            "signed-explicit-non-production-platform-profile",
            "operator-authorization-for-mutating-disruption-cutover-and-rollback-drills",
            "site-owned-external-secret-and-observability-integrations",
        ],
        "stages": [
            "preflight-explicit-kubernetes-context-and-toolchain",
            "apply-exact-ms65-deployment-bundle",
            "observe-tls-and-plaintext-rejection",
            "observe-external-secret-sync-and-rotation",
            "observe-metrics-logs-traces-and-alert-recovery",
            "run-bounded-load-and-security-scans",
            "create-verify-and-exactly-restore-backup",
            "exercise-node-and-failure-domain-disruption",
            "exercise-zero-unavailable-rolling-deployment",
            "exercise-canary-cutover-and-mandatory-rollback",
            "sign-minimized-platform-observation",
            "admit-bounded-non-production-platform-receipt",
        ],
        "required_scenarios": SCENARIO_IDS,
        "raw_logs_persisted": False,
        "secret_values_persisted": False,
        "cluster_credentials_persisted": False,
        "production_data": False,
        "production_deployment": False,
        "production_ready": False,
    })


def evidence_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-ms67-platform-evidence",
        "release": RELEASE,
        "observation_type": "lightyear-cloudbank-ms67-platform-observation",
        "required_scenarios": SCENARIO_IDS,
        "evidence_representation": "content-addresses-and-bounded-aggregates-only",
        "forbidden_persistence": [
            "kubeconfig", "cluster-credentials", "secret-values", "private-keys",
            "database-backup-bodies", "raw-logs", "raw-traces", "production-data",
        ],
        "operator_signatures_required": ["platform-profile", "platform-observation", "receipt"],
        "customer_production_authority": False,
    })


def compatibility_ledger() -> dict[str, Any]:
    rows = [
        ("real-non-production-kubernetes", "platform-qualified", "live-api-and-cluster-identity"),
        ("tls", "platform-qualified", "trusted-hostname-protocol-plaintext"),
        ("external-secrets", "platform-qualified", "sync-and-rotation"),
        ("observability", "platform-qualified", "metrics-logs-traces-alerts"),
        ("bounded-load", "platform-qualified", "sustained-zero-error-p95-window"),
        ("supply-chain-security", "platform-qualified", "signatures-provenance-vulnerability-scans"),
        ("backup-restore", "platform-qualified", "exact-state-rpo-rto"),
        ("high-availability", "platform-qualified", "node-and-failure-domain-disruption"),
        ("rolling-deployment", "platform-qualified", "zero-unavailable-all-services"),
        ("cutover-rollback", "platform-qualified", "canary-switch-rollback-recovery"),
        ("customer-idp", "not-qualified", "ms68-customer-integration-required"),
        ("representative-production-volume", "not-qualified", "ms68-customer-workload-required"),
        ("customer-change-approval", "not-qualified", "ms68-approval-required"),
        ("production-deployment", "not-qualified", "customer-change-authority-required"),
        ("production-readiness", "not-qualified", "ms68-certification-required"),
    ]
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-cloudbank-platform-qualification-compatibility",
        "release": RELEASE,
        "entries": [
            {"capability": capability, "classification": classification, "evidence": evidence}
            for capability, classification, evidence in rows
        ],
        "non_production_platform_qualification_eligible": True,
        "migration_complete": False,
        "production_deployment_eligible": False,
        "production_ready": False,
    })


def acceptance_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-platform-qualification-acceptance",
        "release": RELEASE,
        "bindings": {
            "platform_contract_sha256": platform_contract()["content_sha256"],
            "execution_plan_sha256": execution_plan()["content_sha256"],
            "evidence_contract_sha256": evidence_contract()["content_sha256"],
            "compatibility_ledger_sha256": compatibility_ledger()["content_sha256"],
        },
        "required_receipts": [MS65_RECEIPT_TYPE, MS66_RECEIPT_TYPE],
        "required_services": list(SERVICES),
        "required_scenarios": SCENARIO_IDS,
        "required_contract_sha256": CONTRACT_SHA256,
        "eligible_claim": {
            "non_production_platform_qualified": True,
            "tls_qualified": True,
            "external_secrets_qualified": True,
            "observability_qualified": True,
            "performance_qualified": True,
            "security_qualified": True,
            "backup_restore_qualified": True,
            "high_availability_qualified": True,
            "rolling_deployment_qualified": True,
            "cutover_rollback_qualified": True,
            "customer_idp_qualified": False,
            "representative_data_volume_qualified": False,
            "customer_approval_complete": False,
            "migration_complete": False,
            "production_deployed": False,
            "production_ready": False,
        },
    })


def readiness_receipt() -> dict[str, Any]:
    claims = {name: False for name in acceptance_contract()["eligible_claim"]}
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-cloudbank-non-production-platform-qualification-readiness",
        "release": RELEASE,
        "bindings": acceptance_contract()["bindings"],
        "acceptance_contract_sha256": acceptance_contract()["content_sha256"],
        "gate_status": "ready-for-signed-ms65-ms66-and-authorized-real-platform-observation",
        **claims,
    })


def gke_addons_template() -> str:
    lines = [
        "apiVersion: v1", "kind: Namespace", "metadata:", "  name: observability", "---",
        "apiVersion: v1", "kind: ServiceAccount", "metadata:", "  name: otel-collector",
        "  namespace: observability", "automountServiceAccountToken: true", "---",
        "apiVersion: v1", "kind: ConfigMap", "metadata:", "  name: otel-collector",
        "  namespace: observability", "data:", "  config.yaml: |", "    receivers:",
        "      otlp:", "        protocols:", "          grpc:", "            endpoint: 0.0.0.0:4317",
        "          http:", "            endpoint: 0.0.0.0:4318", "    processors:",
        "      batch: {}", "      resourcedetection:", "        detectors: [gcp]", "        timeout: 10s",
        "    exporters:", "      googlecloud:", "        project: \"{{PROJECT_ID}}\"",
        "    extensions:", "      health_check:", "        endpoint: 0.0.0.0:13133",
        "    service:", "      extensions: [health_check]", "      pipelines:",
        "        metrics:", "          receivers: [otlp]", "          processors: [resourcedetection, batch]",
        "          exporters: [googlecloud]", "        traces:", "          receivers: [otlp]",
        "          processors: [resourcedetection, batch]", "          exporters: [googlecloud]", "---",
        "apiVersion: apps/v1", "kind: Deployment", "metadata:", "  name: otel-collector",
        "  namespace: observability", "spec:", "  replicas: 2", "  selector:", "    matchLabels:",
        "      app: otel-collector", "  template:", "    metadata:", "      labels:",
        "        app: otel-collector", "      annotations:",
        "        lightyear.ai/otel-config-sha256: \"{{OTEL_CONFIGURATION_SHA256}}\"",
        "    spec:", "      serviceAccountName: otel-collector",
        "      containers:", "      - name: collector", "        image: \"{{OTEL_COLLECTOR_IMAGE}}\"",
        "        args: [\"--config=/conf/config.yaml\"]", "        ports:",
        "        - {name: otlp-grpc, containerPort: 4317}",
        "        - {name: otlp-http, containerPort: 4318}",
        "        - {name: health, containerPort: 13133}",
        "        startupProbe:", "          httpGet: {path: /, port: health}",
        "          periodSeconds: 5", "          timeoutSeconds: 2", "          failureThreshold: 60",
        "        livenessProbe:", "          httpGet: {path: /, port: health}",
        "          periodSeconds: 10", "          timeoutSeconds: 2",
        "        readinessProbe:", "          httpGet: {path: /, port: health}",
        "          periodSeconds: 5", "          timeoutSeconds: 2",
        "        resources:", "          requests:",
        "            cpu: 100m", "            memory: 256Mi", "          limits:", "            cpu: 500m",
        "            memory: 512Mi", "        securityContext:", "          runAsNonRoot: true",
        "          runAsUser: 10001", "          allowPrivilegeEscalation: false",
        "          readOnlyRootFilesystem: true", "          capabilities:", "            drop: [\"ALL\"]",
        "        volumeMounts:", "        - {name: config, mountPath: /conf, readOnly: true}",
        "        - {name: tmp, mountPath: /tmp}", "      volumes:", "      - name: config", "        configMap:",
        "          name: otel-collector", "      - name: tmp", "        emptyDir: {sizeLimit: 64Mi}",
        "      securityContext:", "        runAsNonRoot: true", "        seccompProfile:",
        "          type: RuntimeDefault", "---",
        "apiVersion: v1", "kind: Service", "metadata:", "  name: otel-collector",
        "  namespace: observability", "spec:", "  selector:", "    app: otel-collector", "  ports:",
        "  - {name: grpc, port: 4317, targetPort: otlp-grpc}",
        "  - {name: http, port: 4318, targetPort: otlp-http}", "---",
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: observability-default-deny", "  namespace: observability", "spec:",
        "  podSelector: {}", "  policyTypes: [\"Ingress\", \"Egress\"]", "---",
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: otel-collector-traffic", "  namespace: observability", "spec:", "  podSelector:",
        "    matchLabels:", "      app: otel-collector", "  policyTypes: [\"Ingress\", \"Egress\"]",
        "  ingress:", "  - from:", "    - namespaceSelector:", "        matchLabels:",
        "          kubernetes.io/metadata.name: \"{{NAMESPACE}}\"", "    ports:",
        "    - {protocol: TCP, port: 4317}", "  egress:", "  - to:", "    - ipBlock:",
        "        cidr: \"{{GOOGLE_APIS_CIDR}}\"", "    ports:", "    - {protocol: TCP, port: 443}", "  - to:",
        "    - ipBlock:", "        cidr: 169.254.169.254/32", "    ports:",
        "    - {protocol: TCP, port: 80}", "    - {protocol: TCP, port: 8080}", "  - to:",
        "    - namespaceSelector:", "        matchLabels:",
        "          kubernetes.io/metadata.name: kube-system", "    ports:",
        "    - {protocol: UDP, port: 53}", "    - {protocol: TCP, port: 53}", "---",
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: cloudbank-otel-egress", "  namespace: \"{{NAMESPACE}}\"", "spec:",
        "  podSelector:", "    matchLabels:", "      app.kubernetes.io/part-of: cloudbank",
        "  policyTypes: [\"Egress\"]", "  egress:", "  - to:", "    - namespaceSelector:",
        "        matchLabels:", "          kubernetes.io/metadata.name: observability", "      podSelector:",
        "        matchLabels:", "          app: otel-collector", "    ports:",
        "    - {protocol: TCP, port: 4317}", "---",
        "apiVersion: external-secrets.io/v1", "kind: SecretStore", "metadata:",
        "  name: cloudbank-gcp-secret-manager", "  namespace: \"{{NAMESPACE}}\"", "spec:",
        "  provider:", "    gcpsm:", "      projectID: \"{{PROJECT_ID}}\"", "      auth:",
        "        workloadIdentity:", "          clusterProjectID: \"{{PROJECT_ID}}\"",
        "          clusterLocation: \"{{REGION}}\"", "          clusterName: \"{{CLUSTER_NAME}}\"",
        "          serviceAccountRef:", "            name: cloudbank-secret-reader", "---",
    ]
    for service in SERVICES:
        lines.extend([
            "apiVersion: external-secrets.io/v1", "kind: ExternalSecret", "metadata:",
            f"  name: cloudbank-{service}", "  namespace: \"{{NAMESPACE}}\"", "spec:",
            "  refreshInterval: 1m", "  secretStoreRef:",
            "    name: cloudbank-gcp-secret-manager", "    kind: SecretStore", "  target:",
            f"    name: cloudbank-{service}-external", "    creationPolicy: Owner", "  dataFrom:",
            "  - extract:", f"      key: cloudbank-{service}-external", "---",
        ])
    lines.extend([
        "apiVersion: v1", "kind: Namespace", "metadata:", "  name: \"{{MODEL_NAMESPACE}}\"",
        "  labels:", "    pod-security.kubernetes.io/enforce: restricted",
        "    pod-security.kubernetes.io/enforce-version: latest",
        "    environment: non-production", "---",
        "apiVersion: v1", "kind: ServiceAccount", "metadata:", "  name: ollama",
        "  namespace: \"{{MODEL_NAMESPACE}}\"", "automountServiceAccountToken: false", "---",
        "apiVersion: apps/v1", "kind: Deployment", "metadata:", "  name: ollama",
        "  namespace: \"{{MODEL_NAMESPACE}}\"", "  labels:", "    app.kubernetes.io/name: ollama",
        "    app.kubernetes.io/part-of: cloudbank-model", "spec:", "  replicas: 2",
        "  strategy:", "    type: RollingUpdate", "    rollingUpdate:", "      maxUnavailable: 0",
        "      maxSurge: 1", "  selector:", "    matchLabels:", "      app.kubernetes.io/name: ollama",
        "  template:", "    metadata:", "      labels:", "        app.kubernetes.io/name: ollama",
        "        app.kubernetes.io/part-of: cloudbank-model", "      annotations:",
        "        lightyear.ai/model-name: \"{{OLLAMA_MODEL_NAME}}\"",
        "        lightyear.ai/model-manifest-sha256: \"{{OLLAMA_MODEL_MANIFEST_SHA256}}\"", "    spec:",
        "      serviceAccountName: ollama", "      automountServiceAccountToken: false",
        "      topologySpreadConstraints:", "      - maxSkew: 1",
        "        topologyKey: topology.kubernetes.io/zone", "        whenUnsatisfiable: DoNotSchedule",
        "        labelSelector:", "          matchLabels:", "            app.kubernetes.io/name: ollama",
        "      securityContext:", "        runAsNonRoot: true", "        runAsUser: 65532",
        "        runAsGroup: 65532", "        fsGroup: 65532", "        seccompProfile:",
        "          type: RuntimeDefault", "      containers:", "      - name: ollama",
        "        image: \"{{OLLAMA_MODEL_IMAGE}}\"", "        imagePullPolicy: IfNotPresent",
        "        env:", "        - {name: HOME, value: /tmp/ollama-home}",
        "        - {name: OLLAMA_HOST, value: 0.0.0.0:11434}",
        "        - {name: OLLAMA_MODELS, value: /models}",
        "        - {name: OLLAMA_NOHISTORY, value: \"1\"}",
        "        - {name: OLLAMA_KEEP_ALIVE, value: \"0\"}",
        "        - {name: OLLAMA_NUM_PARALLEL, value: \"1\"}",
        "        ports:", "        - {name: http, containerPort: 11434}",
        "        startupProbe:", "          httpGet: {path: /api/tags, port: http}",
        "          failureThreshold: 60", "          periodSeconds: 5", "        livenessProbe:",
        "          httpGet: {path: /, port: http}", "          periodSeconds: 15",
        "          timeoutSeconds: 3", "        readinessProbe:",
        "          httpGet: {path: /api/tags, port: http}", "          periodSeconds: 5",
        "          timeoutSeconds: 3", "        resources:", "          requests:",
        "            cpu: 500m", "            memory: 768Mi", "          limits:",
        "            cpu: \"2\"", "            memory: 2Gi", "        securityContext:",
        "          allowPrivilegeEscalation: false", "          readOnlyRootFilesystem: true",
        "          capabilities:", "            drop: [\"ALL\"]", "        volumeMounts:",
        "        - {name: tmp, mountPath: /tmp}", "      volumes:", "      - name: tmp",
        "        emptyDir: {sizeLimit: 128Mi}", "---",
        "apiVersion: v1", "kind: Service", "metadata:", "  name: ollama",
        "  namespace: \"{{MODEL_NAMESPACE}}\"", "spec:", "  selector:",
        "    app.kubernetes.io/name: ollama", "  ports:",
        "  - {name: http, port: 11434, targetPort: http}", "---",
        "apiVersion: policy/v1", "kind: PodDisruptionBudget", "metadata:", "  name: ollama",
        "  namespace: \"{{MODEL_NAMESPACE}}\"", "spec:", "  minAvailable: 1", "  selector:",
        "    matchLabels:", "      app.kubernetes.io/name: ollama", "---",
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: model-default-deny", "  namespace: \"{{MODEL_NAMESPACE}}\"", "spec:",
        "  podSelector: {}", "  policyTypes: [\"Ingress\", \"Egress\"]", "---",
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: chatbot-only-model-ingress", "  namespace: \"{{MODEL_NAMESPACE}}\"", "spec:",
        "  podSelector:", "    matchLabels:", "      app.kubernetes.io/name: ollama",
        "  policyTypes: [\"Ingress\"]", "  ingress:", "  - from:", "    - namespaceSelector:",
        "        matchLabels:", "          kubernetes.io/metadata.name: \"{{NAMESPACE}}\"",
        "      podSelector:", "        matchLabels:", "          app.kubernetes.io/name: chatbot",
        "    ports:", "    - {protocol: TCP, port: 11434}", "---",
        "apiVersion: networking.k8s.io/v1", "kind: NetworkPolicy", "metadata:",
        "  name: chatbot-in-cluster-model-egress", "  namespace: \"{{NAMESPACE}}\"", "spec:",
        "  podSelector:", "    matchLabels:", "      app.kubernetes.io/name: chatbot",
        "  policyTypes: [\"Egress\"]", "  egress:", "  - to:", "    - namespaceSelector:",
        "        matchLabels:", "          kubernetes.io/metadata.name: \"{{MODEL_NAMESPACE}}\"",
        "      podSelector:", "        matchLabels:", "          app.kubernetes.io/name: ollama",
        "    ports:", "    - {protocol: TCP, port: 11434}", "---",
    ])
    lines.extend([
        "apiVersion: cert-manager.io/v1", "kind: ClusterIssuer", "metadata:",
        "  name: cloudbank-ms67-letsencrypt", "spec:", "  acme:",
        "    email: \"{{LETSENCRYPT_EMAIL}}\"", "    server: https://acme-v02.api.letsencrypt.org/directory",
        "    privateKeySecretRef:", "      name: cloudbank-ms67-acme", "    solvers:",
        "    - http01:", "        ingress:", "          ingressClassName: nginx", "---",
        "apiVersion: networking.k8s.io/v1", "kind: Ingress", "metadata:",
        "  name: cloudbank", "  namespace: \"{{NAMESPACE}}\"", "  annotations:",
        "    cert-manager.io/cluster-issuer: cloudbank-ms67-letsencrypt",
        "    nginx.ingress.kubernetes.io/ssl-redirect: \"true\"", "spec:",
        "  ingressClassName: nginx", "  tls:", "  - hosts:", "    - \"{{TLS_HOSTNAME}}\"",
        "    secretName: cloudbank-ms67-tls", "  rules:", "  - host: \"{{TLS_HOSTNAME}}\"",
        "    http:", "      paths:", "      - path: /", "        pathType: Prefix", "        backend:",
        "          service:", "            name: testrunner", "            port:", "              number: 8080",
        "---",
    ])
    return "\n".join(lines) + "\n"


def render_gke_addons(project_id: str, region: str, cluster_name: str, namespace: str,
                      hostname: str, letsencrypt_email: str, otel_collector_image: str,
                      model_namespace: str, ollama_model_image: str, ollama_model_name: str,
                      ollama_model_manifest_sha256: str,
                      google_apis_cidr: str) -> str:
    values = (project_id, region, cluster_name, namespace, hostname, letsencrypt_email,
              otel_collector_image, model_namespace, ollama_model_image, ollama_model_name,
              ollama_model_manifest_sha256, google_apis_cidr)
    if any(not value.strip() or any(character in value for character in "\n\r\"{}") for value in values):
        raise ValueError("cloudbank-platform-qualification-gke-render-input-invalid")
    if not DNS_NAME.fullmatch(hostname) or not DNS_NAME.fullmatch(namespace) \
            or not DNS_NAME.fullmatch(model_namespace) or model_namespace == namespace:
        raise ValueError("cloudbank-platform-qualification-gke-render-dns-invalid")
    if not IMAGE.fullmatch(otel_collector_image) or not IMAGE.fullmatch(ollama_model_image):
        raise ValueError("cloudbank-platform-qualification-gke-render-image-invalid")
    if ollama_model_name != "qwen2.5:0.5b":
        raise ValueError("cloudbank-platform-qualification-gke-render-model-invalid")
    if not HEX_64.fullmatch(ollama_model_manifest_sha256):
        raise ValueError("cloudbank-platform-qualification-gke-render-model-manifest-invalid")
    if google_apis_cidr != "199.36.153.8/30":
        raise ValueError("cloudbank-platform-qualification-gke-render-google-api-cidr-invalid")
    rendered = gke_addons_template()
    for marker, value in {
        "{{PROJECT_ID}}": project_id, "{{REGION}}": region, "{{CLUSTER_NAME}}": cluster_name,
        "{{NAMESPACE}}": namespace, "{{TLS_HOSTNAME}}": hostname,
        "{{LETSENCRYPT_EMAIL}}": letsencrypt_email,
        "{{OTEL_COLLECTOR_IMAGE}}": otel_collector_image,
        "{{MODEL_NAMESPACE}}": model_namespace,
        "{{OLLAMA_MODEL_IMAGE}}": ollama_model_image,
        "{{OLLAMA_MODEL_NAME}}": ollama_model_name,
        "{{OLLAMA_MODEL_MANIFEST_SHA256}}": ollama_model_manifest_sha256,
        "{{GOOGLE_APIS_CIDR}}": google_apis_cidr,
    }.items():
        rendered = rendered.replace(marker, value)
    # Bind the pod template to the rendered collector configuration so a ConfigMap
    # correction starts a new rollout instead of leaving existing processes unchanged.
    collector_config = rendered.split("  config.yaml: |\n", 1)[1].split("---\n", 1)[0]
    rendered = rendered.replace("{{OTEL_CONFIGURATION_SHA256}}",
                                hashlib.sha256(collector_config.encode()).hexdigest())
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("cloudbank-platform-qualification-gke-render-placeholder-invalid")
    return rendered


def build_artifacts() -> dict[str, dict[str, Any]]:
    return {
        "platform-contract.json": platform_contract(),
        "execution-plan.json": execution_plan(),
        "evidence-contract.json": evidence_contract(),
        "compatibility-ledger.json": compatibility_ledger(),
        "acceptance-contract.json": acceptance_contract(),
        "readiness.receipt.json": readiness_receipt(),
    }


def select_gke_telemetry_resources(rendered: str) -> str:
    """Select only the generated observability resources for a bounded collector repair."""
    documents = [document for document in rendered.split("---\n") if (
        "\n  namespace: observability\n" in document
        or document.startswith("apiVersion: v1\nkind: Namespace\nmetadata:\n  name: observability\n")
    )]
    if len(documents) != 7:
        raise ValueError("cloudbank-platform-qualification-telemetry-resource-count-invalid")
    return "---\n".join(documents) + "---\n"


def write_artifacts(project_root: Path) -> None:
    root = project_root / OUTPUT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in build_artifacts().items():
        write_json(root / name, payload)
    template = root / "gke/kubernetes/addons-template.yaml"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(gke_addons_template(), encoding="utf-8")


def validate_artifacts(project_root: Path) -> list[str]:
    errors: list[str] = []
    root = project_root / OUTPUT_ROOT
    for name, expected in build_artifacts().items():
        try:
            actual = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"cloudbank-platform-qualification-artifact-invalid:{name}")
            continue
        if actual != expected:
            errors.append(f"cloudbank-platform-qualification-artifact-drift:{name}")
    if len(SCENARIO_IDS) != 28 or len(set(SCENARIO_IDS)) != 28:
        errors.append("cloudbank-platform-qualification-scenarios-invalid")
    template = root / "gke/kubernetes/addons-template.yaml"
    if not template.is_file() or template.read_text(encoding="utf-8") != gke_addons_template():
        errors.append("cloudbank-platform-qualification-gke-template-drift")
    if any(readiness_receipt().get(name) is not False
           for name in acceptance_contract()["eligible_claim"]):
        errors.append("cloudbank-platform-qualification-readiness-overclaims")
    return sorted(set(errors))


def _valid_signed(payload: Mapping[str, Any], key: str) -> bool:
    return bool(key) and payload.get("content_sha256") == content_hash(dict(payload)) \
        and verify_signature(dict(payload), key)


def validate_profile(profile: Mapping[str, Any], key: str) -> list[str]:
    errors: list[str] = []
    expected = {
        "schema_version", "profile_type", "release", "signer", "context", "cluster_uid_sha256",
        "provider", "region", "namespace", "namespace_uid_sha256", "ingress_url",
        "expected_hostname", "model_mode", "model_namespace", "model_name", "model_image",
        "model_manifest_sha256", "model_external_egress",
        "mutating_drills_authorized", "production_access_authorized",
        "non_production", "content_sha256", "signature",
    }
    if set(profile) != expected:
        errors.append("cloudbank-platform-qualification-profile-fields-invalid")
    if profile.get("profile_type") != "lightyear-cloudbank-ms67-platform-profile" \
            or profile.get("release") != RELEASE:
        errors.append("cloudbank-platform-qualification-profile-identity-invalid")
    if not _valid_signed(profile, key):
        errors.append("cloudbank-platform-qualification-profile-signature-invalid")
    if not str(profile.get("signer", "")).strip() \
            or (profile.get("signature") or {}).get("signer") != profile.get("signer"):
        errors.append("cloudbank-platform-qualification-profile-signer-invalid")
    for name in ("cluster_uid_sha256", "namespace_uid_sha256"):
        if not HEX_64.fullmatch(str(profile.get(name, ""))):
            errors.append(f"cloudbank-platform-qualification-profile-{name}-invalid")
    if not str(profile.get("context", "")).strip() or not str(profile.get("provider", "")).strip() \
            or not str(profile.get("region", "")).strip() or not str(profile.get("namespace", "")).strip():
        errors.append("cloudbank-platform-qualification-profile-location-invalid")
    url, hostname = str(profile.get("ingress_url", "")), str(profile.get("expected_hostname", ""))
    if url != f"https://{hostname}" or not DNS_NAME.fullmatch(hostname):
        errors.append("cloudbank-platform-qualification-profile-ingress-invalid")
    if profile.get("model_mode") != "in-cluster-ollama" \
            or profile.get("model_name") != "qwen2.5:0.5b" \
            or profile.get("model_external_egress") is not False \
            or not DNS_NAME.fullmatch(str(profile.get("model_namespace", ""))) \
            or profile.get("model_namespace") == profile.get("namespace") \
            or not IMAGE.fullmatch(str(profile.get("model_image", ""))) \
            or not HEX_64.fullmatch(str(profile.get("model_manifest_sha256", ""))):
        errors.append("cloudbank-platform-qualification-profile-model-invalid")
    if profile.get("mutating_drills_authorized") is not True \
            or profile.get("production_access_authorized") is not False \
            or profile.get("non_production") is not True:
        errors.append("cloudbank-platform-qualification-profile-authorization-invalid")
    return sorted(set(errors))


def preflight_platform(
    profile: Mapping[str, Any], key: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    errors = validate_profile(profile, key)
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    if errors or missing:
        raise ValueError(";".join(errors + [f"cloudbank-platform-tool-missing:{item}" for item in missing]))
    context, namespace = str(profile["context"]), str(profile["namespace"])
    commands = [
        ["kubectl", "--context", context, "version", "-o", "json"],
        ["kubectl", "--context", context, "get", "namespace", namespace, "-o", "json"],
        ["kubectl", "--context", context, "get", "nodes", "-o", "json"],
        ["kubectl", "--context", context, "auth", "can-i", "get", "pods", "-n", namespace],
        ["kubectl", "--context", context, "auth", "can-i", "patch", "deployments", "-n", namespace],
        ["kubectl", "--context", context, "auth", "can-i", "delete", "pods", "-n", namespace],
    ]
    results = []
    for argv in commands:
        result = runner(argv, capture_output=True, text=True, timeout=30, check=False)
        results.append({
            "argv_sha256": _sha256_bytes("\0".join(argv).encode()),
            "exit_code": result.returncode,
            "stdout_sha256": _sha256_bytes(result.stdout.encode()),
            "stderr_sha256": _sha256_bytes(result.stderr.encode()),
        })
    if any(item["exit_code"] != 0 for item in results):
        raise ValueError("cloudbank-platform-preflight-command-failed")
    return seal({
        "schema_version": "1.0",
        "observation_type": "lightyear-cloudbank-ms67-read-only-preflight",
        "release": RELEASE,
        "profile_sha256": profile["content_sha256"],
        "cluster_uid_sha256": profile["cluster_uid_sha256"],
        "namespace_uid_sha256": profile["namespace_uid_sha256"],
        "tools": list(TOOLS),
        "commands": results,
        "raw_output_persisted": False,
        "credentials_persisted": False,
        "mutations_performed": False,
    })


def _version_at_least(value: object) -> bool:
    match = re.match(r"^v?(\d+)\.(\d+)(?:\.\d+)?", str(value))
    return bool(match) and tuple(map(int, match.groups())) >= MINIMUM_KUBERNETES


def _exact_services(value: object) -> bool:
    return isinstance(value, list) and value == list(SERVICES)


def _validate_observation_structure(observation: Mapping[str, Any]) -> bool:
    expected = {
        "schema_version", "observation_type", "release", "signer", "bindings", "cluster",
        "scenarios", "service_rollouts", "tls", "external_secrets", "observability", "load",
        "security", "backup_restore", "resilience", "rolling_deployments", "cutover_rollback",
        "safety", "content_sha256", "signature",
    }
    return set(observation) == expected


def validate_observation(
    observation: Mapping[str, Any], key: str, *, ms65: Mapping[str, Any],
    ms66: Mapping[str, Any], profile: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if not _validate_observation_structure(observation):
        errors.append("cloudbank-platform-qualification-observation-fields-invalid")
    if observation.get("observation_type") != "lightyear-cloudbank-ms67-platform-observation" \
            or observation.get("release") != RELEASE:
        errors.append("cloudbank-platform-qualification-observation-identity-invalid")
    if not _valid_signed(observation, key):
        errors.append("cloudbank-platform-qualification-observation-signature-invalid")
    if not str(observation.get("signer", "")).strip() \
            or (observation.get("signature") or {}).get("signer") != observation.get("signer"):
        errors.append("cloudbank-platform-qualification-observation-signer-invalid")
    expected_bindings = {
        "source_ms65_receipt_sha256": ms65.get("content_sha256"),
        "source_ms66_receipt_sha256": ms66.get("content_sha256"),
        "profile_sha256": profile.get("content_sha256"),
        "deployment_bundle_sha256": ms65.get("deployment_bundle_sha256"),
        "cluster_identity_sha256": ms65.get("cluster_identity_sha256"),
        "platform_contract_sha256": platform_contract()["content_sha256"],
        "evidence_contract_sha256": evidence_contract()["content_sha256"],
    }
    if observation.get("bindings") != expected_bindings:
        errors.append("cloudbank-platform-qualification-observation-binding-invalid")
    cluster = observation.get("cluster") or {}
    if not isinstance(cluster, Mapping) or set(cluster) != {
        "context", "cluster_uid_sha256", "namespace", "namespace_uid_sha256", "provider",
        "region", "kubernetes_version", "node_count", "failure_domains",
    } or cluster.get("context") != profile.get("context") \
            or cluster.get("cluster_uid_sha256") != profile.get("cluster_uid_sha256") \
            or cluster.get("namespace") != profile.get("namespace") \
            or cluster.get("namespace_uid_sha256") != profile.get("namespace_uid_sha256") \
            or cluster.get("provider") != profile.get("provider") \
            or cluster.get("region") != profile.get("region") \
            or not _version_at_least(cluster.get("kubernetes_version")) \
            or not isinstance(cluster.get("node_count"), int) \
            or cluster.get("node_count", 0) < MINIMUM_NODES \
            or not isinstance(cluster.get("failure_domains"), list) \
            or len(set(cluster.get("failure_domains", []))) < MINIMUM_FAILURE_DOMAINS:
        errors.append("cloudbank-platform-qualification-observation-cluster-invalid")
    scenarios = observation.get("scenarios") or []
    if not isinstance(scenarios, list) or [item.get("id") for item in scenarios if isinstance(item, Mapping)] != SCENARIO_IDS \
            or len(scenarios) != len(SCENARIO_IDS) or any(
                not isinstance(item, Mapping) or set(item) != {"id", "status", "evidence_sha256"}
                or item.get("status") != "passed"
                or not HEX_64.fullmatch(str(item.get("evidence_sha256", "")))
                for item in scenarios
            ):
        errors.append("cloudbank-platform-qualification-observation-scenarios-invalid")
    expected_images = {
        row.get("service"): row.get("image") for row in (ms65.get("rehearsal") or {}).get("service_rollouts", [])
        if isinstance(row, Mapping)
    }
    rollouts = observation.get("service_rollouts") or []
    if not isinstance(rollouts, list) or [row.get("service") for row in rollouts if isinstance(row, Mapping)] != list(SERVICES) \
            or len(rollouts) != len(SERVICES) or any(
                not isinstance(row, Mapping)
                or set(row) != {"service", "image", "desired_replicas", "ready_replicas", "available_during_drills"}
                or row.get("image") != expected_images.get(row.get("service"))
                or not IMAGE.fullmatch(str(row.get("image", "")))
                or row.get("desired_replicas") != 2 or row.get("ready_replicas") != 2
                or row.get("available_during_drills") is not True for row in rollouts
            ):
        errors.append("cloudbank-platform-qualification-observation-rollouts-invalid")
    tls = observation.get("tls") or {}
    if not isinstance(tls, Mapping) or set(tls) != {
        "hostname", "trusted_chain", "san_match", "minimum_protocol",
        "certificate_days_remaining", "plaintext_rejected",
    } or tls.get("hostname") != profile.get("expected_hostname") \
            or tls.get("trusted_chain") is not True or tls.get("san_match") is not True \
            or tls.get("minimum_protocol") not in {"TLSv1.2", "TLSv1.3"} \
            or not isinstance(tls.get("certificate_days_remaining"), int) \
            or tls.get("certificate_days_remaining", 0) < MINIMUM_CERTIFICATE_DAYS \
            or tls.get("plaintext_rejected") is not True:
        errors.append("cloudbank-platform-qualification-observation-tls-invalid")
    secrets = observation.get("external_secrets") or {}
    if not isinstance(secrets, Mapping) or set(secrets) != {
        "controller_ready", "store_reference_sha256", "synced_services",
        "rotation_observed", "secret_values_persisted",
    } or secrets.get("controller_ready") is not True \
            or not HEX_64.fullmatch(str(secrets.get("store_reference_sha256", ""))) \
            or not _exact_services(secrets.get("synced_services")) \
            or secrets.get("rotation_observed") is not True \
            or secrets.get("secret_values_persisted") is not False:
        errors.append("cloudbank-platform-qualification-observation-secrets-invalid")
    telemetry = observation.get("observability") or {}
    if not isinstance(telemetry, Mapping) or set(telemetry) != {
        "metrics_services", "log_services", "trace_services", "correlation_id_sha256",
        "alert_fired", "alert_recovered",
    } or not _exact_services(telemetry.get("metrics_services")) \
            or not _exact_services(telemetry.get("log_services")) \
            or not _exact_services(telemetry.get("trace_services")) \
            or not HEX_64.fullmatch(str(telemetry.get("correlation_id_sha256", ""))) \
            or telemetry.get("alert_fired") is not True or telemetry.get("alert_recovered") is not True:
        errors.append("cloudbank-platform-qualification-observation-observability-invalid")
    load = observation.get("load") or {}
    if not isinstance(load, Mapping) or set(load) != {
        "tool", "requests", "duration_seconds", "concurrency", "errors", "p95_ms", "requests_per_second",
    } or load.get("tool") != "k6" or not isinstance(load.get("requests"), int) \
            or load.get("requests", 0) < MINIMUM_LOAD_REQUESTS \
            or not isinstance(load.get("duration_seconds"), int) \
            or load.get("duration_seconds", 0) < MINIMUM_LOAD_SECONDS \
            or not isinstance(load.get("concurrency"), int) \
            or load.get("concurrency", 0) < MINIMUM_LOAD_CONCURRENCY \
            or load.get("errors") != MAXIMUM_LOAD_ERRORS \
            or not isinstance(load.get("p95_ms"), (int, float)) or load.get("p95_ms", 501) > MAXIMUM_P95_MS \
            or not isinstance(load.get("requests_per_second"), (int, float)) \
            or load.get("requests_per_second", 0) <= 0:
        errors.append("cloudbank-platform-qualification-observation-load-invalid")
    errors.extend(_validate_security(observation.get("security"), expected_images))
    errors.extend(_validate_recovery(observation))
    safety = observation.get("safety") or {}
    if safety != {
        "non_production": True, "synthetic_data_only": True, "production_accessed": False,
        "raw_logs_persisted": False, "raw_traces_persisted": False,
        "secret_values_persisted": False, "cluster_credentials_persisted": False,
        "backup_bodies_persisted": False,
    }:
        errors.append("cloudbank-platform-qualification-observation-safety-invalid")
    return sorted(set(errors))


def _validate_security(value: object, expected_images: Mapping[object, object]) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != {
        "image_scans", "signed_services", "provenance_services", "manifest_scan",
        "runtime_policy_violations", "network_policy_tests_passed",
    }:
        return ["cloudbank-platform-qualification-observation-security-invalid"]
    scans = value.get("image_scans") or []
    valid = isinstance(scans, list) and len(scans) == len(SERVICES) \
        and [row.get("service") for row in scans if isinstance(row, Mapping)] == list(SERVICES) \
        and all(isinstance(row, Mapping) and set(row) == {"service", "image", "critical", "high", "scan_sha256"}
                and row.get("image") == expected_images.get(row.get("service"))
                and IMAGE.fullmatch(str(row.get("image", ""))) and row.get("critical") == 0
                and row.get("high") == 0 and HEX_64.fullmatch(str(row.get("scan_sha256", "")))
                for row in scans)
    manifest = value.get("manifest_scan") or {}
    valid = valid and _exact_services(value.get("signed_services")) \
        and _exact_services(value.get("provenance_services")) \
        and isinstance(manifest, Mapping) and manifest == {"critical": 0, "high": 0} \
        and value.get("runtime_policy_violations") == 0 \
        and value.get("network_policy_tests_passed") is True
    return [] if valid else ["cloudbank-platform-qualification-observation-security-invalid"]


def _validate_recovery(observation: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    backup = observation.get("backup_restore") or {}
    if not isinstance(backup, Mapping) or set(backup) != {
        "pre_state_sha256", "backup_sha256", "restored_state_sha256", "rpo_seconds",
        "rto_seconds", "point_in_time_restore",
    } or any(not HEX_64.fullmatch(str(backup.get(name, "")))
             for name in ("pre_state_sha256", "backup_sha256", "restored_state_sha256")) \
            or backup.get("pre_state_sha256") != backup.get("restored_state_sha256") \
            or not isinstance(backup.get("rpo_seconds"), int) \
            or backup.get("rpo_seconds", 61) > MAXIMUM_RPO_SECONDS \
            or not isinstance(backup.get("rto_seconds"), int) \
            or backup.get("rto_seconds", 601) > MAXIMUM_RTO_SECONDS \
            or backup.get("point_in_time_restore") is not True:
        errors.append("cloudbank-platform-qualification-observation-backup-invalid")
    resilience = observation.get("resilience") or {}
    if not isinstance(resilience, Mapping) or resilience != {
        "node_disruption_observed": True, "failure_domain_disruption_observed": True,
        "all_services_recovered": True, "data_loss_observed": False,
    }:
        errors.append("cloudbank-platform-qualification-observation-resilience-invalid")
    rolling = observation.get("rolling_deployments") or []
    if not isinstance(rolling, list) or len(rolling) != len(SERVICES) \
            or [row.get("service") for row in rolling if isinstance(row, Mapping)] != list(SERVICES) \
            or any(not isinstance(row, Mapping) or set(row) != {
                "service", "previous_image", "candidate_image", "maximum_unavailable", "completed",
            } or not IMAGE.fullmatch(str(row.get("previous_image", "")))
                or not IMAGE.fullmatch(str(row.get("candidate_image", "")))
                or row.get("previous_image") == row.get("candidate_image")
                or row.get("maximum_unavailable") != 0 or row.get("completed") is not True
                for row in rolling):
        errors.append("cloudbank-platform-qualification-observation-rolling-invalid")
    cutover = observation.get("cutover_rollback") or {}
    if not isinstance(cutover, Mapping) or set(cutover) != {
        "states", "canary_percent", "target_traffic_percent", "business_journey_count",
        "rollback_exercised", "all_services_recovered", "pre_state_sha256", "post_rollback_state_sha256",
    } or cutover.get("states") != CUTOVER_STATES \
            or not isinstance(cutover.get("canary_percent"), int) \
            or not 1 <= cutover.get("canary_percent", 0) < 100 \
            or cutover.get("target_traffic_percent") != 100 \
            or cutover.get("business_journey_count") != 18 \
            or cutover.get("rollback_exercised") is not True \
            or cutover.get("all_services_recovered") is not True \
            or not HEX_64.fullmatch(str(cutover.get("pre_state_sha256", ""))) \
            or cutover.get("pre_state_sha256") != cutover.get("post_rollback_state_sha256"):
        errors.append("cloudbank-platform-qualification-observation-cutover-invalid")
    return errors


QUALIFIED_CLAIMS = {
    "non_production_platform_qualified": True,
    "tls_qualified": True,
    "external_secrets_qualified": True,
    "observability_qualified": True,
    "performance_qualified": True,
    "security_qualified": True,
    "backup_restore_qualified": True,
    "high_availability_qualified": True,
    "rolling_deployment_qualified": True,
    "cutover_rollback_qualified": True,
    "customer_idp_qualified": False,
    "representative_data_volume_qualified": False,
    "customer_approval_complete": False,
    "migration_complete": False,
    "production_deployed": False,
    "production_ready": False,
}


def execute_qualification(
    project_root: Path, ms65: Mapping[str, Any], ms66: Mapping[str, Any],
    profile: Mapping[str, Any], observation: Mapping[str, Any], output_root: Path,
    key: str, signer: str, run_id: str | None = None,
) -> dict[str, Any]:
    if not key:
        raise ValueError("cloudbank-platform-qualification-evidence-key-required")
    if not signer.strip():
        raise ValueError("cloudbank-platform-qualification-signer-required")
    errors = validate_artifacts(project_root)
    errors += validate_ms65_receipt(dict(ms65), key, project_root)
    errors += validate_ms66_receipt(ms66, key, project_root)
    errors += validate_profile(profile, key)
    if ms65.get("receipt_type") != MS65_RECEIPT_TYPE or ms66.get("receipt_type") != MS66_RECEIPT_TYPE:
        errors.append("cloudbank-platform-qualification-prior-receipts-required")
    if ms65.get("source_ms64_receipt_sha256") != ms66.get("source_ms64_receipt_sha256"):
        errors.append("cloudbank-platform-qualification-ms64-chain-invalid")
    if ms65.get("cluster_identity_sha256") != profile.get("cluster_uid_sha256"):
        errors.append("cloudbank-platform-qualification-cluster-chain-invalid")
    if errors:
        raise ValueError(";".join(sorted(set(errors))))
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("cloudbank-platform-qualification-fresh-output-required")
    output_root.mkdir(parents=True, exist_ok=True)
    observation_errors = validate_observation(observation, key, ms65=ms65, ms66=ms66, profile=profile)
    if observation_errors:
        write_json(output_root / FAILURE_NAME, {
            "schema_version": "1.0", "status": "failed-real-non-production-platform-qualification",
            "reason_codes": observation_errors, "raw_output_persisted": False,
            "secret_values_persisted": False, "cluster_credentials_persisted": False,
        })
        raise ValueError("cloudbank-platform-qualification-acceptance-failed")
    receipt = sign({
        "schema_version": "1.0", "receipt_type": RECEIPT_TYPE, "release": RELEASE,
        "run_id": run_id or f"cloudbank-platform-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        "signer": signer, "bindings": readiness_receipt()["bindings"],
        "source_ms65_receipt_sha256": ms65["content_sha256"],
        "source_ms66_receipt_sha256": ms66["content_sha256"],
        "profile_sha256": profile["content_sha256"],
        "observation_sha256": observation["content_sha256"],
        "deployment_bundle_sha256": ms65["deployment_bundle_sha256"],
        "cluster_identity_sha256": profile["cluster_uid_sha256"],
        "namespace_uid_sha256": profile["namespace_uid_sha256"],
        "status": "passed-real-non-production-platform-qualification",
        "services": list(SERVICES), "scenario_count": len(SCENARIO_IDS),
        "platform_summary": {
            "provider": profile["provider"], "region": profile["region"],
            "kubernetes_version": observation["cluster"]["kubernetes_version"],
            "node_count": observation["cluster"]["node_count"],
            "failure_domain_count": len(set(observation["cluster"]["failure_domains"])),
            "load_requests": observation["load"]["requests"],
            "load_p95_ms": observation["load"]["p95_ms"],
            "rpo_seconds": observation["backup_restore"]["rpo_seconds"],
            "rto_seconds": observation["backup_restore"]["rto_seconds"],
        },
        **QUALIFIED_CLAIMS,
        "security": {
            "non_production": True, "synthetic_data_only": True, "production_accessed": False,
            "raw_output_persisted": False, "secret_values_persisted": False,
            "cluster_credentials_persisted": False, "backup_bodies_persisted": False,
        },
    }, key, signer)
    write_json(output_root / RECEIPT_NAME, receipt)
    return receipt


def validate_execution_receipt(receipt: Mapping[str, Any], key: str, project_root: Path) -> list[str]:
    errors: list[str] = []
    expected = {
        "schema_version", "receipt_type", "release", "run_id", "signer", "bindings",
        "source_ms65_receipt_sha256", "source_ms66_receipt_sha256", "profile_sha256",
        "observation_sha256", "deployment_bundle_sha256", "cluster_identity_sha256",
        "namespace_uid_sha256", "status", "services", "scenario_count", "platform_summary",
        *QUALIFIED_CLAIMS, "security", "content_sha256", "signature",
    }
    if set(receipt) != expected:
        errors.append("cloudbank-platform-qualification-receipt-fields-invalid")
    if receipt.get("receipt_type") != RECEIPT_TYPE or receipt.get("release") != RELEASE \
            or receipt.get("status") != "passed-real-non-production-platform-qualification":
        errors.append("cloudbank-platform-qualification-receipt-identity-invalid")
    if not _valid_signed(receipt, key):
        errors.append("cloudbank-platform-qualification-receipt-signature-invalid")
    if not str(receipt.get("run_id", "")).strip() or not str(receipt.get("signer", "")).strip() \
            or (receipt.get("signature") or {}).get("signer") != receipt.get("signer"):
        errors.append("cloudbank-platform-qualification-receipt-provenance-invalid")
    if receipt.get("bindings") != readiness_receipt()["bindings"]:
        errors.append("cloudbank-platform-qualification-receipt-binding-invalid")
    for name in (
        "source_ms65_receipt_sha256", "source_ms66_receipt_sha256", "profile_sha256",
        "observation_sha256", "deployment_bundle_sha256", "cluster_identity_sha256",
        "namespace_uid_sha256",
    ):
        if not HEX_64.fullmatch(str(receipt.get(name, ""))):
            errors.append(f"cloudbank-platform-qualification-receipt-{name}-invalid")
    if receipt.get("services") != list(SERVICES) or receipt.get("scenario_count") != len(SCENARIO_IDS):
        errors.append("cloudbank-platform-qualification-receipt-coverage-invalid")
    if any(receipt.get(name) is not value for name, value in QUALIFIED_CLAIMS.items()):
        errors.append("cloudbank-platform-qualification-receipt-claims-invalid")
    summary = receipt.get("platform_summary") or {}
    numeric_summary_valid = isinstance(summary, Mapping) \
        and isinstance(summary.get("node_count"), int) \
        and isinstance(summary.get("failure_domain_count"), int) \
        and isinstance(summary.get("load_requests"), int) \
        and isinstance(summary.get("load_p95_ms"), (int, float)) \
        and isinstance(summary.get("rpo_seconds"), int) \
        and isinstance(summary.get("rto_seconds"), int)
    if not isinstance(summary, Mapping) or set(summary) != {
        "provider", "region", "kubernetes_version", "node_count", "failure_domain_count",
        "load_requests", "load_p95_ms", "rpo_seconds", "rto_seconds",
    } or not numeric_summary_valid or not _version_at_least(summary.get("kubernetes_version")) \
            or summary.get("node_count", 0) < MINIMUM_NODES \
            or summary.get("failure_domain_count", 0) < MINIMUM_FAILURE_DOMAINS \
            or summary.get("load_requests", 0) < MINIMUM_LOAD_REQUESTS \
            or summary.get("load_p95_ms", 501) > MAXIMUM_P95_MS \
            or summary.get("rpo_seconds", 61) > MAXIMUM_RPO_SECONDS \
            or summary.get("rto_seconds", 601) > MAXIMUM_RTO_SECONDS:
        errors.append("cloudbank-platform-qualification-receipt-summary-invalid")
    if receipt.get("security") != {
        "non_production": True, "synthetic_data_only": True, "production_accessed": False,
        "raw_output_persisted": False, "secret_values_persisted": False,
        "cluster_credentials_persisted": False, "backup_bodies_persisted": False,
    }:
        errors.append("cloudbank-platform-qualification-receipt-security-invalid")
    if validate_artifacts(project_root):
        errors.append("cloudbank-platform-qualification-repository-artifacts-invalid")
    return sorted(set(errors))
