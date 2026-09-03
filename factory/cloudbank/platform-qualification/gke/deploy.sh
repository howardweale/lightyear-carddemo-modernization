#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud kubectl helm jq python
ms67_require_environment
ms67_require_mutation_ack
ms67_require_non_production_project
gcloud config set project "$GCP_PROJECT_ID" >/dev/null
[[ $# -eq 4 ]] || { echo "Usage: deploy.sh MS64_RECEIPT IMAGE_LOCK MS65_ENVIRONMENT OUTPUT_ROOT" >&2; exit 2; }
ms64_receipt="$1"
image_lock="$2"
environment="$3"
output_root="$4"
mkdir -p "$output_root"
[[ -z "$(find "$output_root" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
  echo "OUTPUT_ROOT must be fresh" >&2; exit 2;
}

gcloud container clusters get-credentials "$GKE_CLUSTER_NAME" --region "$GCP_REGION" --dns-endpoint
kube_context="gke_${GCP_PROJECT_ID}_${GCP_REGION}_${GKE_CLUSTER_NAME}"
python_tool="$ms67_project_root/tools/cloudbank_platform_qualification.py"
PYTHONPATH="$ms67_project_root/src" python "$python_tool" render-gke-addons \
  --project-id "$GCP_PROJECT_ID" --region "$GCP_REGION" --cluster-name "$GKE_CLUSTER_NAME" \
  --namespace "$GKE_NAMESPACE" --hostname "$TLS_HOSTNAME" \
  --letsencrypt-email "$LETSENCRYPT_EMAIL" --otel-collector-image "$OTEL_COLLECTOR_IMAGE" \
  --model-namespace "$MODEL_NAMESPACE" --ollama-model-image "$OLLAMA_MODEL_IMAGE" \
  --ollama-model-name "$OLLAMA_MODEL_NAME" \
  --ollama-model-manifest-sha256 "$OLLAMA_MODEL_MANIFEST_SHA256" \
  --google-apis-cidr "$GOOGLE_APIS_CIDR" \
  --output "$output_root/gke-addons.yaml"
PYTHONPATH="$ms67_project_root/src" python "$ms67_project_root/tools/cloudbank_production_readiness.py" render \
  --ms64-receipt "$ms64_receipt" --image-lock "$image_lock" --environment "$environment" \
  --output-root "$output_root/ms65-bundle"

kubectl --context "$kube_context" apply -f "$output_root/gke-addons.yaml"
for service in "${ms67_services[@]}"; do
  kubectl --context "$kube_context" -n "$GKE_NAMESPACE" wait "externalsecret/cloudbank-$service" \
    --for=condition=Ready --timeout=10m
done
kubectl --context "$kube_context" apply -f "$output_root/ms65-bundle/cloudbank-production-readiness.yaml"
model_host="ollama.${MODEL_NAMESPACE}.svc.cluster.local"
kubectl --context "$kube_context" -n "$GKE_NAMESPACE" set env deployment/chatbot \
  CLOUDBANK_CHAT_MODEL_BASE_URL="http://${model_host}:11434" \
  CLOUDBANK_CHAT_MODEL_NAME="$OLLAMA_MODEL_NAME" \
  CLOUDBANK_CHAT_ALLOWED_MODEL_HOSTS="$model_host" \
  CLOUDBANK_CHAT_ALLOW_HTTP_CLUSTER_LOCAL="true"
kubectl --context "$kube_context" -n "$MODEL_NAMESPACE" rollout status deployment/ollama --timeout=15m
for service in "${ms67_services[@]}"; do
  kubectl --context "$kube_context" -n "$GKE_NAMESPACE" set env "deployment/$service" \
    OTEL_SERVICE_NAME="$service" OTEL_RESOURCE_ATTRIBUTES="deployment.environment=non-production,lightyear.milestone=ms67"
  kubectl --context "$kube_context" -n "$GKE_NAMESPACE" rollout status "deployment/$service" --timeout=15m
done
kubectl --context "$kube_context" -n "$GKE_NAMESPACE" wait certificate/cloudbank-ms67-tls --for=condition=Ready --timeout=30m

kubectl --context "$kube_context" -n "$GKE_NAMESPACE" get deployments,services,pods,poddisruptionbudgets,networkpolicies,externalsecrets
echo "Deployment ready at https://$TLS_HOSTNAME"
echo "Continue with LIVE-RUNBOOK.md; this script does not declare qualification complete."
