#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
output_dir="${2:-$project_dir/work/asm-readiness}"
mkdir -p "$output_dir"

if [[ "$action" == "template" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm capture-template \
    --output "$output_dir/zos-capture.template.json"
elif [[ "$action" == "compare" ]]; then
  baseline="${3:?Usage: ./asm-readiness.sh compare OUTPUT_DIR ZOS_CAPTURE}"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm local-capture \
    --project-root "$project_dir" --output "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm validate-capture --capture "$baseline"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm compare \
    --baseline "$baseline" --candidate "$output_dir/local-capture.json" \
    --output "$output_dir/comparison.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm issue \
    --comparison "$output_dir/comparison.json" --output "$output_dir/readiness-receipt.json"
elif [[ "$action" == "verify" || "$action" == "build" ]]; then
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory.asm_private
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm local-capture \
    --project-root "$project_dir" --output "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm validate-capture \
    --capture "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm compare \
    --baseline "$output_dir/local-capture.json" --candidate "$output_dir/local-capture.json" \
    --output "$output_dir/comparison.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm issue \
    --comparison "$output_dir/comparison.json" --output "$output_dir/readiness-receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm validate-receipt \
    --receipt "$output_dir/readiness-receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.asm capture-template \
    --output "$output_dir/zos-capture.template.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.hlasm_qualification build \
    --project-root "$project_dir" --output-root "$output_dir"
  if [[ "$action" == "verify" ]]; then
    cmp "$project_dir/readiness/asm-date/local-capture.json" "$output_dir/local-capture.json"
    cmp "$project_dir/readiness/asm-date/comparison.json" "$output_dir/comparison.json"
    cmp "$project_dir/readiness/asm-date/readiness-receipt.json" "$output_dir/readiness-receipt.json"
    cmp "$project_dir/readiness/asm-date/zos-capture.template.json" "$output_dir/zos-capture.template.json"
    cmp "$project_dir/readiness/asm-date/conformance.receipt.json" "$output_dir/conformance.receipt.json"
    cmp "$project_dir/readiness/asm-date/compatibility-ledger.json" "$output_dir/compatibility-ledger.json"
    cmp "$project_dir/readiness/asm-date/qualification.json" "$output_dir/qualification.json"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.hlasm_qualification verify \
      --project-root "$project_dir"
  fi
  echo "HLASM bounded qualification passed; native build and runtime equivalence remain fail-closed."
else
  echo "Usage: ./asm-readiness.sh [build|verify|template|compare] [output-dir] [zos-capture]" >&2
  exit 2
fi
