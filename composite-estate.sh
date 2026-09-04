#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
action="${1:-verify}"
legacy_root="${2:-${CARDDEMO_UPSTREAM_ROOT:-}}"

if [[ -z "$legacy_root" && -d "$project_dir/../carddemo-upstream/app" ]]; then
  legacy_root="$project_dir/../carddemo-upstream"
fi
if [[ -z "$legacy_root" && -d "$project_dir/work/carddemo-upstream/app" ]]; then
  legacy_root="$project_dir/work/carddemo-upstream"
fi
if [[ -z "$legacy_root" ]]; then
  echo "CardDemo upstream is required. Set CARDDEMO_UPSTREAM_ROOT or pass its path." >&2
  exit 2
fi

base="$project_dir/knowledge/graph.snapshot.json.gz"
fragment="$project_dir/extensions/pli/pli.fragment.json"
oracle_fragment="${LIGHTYEAR_ORACLE_REFERENCE_FRAGMENT:-$project_dir/reference-estates/idempiere/oracle-customer-large.fragment.json}"
cloudbank_fragment="${LIGHTYEAR_CLOUDBANK_REFERENCE_FRAGMENT:-$project_dir/reference-estates/cloudbank/cloudbank-reference.fragment.json}"
capabilities="$project_dir/knowledge/capabilities/mainframe-readiness.json"
canonical_dir="$project_dir/knowledge/composite"

build_projection() {
  local output_dir="$1"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph build-composite \
    --base-graph "$base" \
    --fragment "$fragment" \
    --fragment "$oracle_fragment" \
    --fragment "$cloudbank_fragment" \
    --capabilities "$capabilities" \
    --legacy-root "$legacy_root" \
    --modern-root "$project_dir" \
    --output "$output_dir/estate.snapshot.json.gz" \
    --receipt "$output_dir/estate.receipt.json" \
    --evidence-pack "$output_dir/source.pack.json.gz" \
    --evidence-receipt "$output_dir/source.receipt.json"
}

if [[ "$action" == "build-working" ]]; then
  working_dir="$project_dir/work/composite-estate"
  mkdir -p "$working_dir"
  build_projection "$working_dir"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate-composite \
    --graph "$working_dir/estate.snapshot.json.gz" \
    --base-graph "$base" \
    --fragment "$fragment" \
    --fragment "$oracle_fragment" \
    --fragment "$cloudbank_fragment" \
    --capabilities "$capabilities" \
    --evidence-pack "$working_dir/source.pack.json.gz"
  echo "Working composite built in work/composite-estate."
elif [[ "$action" == "build" ]]; then
  mkdir -p "$canonical_dir"
  build_projection "$canonical_dir"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate-composite \
    --graph "$canonical_dir/estate.snapshot.json.gz" \
    --base-graph "$base" \
    --fragment "$fragment" \
    --fragment "$oracle_fragment" \
    --fragment "$cloudbank_fragment" \
    --capabilities "$capabilities" \
    --evidence-pack "$canonical_dir/source.pack.json.gz"
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/composite-estate-verify"
  mkdir -p "$generated"
  build_projection "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph validate-composite \
    --graph "$generated/estate.snapshot.json.gz" \
    --base-graph "$base" \
    --fragment "$fragment" \
    --fragment "$oracle_fragment" \
    --fragment "$cloudbank_fragment" \
    --capabilities "$capabilities" \
    --evidence-pack "$generated/source.pack.json.gz"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph compare-snapshots \
    --expected "$canonical_dir/estate.snapshot.json.gz" \
    --actual "$generated/estate.snapshot.json.gz"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph compare-evidence-packs \
    --expected "$canonical_dir/source.pack.json.gz" \
    --actual "$generated/source.pack.json.gz"
  cmp "$canonical_dir/estate.receipt.json" "$generated/estate.receipt.json"
  cmp "$canonical_dir/source.receipt.json" "$generated/source.receipt.json"
  echo "Composite estate is deterministic, current, read-only, and evidence-bound."
else
  echo "Usage: ./composite-estate.sh [build|build-working|verify] [optional-carddemo-upstream-root]" >&2
  exit 2
fi
