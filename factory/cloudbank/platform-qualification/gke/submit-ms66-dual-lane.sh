#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud jq git sha256sum
ms67_require_environment
ms67_require_mutation_ack
ms67_require_non_production_project
[[ $# -eq 4 ]] || {
  echo "Usage: submit-ms66-dual-lane.sh MS61_RECEIPT MS64_RECEIPT TARGET_IMAGE_LOCK POSTGRESQL_PROBE_IMAGE" >&2
  exit 2
}

ms61_receipt="$1"
ms64_receipt="$2"
target_image_lock="$3"
postgresql_probe_image="$4"
inputs=("$ms61_receipt" "$ms64_receipt" "$target_image_lock")
names=(ms61-receipt ms64-receipt target-image-lock)
for input in "${inputs[@]}"; do
  [[ -f "$input" && "$(wc -c < "$input")" -le 4194304 ]] || {
    echo "Every MS66 input must be a local JSON file no larger than 4 MiB: $input" >&2
    exit 2
  }
  jq -e 'type == "object"' "$input" >/dev/null
done
jq -e '.receipt_type == "lightyear-cloudbank-oracle-postgresql-equivalence-execution"' \
  "$ms61_receipt" >/dev/null || { echo "MS61_RECEIPT has the wrong receipt type" >&2; exit 2; }
jq -e '.receipt_type == "lightyear-cloudbank-edge-ai-execution"' \
  "$ms64_receipt" >/dev/null || { echo "MS64_RECEIPT has the wrong receipt type" >&2; exit 2; }
jq -e '.lock_type == "lightyear-cloudbank-ms65-image-lock" and (.images | length) == 8' \
  "$target_image_lock" >/dev/null || { echo "TARGET_IMAGE_LOCK has the wrong lock type" >&2; exit 2; }
[[ "$postgresql_probe_image" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]] || {
  echo "POSTGRESQL_PROBE_IMAGE must use an immutable sha256 digest" >&2
  exit 2
}
[[ "${JAVA_BASE_IMAGE:-}" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]] || {
  echo "JAVA_BASE_IMAGE must use an immutable sha256 digest" >&2
  exit 2
}

oracle_candidate="${MS66_ORACLE_IMAGE_CANDIDATE:-gvenzl/oracle-free:23.26.1-slim-faststart}"
microtx_candidate="${MS66_MICROTX_IMAGE_CANDIDATE:-container-registry.oracle.com/database/otmm:24.4.1}"
[[ "$oracle_candidate" =~ ^[^[:space:]]+:[^[:space:]]+$ \
   && "$microtx_candidate" =~ ^[^[:space:]]+:[^[:space:]]+$ ]] || {
  echo "Native runtime candidates must use explicit, non-latest tags" >&2
  exit 2
}
[[ "$oracle_candidate" != *:latest && "$microtx_candidate" != *:latest ]] || {
  echo "Native runtime candidates cannot use latest" >&2
  exit 2
}

evidence_secret="${MS67_EVIDENCE_SECRET:-cloudbank-ms67-evidence-key}"
evidence_bucket="${MS67_EVIDENCE_BUCKET:-${GCP_PROJECT_ID}-ms67-evidence}"
evidence_bucket="${evidence_bucket#gs://}"
evidence_bucket="${evidence_bucket%/}"
[[ "$evidence_bucket" =~ ^[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]$ ]] || {
  echo "MS67_EVIDENCE_BUCKET must name one GCS bucket" >&2
  exit 2
}
service_account_name="cloudbank-ms67-evidence"
service_account="${service_account_name}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
config="$ms67_gke_dir/cloudbuild-ms66-dual-lane.yaml"
source_commit="$(git -C "$ms67_project_root" rev-parse HEAD)"
branch="$(git -C "$ms67_project_root" branch --show-current)"
upstream_name="$(git -C "$ms67_project_root" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"
[[ "$source_commit" =~ ^[0-9a-f]{40}$ && "$branch" == "main" && "$upstream_name" == "origin/main" ]] || {
  echo "MS66 qualification must be submitted from main tracking origin/main" >&2
  exit 2
}
[[ -z "$(git -C "$ms67_project_root" status --porcelain --untracked-files=normal)" ]] || {
  echo "The checkout must be clean so Cloud Build executes only the reviewed commit" >&2
  exit 2
}
[[ "$source_commit" == "$(git -C "$ms67_project_root" rev-parse '@{upstream}')" ]] || {
  echo "HEAD must match its pushed upstream before Cloud Build can fetch it" >&2
  exit 2
}

active_builds="$(gcloud builds list --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --ongoing --format=json | \
  jq '[.[] | select(((.tags // []) | index("ms67-ms66-dual-lane")) != null)]')"
if [[ "$(jq 'length' <<<"$active_builds")" -ne 0 ]]; then
  jq -r '.[] | "ACTIVE_MS66_DUAL_LANE_BUILD=\(.id) status=\(.status)"' <<<"$active_builds"
  exit 0
fi

for api in artifactregistry.googleapis.com cloudbuild.googleapis.com \
  cloudresourcemanager.googleapis.com container.googleapis.com secretmanager.googleapis.com; do
  gcloud services enable "$api" --project "$GCP_PROJECT_ID" >/dev/null
done
gcloud secrets describe "$evidence_secret" --project "$GCP_PROJECT_ID" >/dev/null
enabled_versions="$(gcloud secrets versions list "$evidence_secret" --project "$GCP_PROJECT_ID" \
  --format=json | jq '[.[] | select(.state == "ENABLED")] | length')"
[[ "$enabled_versions" -eq 1 ]] || {
  echo "Evidence secret must have exactly one enabled version" >&2
  exit 2
}
gcloud secrets describe cloudbank-azn-server-external --project "$GCP_PROJECT_ID" >/dev/null
gcloud iam service-accounts describe "$service_account" --project "$GCP_PROJECT_ID" >/dev/null
gcloud storage buckets describe "gs://$evidence_bucket" --project "$GCP_PROJECT_ID" >/dev/null

for role in roles/artifactregistry.writer roles/container.developer roles/logging.logWriter \
  roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member "serviceAccount:$service_account" --role "$role" >/dev/null
done
for secret in "$evidence_secret" cloudbank-azn-server-external; do
  gcloud secrets add-iam-policy-binding "$secret" --project "$GCP_PROJECT_ID" \
    --member "serviceAccount:$service_account" --role roles/secretmanager.secretAccessor >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://$evidence_bucket" \
  --member "serviceAccount:$service_account" --role roles/storage.objectAdmin >/dev/null

digests=()
for input in "${inputs[@]}"; do digests+=("$(sha256sum "$input" | cut -d' ' -f1)"); done
input_set_sha="$(printf '%s\n' "${digests[@]}" | sha256sum | cut -d' ' -f1)"
input_prefix="gs://$evidence_bucket/live-inputs/ms66-$input_set_sha"
uris=()
for index in "${!inputs[@]}"; do
  uri="$input_prefix/${names[$index]}.json"
  gcloud storage cp "${inputs[$index]}" "$uri" --project "$GCP_PROJECT_ID"
  uris+=("$uri")
done

substitutions="_REGION=$GCP_REGION,_CLUSTER=$GKE_CLUSTER_NAME,_TARGET_NAMESPACE=$GKE_NAMESPACE"
substitutions+=",_MODEL_NAMESPACE=$MODEL_NAMESPACE,_MODEL_NAME=$OLLAMA_MODEL_NAME"
substitutions+=",_ARTIFACT_REPOSITORY=$ARTIFACT_REPOSITORY,_SOURCE_COMMIT=$source_commit"
substitutions+=",_JAVA_BASE_IMAGE=$JAVA_BASE_IMAGE,_POSTGRESQL_PROBE_IMAGE=$postgresql_probe_image"
substitutions+=",_ORACLE_IMAGE_CANDIDATE=$oracle_candidate,_MICROTX_IMAGE_CANDIDATE=$microtx_candidate"
substitutions+=",_EVIDENCE_BUCKET_PREFIX=gs://$evidence_bucket/ms66-dual-lane"
substitutions+=",_EVIDENCE_SECRET=$evidence_secret,_SIGNER=$service_account"
for index in "${!names[@]}"; do
  variable="$(printf '%s' "${names[$index]}" | tr '[:lower:]-' '[:upper:]_')"
  substitutions+=",_${variable}_URI=${uris[$index]},_${variable}_SHA256=${digests[$index]}"
done

build_id="$(gcloud builds submit --no-source --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --config "$config" \
  --service-account "projects/$GCP_PROJECT_ID/serviceAccounts/$service_account" \
  --substitutions "$substitutions" --async --format='value(id)')"
[[ "$build_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || {
  echo "Cloud Build did not return a build ID" >&2
  exit 1
}

printf '%s\n' "$build_id" > "$HOME/ms66-dual-lane-build-id"
echo "MS66_DUAL_LANE_BUILD_ID=$build_id"
echo "MS66_DUAL_LANE_SOURCE_COMMIT=$source_commit"
echo "MS66_DUAL_LANE_EVIDENCE=gs://$evidence_bucket/ms66-dual-lane/ms66-$build_id/"
echo "MS66_DUAL_LANE_RECOVERY_STATE=gs://$evidence_bucket/ms66-dual-lane/ms66-$build_id/recovery-state.json"
echo "MS66_DUAL_LANE_BUILD=SUBMITTED"
