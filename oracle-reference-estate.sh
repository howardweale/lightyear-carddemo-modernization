#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
action="${1:-verify}"

base="$project_dir/knowledge/graph.snapshot.json.gz"
slices="$project_dir/reference-estates/idempiere/business-slices.json"
inventory="$project_dir/reference-estates/idempiere/inventory.json"
source_pin="$project_dir/reference-estates/idempiere/source-pin.json"
fragment="$project_dir/reference-estates/idempiere/oracle-customer-large.fragment.json"
receipt="$project_dir/reference-estates/idempiere/oracle-customer-large.receipt.json"

build_projection() {
  local output_fragment="$1"
  local output_receipt="$2"
  local input_inventory="${3:-$inventory}"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph build-oracle-reference \
    --base-graph "$base" \
    --slices "$slices" \
    --inventory "$input_inventory" \
    --source-pin "$source_pin" \
    --output "$output_fragment" \
    --receipt "$output_receipt"
}

if [[ "$action" == "build-full" ]]; then
  source_root="${2:-}"
  if [[ -z "$source_root" ]]; then
    echo "Pinned iDempiere upstream checkout is required for build-full." >&2
    exit 2
  fi
  generated="$project_dir/work/reference-estates/idempiere"
  mkdir -p "$generated"
  "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/inventory_idempiere_reference.py" \
    --source-root "$source_root" \
    --output "$generated/inventory.json"
  build_projection "$generated/oracle-reference.fragment.json.gz" \
    "$generated/oracle-reference.receipt.json" \
    "$generated/inventory.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate-oracle-reference \
    --base-graph "$base" \
    --slices "$slices" \
    --inventory "$generated/inventory.json" \
    --source-pin "$source_pin" \
    --fragment "$generated/oracle-reference.fragment.json.gz"
  echo "Full iDempiere reference projection built in work/reference-estates/idempiere."
elif [[ "$action" == "build" ]]; then
  build_projection "$fragment" "$receipt"
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/oracle-reference-estate-verify"
  mkdir -p "$generated"
  build_projection "$generated/oracle-customer-large.fragment.json" \
    "$generated/oracle-customer-large.receipt.json"
  cmp "$fragment" "$generated/oracle-customer-large.fragment.json"
  cmp "$receipt" "$generated/oracle-customer-large.receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate-oracle-reference \
    --base-graph "$base" \
    --slices "$slices" \
    --inventory "$inventory" \
    --source-pin "$source_pin" \
    --fragment "$fragment"
  echo "The bounded iDempiere reference projection is deterministic and current."
else
  echo "Usage: ./oracle-reference-estate.sh [build|verify|build-full IDEMPIERE_ROOT]" >&2
  exit 2
fi
