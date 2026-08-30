#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
export LIGHTYEAR_CICS_VSAM_WORKSPACE="$project_dir"

action="${1:-verify}"
output_dir="${2:-$project_dir/work/cics-vsam-readiness}"
mkdir -p "$output_dir"

if [[ "$action" == "template" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness capture-template \
    --output "$output_dir/zos-capture.template.json"
elif [[ "$action" == "compare" ]]; then
  baseline="${3:?Usage: ./cics-vsam-readiness.sh compare OUTPUT_DIR ZOS_CAPTURE}"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness local-capture \
    --project-root "$project_dir" --output "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness validate-capture --capture "$baseline"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness compare \
    --baseline "$baseline" --candidate "$output_dir/local-capture.json" \
    --output "$output_dir/comparison.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness issue \
    --comparison "$output_dir/comparison.json" --output "$output_dir/readiness-receipt.json"
elif [[ "$action" == "verify" || "$action" == "build" ]]; then
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory.cics_vsam_private
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness local-capture \
    --project-root "$project_dir" --output "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness validate-capture \
    --capture "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness compare \
    --baseline "$output_dir/local-capture.json" --candidate "$output_dir/local-capture.json" \
    --output "$output_dir/comparison.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness issue \
    --comparison "$output_dir/comparison.json" --output "$output_dir/readiness-receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness validate-receipt \
    --receipt "$output_dir/readiness-receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness capture-template \
    --output "$output_dir/zos-capture.template.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.cics_vsam_qualification build \
    --project-root "$project_dir" --output-root "$output_dir"
  if [[ "$action" == "verify" ]]; then
    cmp "$project_dir/readiness/cics-vsam/local-capture.json" "$output_dir/local-capture.json"
    cmp "$project_dir/readiness/cics-vsam/comparison.json" "$output_dir/comparison.json"
    cmp "$project_dir/readiness/cics-vsam/readiness-receipt.json" "$output_dir/readiness-receipt.json"
    cmp "$project_dir/readiness/cics-vsam/zos-capture.template.json" "$output_dir/zos-capture.template.json"
    cmp "$project_dir/readiness/cics-vsam/conformance.receipt.json" "$output_dir/conformance.receipt.json"
    cmp "$project_dir/readiness/cics-vsam/compatibility-ledger.json" "$output_dir/compatibility-ledger.json"
    cmp "$project_dir/readiness/cics-vsam/qualification.json" "$output_dir/qualification.json"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.cics_vsam_qualification verify \
      --project-root "$project_dir"
  fi
  echo "CICS/VSAM bounded qualification passed; live z/OS equivalence remains fail-closed."
else
  echo "Usage: ./cics-vsam-readiness.sh [build|verify|template|compare] [output-dir] [zos-capture]" >&2
  exit 2
fi
