#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
action="${1:-verify}"

base="$project_dir/knowledge/graph.snapshot.json.gz"
workloads="$project_dir/reference-estates/cloudbank/workloads.json"
inventory="$project_dir/reference-estates/cloudbank/inventory.json"
source_pin="$project_dir/reference-estates/cloudbank/source-pin.json"
fragment="$project_dir/reference-estates/cloudbank/cloudbank-reference.fragment.json"
receipt="$project_dir/reference-estates/cloudbank/cloudbank-reference.receipt.json"

build_projection() {
  local output_fragment="$1"
  local output_receipt="$2"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph build-cloudbank-reference \
    --base-graph "$base" \
    --workloads "$workloads" \
    --inventory "$inventory" \
    --source-pin "$source_pin" \
    --output "$output_fragment" \
    --receipt "$output_receipt"
}

if [[ "$action" == "inventory" || "$action" == "verify-inventory" ]]; then
  source_root="${2:-}"
  if [[ -z "$source_root" ]]; then
    echo "CloudBank upstream checkout is required for $action." >&2
    exit 2
  fi
  inventory_args=(--source-root "$source_root" --output "$inventory")
  if [[ "$action" == "verify-inventory" ]]; then inventory_args+=(--verify); fi
  exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/inventory_cloudbank_reference.py" \
    "${inventory_args[@]}"
elif [[ "$action" == "build" ]]; then
  build_projection "$fragment" "$receipt"
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/cloudbank-reference-estate-verify"
  mkdir -p "$generated"
  build_projection "$generated/cloudbank-reference.fragment.json" \
    "$generated/cloudbank-reference.receipt.json"
  cmp "$fragment" "$generated/cloudbank-reference.fragment.json"
  cmp "$receipt" "$generated/cloudbank-reference.receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate-cloudbank-reference \
    --base-graph "$base" \
    --workloads "$workloads" \
    --inventory "$inventory" \
    --source-pin "$source_pin" \
    --fragment "$fragment"
  echo "CloudBank modern Oracle reference projection is deterministic and current."
else
  echo "Usage: ./cloudbank-reference-estate.sh [inventory SOURCE_ROOT|verify-inventory SOURCE_ROOT|build|verify]" >&2
  exit 2
fi
