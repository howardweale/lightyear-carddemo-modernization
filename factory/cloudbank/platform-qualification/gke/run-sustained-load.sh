#!/usr/bin/env bash
# macOS/Linux launcher. Run under caffeinate on macOS to prevent idle sleep.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
source "$repo/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$repo/src"

[[ $# -le 1 ]] || { echo "Usage: run-sustained-load.sh [INPUTS_ROOT]" >&2; exit 2; }
[[ "${LIGHTYEAR_NON_PRODUCTION_ACK:-}" == I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS ]] || {
  echo "LIGHTYEAR_NON_PRODUCTION_ACK is required for synthetic business writes." >&2
  exit 2
}
for tool in gcloud kubectl gke-gcloud-auth-plugin k6; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 2; }
done

project="${GCP_PROJECT_ID:-lightyear-ms67-nonproduction}"
region="${GCP_REGION:-us-west1}"
cluster="${GKE_CLUSTER_NAME:-cloudbank-ms67}"
namespace="${GKE_NAMESPACE:-cloudbank-ms67}"
account="${CLOUDSDK_CORE_ACCOUNT:-howard.weale@gmail.com}"
export CLOUDSDK_CORE_ACCOUNT="$account" CLOUDSDK_CORE_PROJECT="$project"
gcloud auth print-access-token --account "$account" >/dev/null
gcloud container clusters get-credentials "$cluster" --region "$region" --project "$project" --account "$account"

mkdir -p "$HOME/ms67-evidence"
run_root="$(mktemp -d "$HOME/ms67-evidence/ms67-load.XXXXXXXX")"
inputs="${1:-$run_root/inputs}"
if [[ $# -eq 0 ]]; then
  [[ "$project" == lightyear-ms67-nonproduction && "$namespace" == cloudbank-ms67 ]] || {
    echo "Supply INPUTS_ROOT explicitly for another environment." >&2
    exit 2
  }
  mkdir -m 700 "$inputs"
  bucket="gs://lightyear-ms67-nonproduction-ms67-evidence"
  bound="$bucket/live-inputs/ms66-a982568eef9284ac8316180c952049774f8bf6d3dfb5052e8d68fe5e202f4e8e"
  ms66="$bucket/ms66-dual-lane/ms66-7025c311-7cbe-424b-841f-b999a2e188a0"
  echo "MS67_LOAD_INPUTS=Downloading the existing signed deployment and MS66 evidence"
  gcloud storage cp "$bound/target-image-lock.json" "$inputs/image-lock.json" --project "$project"
  gcloud storage cp "$bound/ms64-receipt.json" "$inputs/ms64-receipt.json" --project "$project"
  gcloud storage cp "$bucket/deployments/ms67-deploy.deg_mw1y/ms67-platform-profile.json" "$inputs/platform-profile.json" --project "$project"
  gcloud storage cp "$ms66/cloudbank-whole-application-equivalence.receipt.json" "$inputs/ms66-receipt.json" --project "$project"
  gcloud storage cp "$ms66/postgresql-journeys.json" "$inputs/journeys.json" --project "$project"
  "$LIGHTYEAR_PYTHON_BIN" - "$inputs" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
expected = {
    "image-lock.json": "bfb1d6dd2055e388aaf91c24f55adc3f7fd5dd48d318af23a254a4fd62e29715",
    "ms64-receipt.json": "5d807f2e882bb68f2d44c08f261a9eb8a3190915d727b4952e843e0a704fe674",
    "platform-profile.json": "cfa845d9f93c143ec87563a0c510fe4d0f517d8baad07d92d65a203786f2c9f4",
    "ms66-receipt.json": "c5c81415081ab65f80de5d8a72fd8d010bf433aff2e8e88b24ad777f8a064dd3",
}
for name, digest in expected.items():
    value = json.loads((root / name).read_text(encoding="utf-8"))
    if value.get("content_sha256") != digest:
        raise SystemExit("Downloaded input does not match the recorded MS67 binding: " + name)
PY
fi

common=(--project "$project" --region "$region" --cluster "$cluster" --namespace "$namespace"
  --signer "$account" --evidence-bucket "gs://$project-ms67-evidence/sustained-load"
  --image-lock "$inputs/image-lock.json" --ms64-receipt "$inputs/ms64-receipt.json"
  --platform-profile "$inputs/platform-profile.json" --ms66-receipt "$inputs/ms66-receipt.json"
  --journeys "$inputs/journeys.json")

printf 'MS67_LOAD_RUN=%s\n' "$run_root/run"
printf 'MS67_LOAD_INPUTS_ROOT=%s\n' "$inputs"
"$LIGHTYEAR_PYTHON_BIN" "$repo/tools/cloudbank_sustained_load.py" run "${common[@]}" --output-root "$run_root/run"
"$LIGHTYEAR_PYTHON_BIN" "$repo/tools/cloudbank_sustained_load.py" verify "${common[@]}" \
  --observation "$run_root/run/sustained-load.observation.json"
printf 'MS67_LOAD_VERIFICATION=PASSED\nMS67_LOAD_ROOT=%s\n' "$run_root/run"
