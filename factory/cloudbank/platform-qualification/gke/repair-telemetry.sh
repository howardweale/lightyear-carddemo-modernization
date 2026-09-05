#!/usr/bin/env bash
# Repair only the collector resources; preserve a small deployment record and configuration.
set -euo pipefail
set +x
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
ms67_require_tools gcloud kubectl jq python sha256sum
ms67_require_environment
ms67_require_mutation_ack
ms67_require_non_production_project
[[ $# -eq 1 ]] || { echo "Usage: repair-telemetry.sh FRESH_OUTPUT_ROOT" >&2; exit 2; }
output_root="$1"
mkdir -p "$output_root"
output_root="$(cd "$output_root" && pwd)"
[[ -z "$(find "$output_root" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
  echo "OUTPUT_ROOT must be fresh" >&2; exit 2;
}
provider="$(gcloud container clusters describe "$GKE_CLUSTER_NAME" --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" --format='value(networkConfig.datapathProvider)')"
[[ "$provider" == ADVANCED_DATAPATH ]] || {
  echo "Collector metadata policy requires the MS67 Dataplane V2 cluster" >&2; exit 2;
}
kube_context="gke_${GCP_PROJECT_ID}_${GCP_REGION}_${GKE_CLUSTER_NAME}"
evidence_bucket="gs://${GCP_PROJECT_ID}-ms67-evidence/telemetry-recovery/$(basename "$output_root")/"
stage="rendering collector configuration"
heartbeat_pid=""
cleanup() {
  local result=$?
  trap - EXIT
  if [[ -n "$heartbeat_pid" ]]; then
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
  fi
  local state=failed
  [[ "$result" -eq 0 ]] && state=ready
  if ! jq -n --arg status "$state" --arg stage "$stage" --arg context "$kube_context" \
    '{status:$status,stage:$stage,context:$context,qualification_complete:false}' \
    > "$output_root/collector-status.json"; then
    echo "Unable to write collector status at $output_root" >&2
    result=1
  fi
  # A renderer failure can leave no YAML. Still hash and upload the failure record.
  shopt -s nullglob
  local evidence_files=("$output_root"/*.yaml "$output_root"/*.json)
  if [[ ${#evidence_files[@]} -eq 0 ]] || \
    ! (cd "$output_root" && sha256sum ./*.yaml ./*.json > SHA256SUMS); then
    echo "Unable to checksum collector evidence at $output_root" >&2
    result=1
  elif ! gcloud storage cp "${evidence_files[@]}" "$output_root/SHA256SUMS" \
    "$evidence_bucket" --project "$GCP_PROJECT_ID"; then
    echo "Collector evidence upload failed; local evidence is retained at $output_root" >&2
    result=1
  fi
  echo "MS67_TELEMETRY_ROOT=$output_root"
  echo "MS67_TELEMETRY_BUCKET=$evidence_bucket"
  if [[ "$result" -eq 0 ]]; then
    echo "MS67_COLLECTOR=READY"
    echo "Collector replicas are ready; Cloud Monitoring and Cloud Trace delivery still require live evidence."
  else
    echo "MS67_COLLECTOR=FAILED"
    echo "Failure stage: $stage"
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
PYTHONPATH="$ms67_project_root/src" python "$ms67_project_root/tools/cloudbank_platform_qualification.py" \
  render-gke-addons --telemetry-only \
  --project-id "$GCP_PROJECT_ID" --region "$GCP_REGION" --cluster-name "$GKE_CLUSTER_NAME" \
  --namespace "$GKE_NAMESPACE" --hostname "$TLS_HOSTNAME" --letsencrypt-email "$LETSENCRYPT_EMAIL" \
  --otel-collector-image "$OTEL_COLLECTOR_IMAGE" --model-namespace "$MODEL_NAMESPACE" \
  --ollama-model-image "$OLLAMA_MODEL_IMAGE" --ollama-model-name "$OLLAMA_MODEL_NAME" \
  --ollama-model-manifest-sha256 "$OLLAMA_MODEL_MANIFEST_SHA256" \
  --google-apis-cidr "$GOOGLE_APIS_CIDR" --output "$output_root/collector.yaml"
stage="applying collector project, identity policy, and health probes"
gcloud container clusters get-credentials "$GKE_CLUSTER_NAME" --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" --dns-endpoint
kubectl --context "$kube_context" apply -f "$output_root/collector.yaml"
stage="waiting for two healthy collector replicas"
(
  sleeper=""
  trap '[[ -z "$sleeper" ]] || kill "$sleeper" 2>/dev/null || true; exit 0' TERM INT
  while true; do
    sleep 20 &
    sleeper=$!
    wait "$sleeper"
    sleeper=""
    echo "$(date -u +%H:%M:%S) UTC | Waiting for collector readiness"
  done
) &
heartbeat_pid=$!
kubectl --context "$kube_context" -n observability rollout status deployment/otel-collector --timeout=10m
kubectl --context "$kube_context" -n observability get deployment otel-collector -o json | \
  jq '{generation:.metadata.generation,observed_generation:.status.observedGeneration,
       desired:.spec.replicas,ready:(.status.readyReplicas // 0),
       updated:(.status.updatedReplicas // 0),available:(.status.availableReplicas // 0)}' \
  > "$output_root/collector-rollout.json"
jq -e '.desired == 2 and .ready == 2 and .updated == 2 and .available == 2
       and .observed_generation >= .generation' "$output_root/collector-rollout.json" >/dev/null
stage="two collector replicas ready"
