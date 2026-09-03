#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud kubectl jq python sha256sum
ms67_require_environment
ms67_require_non_production_project
gcloud config set project "$GCP_PROJECT_ID" >/dev/null
[[ $# -eq 2 ]] || { echo "Usage: render-site-inputs.sh OUTPUT_ROOT SIGNER" >&2; exit 2; }
[[ -n "${LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY:-}" ]] || {
  echo "LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY is required" >&2; exit 2;
}
output_root="$1"
signer="$2"
[[ -n "$signer" ]] || { echo "SIGNER is required" >&2; exit 2; }
mkdir -p "$output_root"
[[ -z "$(find "$output_root" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
  echo "OUTPUT_ROOT must be fresh" >&2; exit 2;
}

cluster_json="$(gcloud container clusters describe "$GKE_CLUSTER_NAME" --region "$GCP_REGION" \
  --format='json(name,location,selfLink,endpoint,currentMasterVersion)')"
cluster_identity="$(printf '%s' "$cluster_json" | sha256sum | cut -d' ' -f1)"
kube_context="gke_${GCP_PROJECT_ID}_${GCP_REGION}_${GKE_CLUSTER_NAME}"
namespace_uid="$(kubectl --context "$kube_context" get namespace "$GKE_NAMESPACE" -o jsonpath='{.metadata.uid}')"
namespace_identity="$(printf '%s' "$namespace_uid" | sha256sum | cut -d' ' -f1)"
database_ip="$(gcloud sql instances describe "$CLOUD_SQL_INSTANCE" \
  --format='value(ipAddresses.filter(type=PRIVATE).firstof(ipAddress))')"
[[ "$database_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "Cloud SQL private address was not found" >&2; exit 2;
}

CLUSTER_IDENTITY="$cluster_identity" NAMESPACE_IDENTITY="$namespace_identity" \
DATABASE_CIDR="$database_ip/32" OUTPUT_ROOT="$output_root" SIGNER="$signer" \
GCP_PROJECT_ID="$GCP_PROJECT_ID" GCP_REGION="$GCP_REGION" GKE_CLUSTER_NAME="$GKE_CLUSTER_NAME" \
GKE_NAMESPACE="$GKE_NAMESPACE" MODEL_EGRESS_CIDR="$MODEL_EGRESS_CIDR" TLS_HOSTNAME="$TLS_HOSTNAME" \
PYTHONPATH="$ms67_project_root/src" python - <<'PY'
import json, os
from pathlib import Path
from lightyear_data.contracts import seal, sign

services = ("azn-server", "customer", "account", "transfer", "checks", "testrunner", "creditscore", "chatbot")
root = Path(os.environ["OUTPUT_ROOT"])
environment = seal({
    "schema_version": "1.0",
    "environment_type": "lightyear-cloudbank-ms65-environment",
    "release": "0.65.0",
    "cluster_identity_sha256": os.environ["CLUSTER_IDENTITY"],
    "namespace": os.environ["GKE_NAMESPACE"],
    "ingress_namespace": "ingress-nginx",
    "database_egress_cidr": os.environ["DATABASE_CIDR"],
    "model_egress_cidr": os.environ["MODEL_EGRESS_CIDR"],
    "service_secret_names": {service: f"cloudbank-{service}-external" for service in services},
    "non_production": True,
})
profile = sign({
    "schema_version": "1.0",
    "profile_type": "lightyear-cloudbank-ms67-platform-profile",
    "release": "0.67.0",
    "signer": os.environ["SIGNER"],
    "context": f"gke_{os.environ['GCP_PROJECT_ID']}_{os.environ['GCP_REGION']}_{os.environ['GKE_CLUSTER_NAME']}",
    "cluster_uid_sha256": os.environ["CLUSTER_IDENTITY"],
    "provider": "google-gke-standard-regional",
    "region": os.environ["GCP_REGION"],
    "namespace": os.environ["GKE_NAMESPACE"],
    "namespace_uid_sha256": os.environ["NAMESPACE_IDENTITY"],
    "ingress_url": f"https://{os.environ['TLS_HOSTNAME']}",
    "expected_hostname": os.environ["TLS_HOSTNAME"],
    "mutating_drills_authorized": True,
    "production_access_authorized": False,
    "non_production": True,
}, os.environ["LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY"], os.environ["SIGNER"])
for name, payload in (("ms65-environment.json", environment), ("ms67-platform-profile.json", profile)):
    (root / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
echo "Created $output_root/ms65-environment.json and $output_root/ms67-platform-profile.json"
