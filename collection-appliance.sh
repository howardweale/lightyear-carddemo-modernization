#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/extensions/runtime:$project_dir/src"

action="${1:-verify}"
appliance_profile="$project_dir/extensions/adapters/enterprise-appliance.profile.json"
campaign_profile="$project_dir/extensions/adapters/mainframe-access.profile.json"
responses="$project_dir/extensions/adapters/fixtures/enterprise-appliance.simulated.responses.json"
faults="$project_dir/extensions/adapters/fixtures/enterprise-appliance.faults.json"
graph="$project_dir/knowledge/graph.snapshot.json.gz"
canonical="$project_dir/extensions/adapters/appliance"

build_appliance() {
  local output="$1"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions appliance-fixture \
    --appliance-profile "$appliance_profile" \
    --campaign-profile "$campaign_profile" \
    --responses "$responses" \
    --faults "$faults" \
    --graph "$graph" \
    --output-root "$output"
}

case "$action" in
  build)
    mkdir -p "$canonical"
    build_appliance "$canonical"
    ;;
  verify)
    generated="$project_dir/work/enterprise-appliance-verify"
    rm -rf "$generated"
    mkdir -p "$generated"
    build_appliance "$generated" >/dev/null
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions appliance-validate \
      --appliance-profile "$appliance_profile" \
      --campaign-profile "$campaign_profile" \
      --graph "$graph" \
      --artifact-root "$generated"
    for name in \
      appliance.receipt.json checkpoint.json fault-lab.receipt.json \
      lightyear.cics-cmci.capture.json \
      lightyear.db2-zos-catalog.capture.json \
      lightyear.zosmf-jobs.capture.json; do
      cmp "$canonical/$name" "$generated/$name"
    done
    "$LIGHTYEAR_PYTHON_BIN" -m unittest extensions.tests.test_enterprise_collection_appliance -v
    echo "Enterprise collection, recovery, retention, and fault evidence is deterministic."
    ;;
  live|resume)
    base_url="${2:?Usage: ./collection-appliance.sh $action HTTPS-BASE-URL KEY-ID [OUTPUT] [AUTH-MODE]}"
    key_id="${3:?Usage: ./collection-appliance.sh $action HTTPS-BASE-URL KEY-ID [OUTPUT] [AUTH-MODE]}"
    output="${4:-$project_dir/work/enterprise-appliance-live}"
    auth_mode="${5:-bearer-env}"
    : "${LIGHTYEAR_MAINFRAME_BEARER:?Set LIGHTYEAR_MAINFRAME_BEARER}"
    : "${LIGHTYEAR_EXTENSION_EVIDENCE_KEY:?Set LIGHTYEAR_EXTENSION_EVIDENCE_KEY}"
    live_args=(
      -m lightyear_extensions appliance-live
      --appliance-profile "$appliance_profile"
      --campaign-profile "$campaign_profile"
      --faults "$faults"
      --graph "$graph"
      --base-url "$base_url"
      --key-id "$key_id"
      --auth-mode "$auth_mode"
      --output-root "$output"
    )
    if [[ "$action" == "resume" ]]; then live_args+=(--resume); fi
    if [[ -n "${LIGHTYEAR_MAINFRAME_CA_FILE:-}" ]]; then
      live_args+=(--ca-file "$LIGHTYEAR_MAINFRAME_CA_FILE")
    fi
    if [[ -n "${LIGHTYEAR_MAINFRAME_CLIENT_CERTIFICATE:-}" ]]; then
      live_args+=(--client-certificate "$LIGHTYEAR_MAINFRAME_CLIENT_CERTIFICATE")
    fi
    if [[ -n "${LIGHTYEAR_MAINFRAME_CLIENT_KEY:-}" ]]; then
      live_args+=(--client-key "$LIGHTYEAR_MAINFRAME_CLIENT_KEY")
    fi
    "$LIGHTYEAR_PYTHON_BIN" "${live_args[@]}"
    ;;
  validate-live)
    key_id="${2:?Usage: ./collection-appliance.sh validate-live KEY-ID OUTPUT}"
    output="${3:?Usage: ./collection-appliance.sh validate-live KEY-ID OUTPUT}"
    : "${LIGHTYEAR_EXTENSION_EVIDENCE_KEY:?Set LIGHTYEAR_EXTENSION_EVIDENCE_KEY}"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions appliance-validate \
      --appliance-profile "$appliance_profile" \
      --campaign-profile "$campaign_profile" \
      --graph "$graph" \
      --artifact-root "$output" \
      --trusted-key-id "$key_id"
    ;;
  *)
    echo "Usage: ./collection-appliance.sh [build|verify|live|resume|validate-live]" >&2
    exit 2
    ;;
esac
