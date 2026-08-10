#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
legacy_commit="59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
action="${1:-verify}"
legacy_root="${2:-${CARDDEMO_UPSTREAM_ROOT:-}}"

if [[ -z "$legacy_root" && -d "$project_dir/../carddemo-upstream/app" ]]; then
  legacy_root="$project_dir/../carddemo-upstream"
fi

if [[ -z "$legacy_root" ]]; then
  legacy_root="$project_dir/work/carddemo-upstream"
  if [[ ! -d "$legacy_root/.git" ]]; then
    git clone --filter=blob:none --no-checkout \
      https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git \
      "$legacy_root"
  fi
  git -C "$legacy_root" checkout --detach "$legacy_commit"
fi

export PYTHONPATH="$project_dir/src"

if [[ "$action" == "build" ]]; then
  python3 -m lightyear_knowledge_graph build \
    --legacy-root "$legacy_root" \
    --modern-root "$project_dir" \
    --manifest "$project_dir/knowledge/mappings/carddemo-intcalc.json" \
    --output "$project_dir/knowledge/graph.snapshot.json.gz" \
    --receipt "$project_dir/knowledge/graph.receipt.json" \
    --legacy-commit "$legacy_commit" \
    --modern-commit repository-content
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/knowledge-graph-verify"
  mkdir -p "$generated"
  python3 -m lightyear_knowledge_graph build \
    --legacy-root "$legacy_root" \
    --modern-root "$project_dir" \
    --manifest "$project_dir/knowledge/mappings/carddemo-intcalc.json" \
    --output "$generated/graph.snapshot.json.gz" \
    --receipt "$generated/graph.receipt.json" \
    --legacy-commit "$legacy_commit" \
    --modern-commit repository-content
  python3 -m lightyear_knowledge_graph validate --graph "$generated/graph.snapshot.json.gz"
  python3 -m lightyear_knowledge_graph gaps --graph "$generated/graph.snapshot.json.gz"
  python3 -m lightyear_knowledge_graph compare-snapshots \
    --expected "$project_dir/knowledge/graph.snapshot.json.gz" \
    --actual "$generated/graph.snapshot.json.gz"
  cmp "$project_dir/knowledge/graph.receipt.json" "$generated/graph.receipt.json"
  echo "Knowledge graph snapshot is deterministic, current, and policy-complete."
else
  echo "Usage: ./knowledge-graph.sh [build|verify] [optional-carddemo-upstream-root]" >&2
  exit 2
fi
