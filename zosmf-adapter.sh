#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
cd "$project_dir"

action="${1:-simulate}"
if [[ "$action" == "simulate" ]]; then
  output="${2:-$project_dir/work/zosmf-simulator/intcalc.runtime.snapshot.json.gz}"
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime simulate-zosmf --output "$output"
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/zosmf-adapter-verify/intcalc.runtime.snapshot.json.gz"
  mkdir -p "$(dirname "$generated")"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime simulate-zosmf --output "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime validate --snapshot "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_runtime compare \
    --expected "$project_dir/knowledge/runtime/zosmf/intcalc.runtime.snapshot.json.gz" \
    --actual "$generated"
  echo "z/OSMF simulator, adapter mapping, and trust boundary are deterministic."
else
  echo "Usage: ./zosmf-adapter.sh [simulate [output]|verify]" >&2
  exit 2
fi
