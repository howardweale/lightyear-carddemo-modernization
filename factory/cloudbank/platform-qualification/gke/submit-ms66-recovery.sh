#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud jq git sha256sum
ms67_require_environment
ms67_require_mutation_ack
ms67_require_non_production_project
[[ $# -eq 1 ]] || { echo "Usage: submit-ms66-recovery.sh RECOVERY_STATE" >&2; exit 2; }
recovery_state="$1"
[[ -f "$recovery_state" && "$(wc -c < "$recovery_state")" -le 4194304 ]] || {
  echo "RECOVERY_STATE must be a local JSON file no larger than 4 MiB" >&2
  exit 2
}
jq -e '
  if .state_type == "lightyear-cloudbank-ms66-isolated-lane-recovery" then
    .production_environment == false
    and ((.namespace_uid | type) == "string" or .namespace_uid == null)
    and .cleanup_required == true
  elif .state_type == "lightyear-cloudbank-journey-recovery" then
    (.run_id | type == "string")
    and (.context | type == "string")
    and (.namespace | type == "string")
    and (.images | type == "object" and length == 8)
    and (.original_deployments | type == "object")
    and (.stopped_services | type == "array")
  else false end' "$recovery_state" >/dev/null || {
  echo "RECOVERY_STATE is not an active governed MS66 lane recovery journal" >&2
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
service_account="cloudbank-ms67-evidence@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
source_commit="$(git -C "$ms67_project_root" rev-parse HEAD)"
[[ "$(git -C "$ms67_project_root" branch --show-current)" == "main" \
   && "$(git -C "$ms67_project_root" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)" == \
      "origin/main" \
   && "$source_commit" == "$(git -C "$ms67_project_root" rev-parse '@{upstream}')" \
   && -z "$(git -C "$ms67_project_root" status --porcelain --untracked-files=normal)" ]] || {
  echo "MS66 recovery must be submitted from a clean main matching origin/main" >&2
  exit 2
}

active_builds="$(gcloud builds list --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --ongoing --format=json | \
  jq '[.[] | select(((.tags // []) | index("ms67-ms66-recovery")) != null)]')"
if [[ "$(jq 'length' <<<"$active_builds")" -ne 0 ]]; then
  jq -r '.[] | "ACTIVE_MS66_RECOVERY_BUILD=\(.id) status=\(.status)"' <<<"$active_builds"
  exit 0
fi

gcloud services enable cloudresourcemanager.googleapis.com --project "$GCP_PROJECT_ID" >/dev/null
gcloud secrets describe "$evidence_secret" --project "$GCP_PROJECT_ID" >/dev/null
enabled_versions="$(gcloud secrets versions list "$evidence_secret" \
  --project "$GCP_PROJECT_ID" --format=json | \
  jq '[.[] | select(.state == "ENABLED")] | length')"
[[ "$enabled_versions" -eq 1 ]] || {
  echo "Evidence secret must have exactly one enabled version" >&2
  exit 2
}
gcloud iam service-accounts describe "$service_account" --project "$GCP_PROJECT_ID" >/dev/null
gcloud storage buckets describe "gs://$evidence_bucket" --project "$GCP_PROJECT_ID" >/dev/null

for role in roles/container.developer roles/logging.logWriter roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member "serviceAccount:$service_account" --role "$role" >/dev/null
done
gcloud secrets add-iam-policy-binding "$evidence_secret" --project "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" --role roles/secretmanager.secretAccessor >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$evidence_bucket" \
  --member "serviceAccount:$service_account" --role roles/storage.objectAdmin >/dev/null

state_sha="$(sha256sum "$recovery_state" | cut -d' ' -f1)"
state_uri="gs://$evidence_bucket/recovery-inputs/ms66-$state_sha.json"
gcloud storage cp "$recovery_state" "$state_uri" --project "$GCP_PROJECT_ID"
config="$ms67_gke_dir/cloudbuild-ms66-recovery.yaml"
substitutions="_REGION=$GCP_REGION,_CLUSTER=$GKE_CLUSTER_NAME,_SOURCE_COMMIT=$source_commit"
substitutions+=",_RECOVERY_STATE_URI=$state_uri,_RECOVERY_STATE_SHA256=$state_sha"
substitutions+=",_EVIDENCE_BUCKET_PREFIX=gs://$evidence_bucket/ms66-recovery"
substitutions+=",_EVIDENCE_SECRET=$evidence_secret,_SIGNER=$service_account"
build_id="$(gcloud builds submit --no-source --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --config "$config" \
  --service-account "projects/$GCP_PROJECT_ID/serviceAccounts/$service_account" \
  --substitutions "$substitutions" --async --format='value(id)')"
[[ "$build_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || {
  echo "Cloud Build did not return a build ID" >&2
  exit 1
}

printf '%s\n' "$build_id" > "$HOME/ms66-recovery-build-id"
echo "MS66_RECOVERY_BUILD_ID=$build_id"
echo "MS66_RECOVERY_EVIDENCE=gs://$evidence_bucket/ms66-recovery/ms66-recovery-$build_id/"
echo "MS66_RECOVERY_BUILD=SUBMITTED"
