#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-validate}"
memory_root="${LIGHTYEAR_MEMORY_ROOT:-$project_dir/factory/memory/store}"
policy="$project_dir/factory/memory/policy.json"

case "$action" in
  validate)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory memory-validate \
      --memory-root "$memory_root" --memory-policy "$policy"
    ;;
  summary)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory memory-summary \
      --memory-root "$memory_root" --memory-policy "$policy"
    ;;
  ingest)
    test -n "${2:-}" || { echo "Usage: ./semantic-memory.sh ingest <run-directory>"; exit 2; }
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory memory-ingest \
      --run-dir "$2" --memory-root "$memory_root" --memory-policy "$policy"
    ;;
  query)
    work_order="${2:-$project_dir/factory/work-orders/intcalc-repair.example.json}"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory memory-query \
      --work-order "$work_order" --source-root "$project_dir" \
      --graph "$project_dir/knowledge/graph.snapshot.json.gz" \
      --evidence-pack "$project_dir/knowledge/evidence/source.pack.json.gz" \
      --memory-root "$memory_root" --memory-policy "$policy"
    ;;
  *)
    echo "Usage: ./semantic-memory.sh [validate|summary|query|ingest] [path]"
    exit 2
    ;;
esac
