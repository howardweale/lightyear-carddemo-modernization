#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud jq git sha256sum
ms67_require_environment
ms67_require_mutation_ack
ms67_require_non_production_project
[[ $# -eq 3 ]] || {
  echo "Usage: submit-shared-journeys.sh IMAGE_LOCK MS64_RECEIPT PROBE_IMAGE" >&2
  exit 2
}

image_lock="$1"
ms64_receipt="$2"
probe_image="$3"
[[ -f "$image_lock" && -f "$ms64_receipt" ]] || {
  echo "IMAGE_LOCK and MS64_RECEIPT must be files" >&2
  exit 2
}
[[ "$probe_image" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]] || {
  echo "PROBE_IMAGE must use an immutable sha256 digest" >&2
  exit 2
}

evidence_secret="${MS67_EVIDENCE_SECRET:-cloudbank-ms67-evidence-key}"
evidence_bucket="${MS67_EVIDENCE_BUCKET:-${GCP_PROJECT_ID}-ms67-evidence}"
service_account_name="cloudbank-ms67-evidence"
service_account="${service_account_name}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
config="$ms67_gke_dir/cloudbuild-shared-journeys.yaml"
source_commit="$(git -C "$ms67_project_root" rev-parse HEAD)"
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || {
  echo "Pinned source commit is invalid" >&2
  exit 2
}
[[ -z "$(git -C "$ms67_project_root" status --porcelain --untracked-files=normal)" ]] || {
  echo "The source checkout must be clean so Cloud Build executes the reviewed commit" >&2
  exit 2
}
upstream_commit="$(git -C "$ms67_project_root" rev-parse '@{upstream}' 2>/dev/null || true)"
[[ "$source_commit" == "$upstream_commit" ]] || {
  echo "HEAD must match its pushed upstream before Cloud Build can fetch it" >&2
  exit 2
}

active_builds="$(gcloud builds list \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --ongoing \
  --format=json | \
  jq '[.[] | select(((.tags // []) | index("ms67-shared-journeys")) != null)]')"
if [[ "$(jq 'length' <<<"$active_builds")" -ne 0 ]]; then
  jq -r '.[] | "ACTIVE_SHARED_JOURNEY_BUILD=\(.id) status=\(.status)"' <<<"$active_builds"
  exit 0
fi

gcloud secrets describe "$evidence_secret" --project "$GCP_PROJECT_ID" >/dev/null
enabled_evidence_versions="$(gcloud secrets versions list "$evidence_secret" \
  --project "$GCP_PROJECT_ID" --format=json | jq '[.[] | select(.state == "ENABLED")] | length')"
[[ "$enabled_evidence_versions" -eq 1 ]] || {
  echo "Evidence secret must have exactly one enabled version" >&2
  exit 2
}
gcloud secrets describe cloudbank-azn-server-external --project "$GCP_PROJECT_ID" >/dev/null
gcloud secrets describe cloudbank-checks-external --project "$GCP_PROJECT_ID" >/dev/null
gcloud iam service-accounts describe "$service_account" --project "$GCP_PROJECT_ID" >/dev/null
gcloud storage buckets describe "gs://$evidence_bucket" --project "$GCP_PROJECT_ID" >/dev/null

# GkeRuntime independently reads the environment label under the dedicated
# build identity. Keep that fail-closed check usable even when an older
# bootstrap predates this required API.
gcloud services enable cloudresourcemanager.googleapis.com \
  --project "$GCP_PROJECT_ID" >/dev/null
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" \
  --role roles/container.developer >/dev/null
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" \
  --role roles/logging.logWriter >/dev/null
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" \
  --role roles/serviceusage.serviceUsageConsumer >/dev/null
for secret in "$evidence_secret" cloudbank-azn-server-external cloudbank-checks-external; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project "$GCP_PROJECT_ID" \
    --member "serviceAccount:$service_account" \
    --role roles/secretmanager.secretAccessor >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://$evidence_bucket" \
  --member "serviceAccount:$service_account" \
  --role roles/storage.objectAdmin >/dev/null

image_lock_sha="$(sha256sum "$image_lock" | cut -d' ' -f1)"
ms64_receipt_sha="$(sha256sum "$ms64_receipt" | cut -d' ' -f1)"
input_prefix="gs://$evidence_bucket/live-inputs/${image_lock_sha}-${ms64_receipt_sha}"
image_lock_uri="$input_prefix/image-lock.json"
ms64_receipt_uri="$input_prefix/ms64-edge-ai.receipt.json"
gcloud storage cp "$image_lock" "$image_lock_uri" --project "$GCP_PROJECT_ID"
gcloud storage cp "$ms64_receipt" "$ms64_receipt_uri" --project "$GCP_PROJECT_ID"

build_id="$(gcloud builds submit --no-source \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --config "$config" \
  --service-account "projects/$GCP_PROJECT_ID/serviceAccounts/$service_account" \
  --substitutions "_REGION=$GCP_REGION,_CLUSTER=$GKE_CLUSTER_NAME,_NAMESPACE=$GKE_NAMESPACE,_SOURCE_COMMIT=$source_commit,_IMAGE_LOCK_URI=$image_lock_uri,_IMAGE_LOCK_SHA256=$image_lock_sha,_MS64_RECEIPT_URI=$ms64_receipt_uri,_MS64_RECEIPT_SHA256=$ms64_receipt_sha,_PROBE_IMAGE=$probe_image,_EVIDENCE_BUCKET_PREFIX=gs://$evidence_bucket/shared-journeys,_EVIDENCE_SECRET=$evidence_secret,_SIGNER=$service_account" \
  --async \
  --format='value(id)')"
[[ "$build_id" =~ ^[0-9a-f-]{36}$ ]] || {
  echo "Cloud Build did not return a build ID" >&2
  exit 1
}

printf '%s\n' "$build_id" > "$HOME/ms67-shared-journeys-build-id"
echo "MS67_SHARED_JOURNEYS_BUILD_ID=$build_id"
echo "MS67_SHARED_JOURNEYS_SOURCE_COMMIT=$source_commit"
echo "MS67_SHARED_JOURNEYS_EVIDENCE=gs://$evidence_bucket/shared-journeys/ms67-journeys-$build_id/"
echo "MS67_SHARED_JOURNEYS_BUILD=SUBMITTED"
