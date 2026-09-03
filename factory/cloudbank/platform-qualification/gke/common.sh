#!/usr/bin/env bash
set -euo pipefail

ms67_gke_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ms67_project_root="$(cd "$ms67_gke_dir/../../../.." && pwd)"

ms67_require_tools() {
  local missing=0
  for tool in "$@"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "Required tool is missing: $tool" >&2
      missing=1
    fi
  done
  [[ $missing -eq 0 ]]
}

ms67_require_environment() {
  local name
  for name in GCP_PROJECT_ID GCP_REGION GKE_CLUSTER_NAME GKE_NAMESPACE GCP_NETWORK_NAME \
    GCP_SUBNET_NAME ARTIFACT_REPOSITORY CLOUD_SQL_INSTANCE DNS_ZONE_NAME \
    DELEGATED_DNS_NAME TLS_HOSTNAME MODEL_EGRESS_CIDR GOOGLE_APIS_CIDR LETSENCRYPT_EMAIL \
    MODEL_NAMESPACE OLLAMA_MODEL_IMAGE OLLAMA_MODEL_NAME OLLAMA_MODEL_MANIFEST_SHA256 \
    EXTERNAL_SECRETS_CHART_VERSION CERT_MANAGER_CHART_VERSION INGRESS_NGINX_CHART_VERSION \
    OTEL_COLLECTOR_IMAGE; do
    [[ -n "${!name:-}" ]] || { echo "Required environment variable is missing: $name" >&2; exit 2; }
  done
  [[ "$GKE_NAMESPACE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
    echo "GKE_NAMESPACE is not a DNS label" >&2; exit 2;
  }
  [[ "$TLS_HOSTNAME" == *".$DELEGATED_DNS_NAME" ]] || {
    echo "TLS_HOSTNAME must be below DELEGATED_DNS_NAME" >&2; exit 2;
  }
  [[ "$MODEL_EGRESS_CIDR" != "0.0.0.0/0" && "$MODEL_EGRESS_CIDR" != "::/0" ]] || {
    echo "MODEL_EGRESS_CIDR must be bounded" >&2; exit 2;
  }
  [[ "$MODEL_EGRESS_CIDR" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/32$ ]] || {
    echo "MODEL_EGRESS_CIDR must be one explicit IPv4 /32" >&2; exit 2;
  }
  [[ "$MODEL_EGRESS_CIDR" == "192.0.2.1/32" ]] || {
    echo "MS67 in-cluster mode requires the unroutable MS65 compatibility value 192.0.2.1/32" >&2; exit 2;
  }
  [[ "$MODEL_NAMESPACE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && "$MODEL_NAMESPACE" != "$GKE_NAMESPACE" ]] || {
    echo "MODEL_NAMESPACE must be a separate DNS-label namespace" >&2; exit 2;
  }
  [[ "$OLLAMA_MODEL_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || {
    echo "OLLAMA_MODEL_IMAGE must use an immutable sha256 digest" >&2; exit 2;
  }
  [[ "$OLLAMA_MODEL_NAME" == "qwen2.5:0.5b" ]] || {
    echo "OLLAMA_MODEL_NAME must be the qualified qwen2.5:0.5b model" >&2; exit 2;
  }
  [[ "$OLLAMA_MODEL_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "OLLAMA_MODEL_MANIFEST_SHA256 must be a verified sha256" >&2; exit 2;
  }
  [[ "$GOOGLE_APIS_CIDR" == "199.36.153.8/30" ]] || {
    echo "GOOGLE_APIS_CIDR must use Google's restricted API VIP 199.36.153.8/30" >&2; exit 2;
  }
  for version in "$EXTERNAL_SECRETS_CHART_VERSION" "$CERT_MANAGER_CHART_VERSION" "$INGRESS_NGINX_CHART_VERSION"; do
    [[ "$version" != replace-* && "$version" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
      echo "Every Helm chart version must be an approved exact semantic version" >&2; exit 2;
    }
  done
  [[ "$OTEL_JAVA_AGENT_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "OTEL_JAVA_AGENT_SHA256 must be a verified sha256" >&2; exit 2;
  }
  [[ "$OTEL_COLLECTOR_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || {
    echo "OTEL_COLLECTOR_IMAGE must use an immutable sha256 digest" >&2; exit 2;
  }
}

ms67_require_mutation_ack() {
  [[ "${LIGHTYEAR_NON_PRODUCTION_ACK:-}" == "I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS" ]] || {
    echo "Set LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS" >&2
    exit 2
  }
}

ms67_require_non_production_project() {
  local labels
  labels="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(labels.environment)' 2>/dev/null || true)"
  [[ "$labels" =~ ^(non-production|nonprod|test|sandbox)$ ]] || {
    echo "Project must carry label environment=non-production, nonprod, test, or sandbox" >&2
    exit 2
  }
}

ms67_services=(azn-server customer account transfer checks testrunner creditscore chatbot)
