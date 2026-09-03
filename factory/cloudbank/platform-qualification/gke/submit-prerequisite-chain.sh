#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud jq git
ms67_require_environment
ms67_require_mutation_ack
ms67_require_non_production_project
[[ $# -eq 1 ]] || { echo "Usage: submit-prerequisite-chain.sh SIGNER" >&2; exit 2; }
signer="$1"
[[ -n "$signer" ]] || { echo "SIGNER is required" >&2; exit 2; }

evidence_secret="${MS67_EVIDENCE_SECRET:-cloudbank-ms67-evidence-key}"
evidence_bucket="${MS67_EVIDENCE_BUCKET:-${GCP_PROJECT_ID}-ms67-evidence}"
service_account_name="cloudbank-ms67-evidence-builder"
service_account="${service_account_name}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
config="$ms67_gke_dir/cloudbuild-prerequisite-chain.yaml"

gcloud config set project "$GCP_PROJECT_ID" >/dev/null
gcloud secrets describe "$evidence_secret" --project "$GCP_PROJECT_ID" >/dev/null
enabled_versions="$(gcloud secrets versions list "$evidence_secret" --project "$GCP_PROJECT_ID" \
  --format=json | jq '[.[] | select(.state == "ENABLED")] | length')"
[[ "$enabled_versions" -eq 1 ]] || {
  echo "Evidence secret must have exactly one enabled version" >&2
  exit 2
}

if ! gcloud iam service-accounts describe "$service_account" \
  --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$service_account_name" \
    --project "$GCP_PROJECT_ID" \
    --display-name "CloudBank MS67 evidence builder"
fi

if ! gcloud storage buckets describe "gs://$evidence_bucket" \
  --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$evidence_bucket" \
    --project "$GCP_PROJECT_ID" --location "$GCP_REGION" \
    --uniform-bucket-level-access --public-access-prevention
  gcloud storage buckets update "gs://$evidence_bucket" --versioning
fi

gcloud secrets add-iam-policy-binding "$evidence_secret" \
  --project "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" \
  --role roles/secretmanager.secretAccessor >/dev/null
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" \
  --role roles/artifactregistry.writer >/dev/null
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" \
  --role roles/logging.logWriter >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$evidence_bucket" \
  --member "serviceAccount:$service_account" \
  --role roles/storage.objectAdmin >/dev/null

build_id="$(gcloud builds submit "$ms67_project_root" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --config "$config" \
  --service-account "projects/$GCP_PROJECT_ID/serviceAccounts/$service_account" \
  --gcs-source-staging-dir "gs://$evidence_bucket/source" \
  --substitutions "_REGION=$GCP_REGION,_ARTIFACT_REPOSITORY=$ARTIFACT_REPOSITORY,_JAVA_BASE_IMAGE=$JAVA_BASE_IMAGE,_EVIDENCE_SECRET=$evidence_secret,_EVIDENCE_BUCKET=$evidence_bucket,_SIGNER=$signer" \
  --async --format='value(id)')"
[[ "$build_id" =~ ^[0-9a-f-]{36}$ ]] || { echo "Cloud Build did not return a build ID" >&2; exit 1; }

printf '%s\n' "$build_id" > "$HOME/ms67-prerequisite-build-id"
echo "PREREQUISITE_BUILD_ID=$build_id"
echo "EVIDENCE_BUCKET=gs://$evidence_bucket/prerequisite-chain/$build_id/"
echo "MS67_PREREQUISITE_BUILD=SUBMITTED"
