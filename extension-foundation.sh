#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/extensions/runtime:$project_dir/src"

action="${1:-verify}"
graph="$project_dir/knowledge/graph.snapshot.json.gz"
spec="$project_dir/extensions/adapters/fixtures/zosmf-intcalc.simulated.spec.json"
capture="$project_dir/extensions/adapters/fixtures/zosmf-intcalc.simulated.capture.json"
replay="$project_dir/extensions/adapters/fixtures/zosmf-intcalc.simulated.replay.json"
fragment="$project_dir/extensions/pli/pli.fragment.json"
receipt="$project_dir/extensions/pli/pli.fragment.receipt.json"
catalog="$project_dir/extensions/catalog.json"
campaign_profile="$project_dir/extensions/adapters/mainframe-access.profile.json"
campaign_responses="$project_dir/extensions/adapters/fixtures/mainframe-access.simulated.responses.json"
campaign_canonical="$project_dir/extensions/adapters/campaign"

build_outputs() {
  local output_root="$1"
  mkdir -p "$output_root/adapters" "$output_root/pli" "$output_root/campaign"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions catalog \
    --output "$output_root/catalog.json" >/dev/null
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions build-fixture-capture \
    --spec "$spec" --graph "$graph" --output "$output_root/adapters/capture.json" >/dev/null
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions replay \
    --capture "$output_root/adapters/capture.json" --graph "$graph" \
    --output "$output_root/adapters/replay.json" >/dev/null
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions build-pli \
    --graph "$graph" --source-root "$project_dir/extensions/pli/reference" \
    --repository-root "$project_dir" --output "$output_root/pli/fragment.json" \
    --receipt "$output_root/pli/receipt.json" >/dev/null
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions campaign-fixture \
    --profile "$campaign_profile" --responses "$campaign_responses" \
    --graph "$graph" --output-root "$output_root/campaign" >/dev/null
}

case "$action" in
  build)
    build_outputs "$project_dir/work/extension-foundation-build"
    cp "$project_dir/work/extension-foundation-build/catalog.json" "$catalog"
    cp "$project_dir/work/extension-foundation-build/adapters/capture.json" "$capture"
    cp "$project_dir/work/extension-foundation-build/adapters/replay.json" "$replay"
    cp "$project_dir/work/extension-foundation-build/pli/fragment.json" "$fragment"
    cp "$project_dir/work/extension-foundation-build/pli/receipt.json" "$receipt"
    mkdir -p "$campaign_canonical"
    cp "$project_dir/work/extension-foundation-build/campaign/"*.json "$campaign_canonical/"
    ;;
  verify)
    generated="$project_dir/work/extension-foundation-verify"
    rm -rf "$generated"
    build_outputs "$generated"
    "$LIGHTYEAR_PYTHON_BIN" -m unittest discover \
      -s "$project_dir/extensions/tests" -p 'test_*.py' -v
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions validate-capture \
      --capture "$generated/adapters/capture.json" --graph "$graph" >/dev/null
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions validate-capture \
      --capture "$generated/adapters/replay.json" --graph "$graph" >/dev/null
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions validate-pli \
      --fragment "$generated/pli/fragment.json" --graph "$graph" >/dev/null
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions campaign-validate \
      --profile "$campaign_profile" --graph "$graph" \
      --capture-root "$generated/campaign" >/dev/null
    cmp "$catalog" "$generated/catalog.json"
    cmp "$capture" "$generated/adapters/capture.json"
    cmp "$replay" "$generated/adapters/replay.json"
    cmp "$fragment" "$generated/pli/fragment.json"
    cmp "$receipt" "$generated/pli/receipt.json"
    for expected in "$campaign_canonical/"*.json; do
      cmp "$expected" "$generated/campaign/$(basename "$expected")"
    done
    echo "Trusted adapter evidence, mainframe access campaign, record/replay, and PL/I graph extension are deterministic."
    ;;
  *)
    echo "Usage: ./extension-foundation.sh [build|verify]" >&2
    exit 2
    ;;
esac
