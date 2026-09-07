#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ms67_require_tools gcloud jq git sha256sum
ms67_require_environment
ms67_require_mutation_ack
ms67_require_non_production_project
[[ $# -eq 5 ]] || {
  echo "Usage: submit-ms65-rehearsal.sh IMAGE_LOCK MS64_RECEIPT MS65_ENVIRONMENT JOURNEYS DATABASE_RECOVERY" >&2
  exit 2
}

inputs=("$@")
names=(image-lock ms64-receipt ms65-environment journeys database-recovery)
for input in "${inputs[@]}"; do
  [[ -f "$input" && "$(wc -c < "$input")" -le 4194304 ]] || {
    echo "Every MS65 input must be a local JSON file no larger than 4 MiB: $input" >&2
    exit 2
  }
  jq -e 'type == "object"' "$input" >/dev/null
done
jq -e '.status == "passed-shared-journeys" and .scenario_count == 18' "${inputs[3]}" >/dev/null || {
  echo "JOURNEYS must be a passing 18-scenario shared execution" >&2
  exit 2
}
jq -e '.status == "passed-isolated-database-recovery" and .recovery.status == "restored"' \
  "${inputs[4]}" >/dev/null || {
  echo "DATABASE_RECOVERY must be a passing restored isolated recovery observation" >&2
  exit 2
}
journeys_sha="$(jq -r '.content_sha256 // empty' "${inputs[3]}")"
[[ "$journeys_sha" =~ ^[0-9a-f]{64}$ ]] || {
  echo "JOURNEYS must contain a valid content hash" >&2
  exit 2
}
jq -e --arg journeys_sha "$journeys_sha" \
  '.bindings.journeys_content_sha256 == $journeys_sha' "${inputs[4]}" >/dev/null || {
  echo "DATABASE_RECOVERY must be bound to the supplied JOURNEYS observation" >&2
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
config="$ms67_gke_dir/cloudbuild-ms65-rehearsal.yaml"
source_commit="$(git -C "$ms67_project_root" rev-parse HEAD)"
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || { echo "Pinned source commit is invalid" >&2; exit 2; }
branch="$(git -C "$ms67_project_root" branch --show-current)"
upstream_name="$(git -C "$ms67_project_root" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"
[[ "$branch" == "main" && "$upstream_name" == "origin/main" ]] || {
  echo "MS65 qualification must be submitted from main tracking origin/main" >&2
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

active_builds="$(gcloud builds list --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --ongoing --format=json | jq '[.[] | select(((.tags // []) | index("ms67-ms65-rehearsal")) != null)]')"
if [[ "$(jq 'length' <<<"$active_builds")" -ne 0 ]]; then
  jq -r '.[] | "ACTIVE_MS65_REHEARSAL_BUILD=\(.id) status=\(.status)"' <<<"$active_builds"
  exit 0
fi

gcloud services enable cloudresourcemanager.googleapis.com --project "$GCP_PROJECT_ID" >/dev/null
gcloud secrets describe "$evidence_secret" --project "$GCP_PROJECT_ID" >/dev/null
enabled_versions="$(gcloud secrets versions list "$evidence_secret" --project "$GCP_PROJECT_ID" \
  --format=json | jq '[.[] | select(.state == "ENABLED")] | length')"
[[ "$enabled_versions" -eq 1 ]] || { echo "Evidence secret must have exactly one enabled version" >&2; exit 2; }
gcloud iam service-accounts describe "$service_account" --project "$GCP_PROJECT_ID" >/dev/null
gcloud storage buckets describe "gs://$evidence_bucket" --project "$GCP_PROJECT_ID" >/dev/null

for role in roles/container.developer roles/logging.logWriter roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member "serviceAccount:$service_account" --role "$role" >/dev/null
done
gcloud secrets add-iam-policy-binding "$evidence_secret" --project "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" --role roles/secretmanager.secretAccessor >/dev/null
gcloud secrets add-iam-policy-binding cloudbank-azn-server-external --project "$GCP_PROJECT_ID" \
  --member "serviceAccount:$service_account" --role roles/secretmanager.secretAccessor >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$evidence_bucket" \
  --member "serviceAccount:$service_account" --role roles/storage.objectAdmin >/dev/null

digests=()
for input in "${inputs[@]}"; do digests+=("$(sha256sum "$input" | cut -d' ' -f1)"); done
input_set_sha="$(printf '%s\n' "${digests[@]}" | sha256sum | cut -d' ' -f1)"
input_prefix="gs://$evidence_bucket/live-inputs/ms65-$input_set_sha"
uris=()
for index in "${!inputs[@]}"; do
  uri="$input_prefix/${names[$index]}.json"
  gcloud storage cp "${inputs[$index]}" "$uri" --project "$GCP_PROJECT_ID"
  uris+=("$uri")
done

substitutions="_REGION=$GCP_REGION,_CLUSTER=$GKE_CLUSTER_NAME,_NAMESPACE=$GKE_NAMESPACE"
substitutions+=",_SOURCE_COMMIT=$source_commit,_EVIDENCE_BUCKET_PREFIX=gs://$evidence_bucket/ms65-rehearsal"
substitutions+=",_EVIDENCE_SECRET=$evidence_secret,_SIGNER=$service_account"
for index in "${!names[@]}"; do
  variable="$(printf '%s' "${names[$index]}" | tr '[:lower:]-' '[:upper:]_')"
  substitutions+=",_${variable}_URI=${uris[$index]},_${variable}_SHA256=${digests[$index]}"
done

build_id="$(gcloud builds submit --no-source --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --config "$config" \
  --service-account "projects/$GCP_PROJECT_ID/serviceAccounts/$service_account" \
  --substitutions "$substitutions" --async --format='value(id)')"
[[ "$build_id" =~ ^[0-9a-f-]{36}$ ]] || { echo "Cloud Build did not return a build ID" >&2; exit 1; }

printf '%s\n' "$build_id" > "$HOME/ms65-rehearsal-build-id"
echo "MS65_REHEARSAL_BUILD_ID=$build_id"
echo "MS65_REHEARSAL_SOURCE_COMMIT=$source_commit"
echo "MS65_REHEARSAL_EVIDENCE=gs://$evidence_bucket/ms65-rehearsal/ms65-rehearsal-$build_id/"
echo "MS65_REHEARSAL_BUILD=SUBMITTED"
