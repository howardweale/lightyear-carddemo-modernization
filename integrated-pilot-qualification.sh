#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
output_dir="${2:-$project_dir/work/integrated-pilot-qualification}"
mkdir -p "$output_dir"

if [[ "$action" == "build" || "$action" == "verify" ]]; then
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_pilot.integrated_qualification build \
    --project-root "$project_dir" --output-root "$output_dir"
  if [[ "$action" == "verify" ]]; then
    for name in conformance.receipt.json evidence-matrix.json compatibility-ledger.json qualification.json; do
      cmp "$project_dir/pilot/integrated-qualification/$name" "$output_dir/$name"
    done
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_pilot.integrated_qualification verify \
      --project-root "$project_dir"
  fi
  echo "Integrated pilot Wave 2 development qualification passed; dispatch, native execution, and production release remain blocked."
else
  echo "Usage: ./integrated-pilot-qualification.sh [build|verify] [output-dir]" >&2
  exit 2
fi
