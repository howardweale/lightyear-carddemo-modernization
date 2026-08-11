#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
cd "$project_dir"

action="${1:-build}"
if [[ "$action" == "build" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime build
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/runtime-evidence-verify/runtime.snapshot.json.gz"
  mkdir -p "$(dirname "$generated")"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime build --output "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime validate --snapshot "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime validate
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime compare \
    --expected "$project_dir/knowledge/runtime/runtime.snapshot.json.gz" \
    --actual "$generated"
  "$project_dir/zosmf-adapter.sh" verify
  echo "Runtime evidence snapshot is deterministic, graph-bound, and policy-valid."
else
  echo "Usage: ./runtime-evidence.sh [build|verify]" >&2
  exit 2
fi
