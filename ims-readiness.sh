#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
output_dir="${2:-$project_dir/work/ims-readiness}"
mkdir -p "$output_dir"

if [[ "$action" == "template" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims capture-template \
    --output "$output_dir/zos-capture.template.json"
elif [[ "$action" == "compare" ]]; then
  baseline="${3:?Usage: ./ims-readiness.sh compare OUTPUT_DIR ZOS_CAPTURE}"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims local-capture \
    --project-root "$project_dir" --output "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims validate-capture --capture "$baseline"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims compare \
    --baseline "$baseline" --candidate "$output_dir/local-capture.json" \
    --output "$output_dir/comparison.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims issue \
    --comparison "$output_dir/comparison.json" --output "$output_dir/readiness-receipt.json"
elif [[ "$action" == "verify" || "$action" == "build" ]]; then
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory.ims_private
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims local-capture \
    --project-root "$project_dir" --output "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims validate-capture \
    --capture "$output_dir/local-capture.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims compare \
    --baseline "$output_dir/local-capture.json" --candidate "$output_dir/local-capture.json" \
    --output "$output_dir/comparison.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims issue \
    --comparison "$output_dir/comparison.json" --output "$output_dir/readiness-receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims validate-receipt \
    --receipt "$output_dir/readiness-receipt.json"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.ims capture-template \
    --output "$output_dir/zos-capture.template.json"
  if [[ "$action" == "verify" ]]; then
    cmp "$project_dir/readiness/ims-expiry/local-capture.json" "$output_dir/local-capture.json"
    cmp "$project_dir/readiness/ims-expiry/comparison.json" "$output_dir/comparison.json"
    cmp "$project_dir/readiness/ims-expiry/readiness-receipt.json" "$output_dir/readiness-receipt.json"
    cmp "$project_dir/readiness/ims-expiry/zos-capture.template.json" "$output_dir/zos-capture.template.json"
  fi
  echo "IMS logical development proof passed; live BMP equivalence remains fail-closed."
else
  echo "Usage: ./ims-readiness.sh [build|verify|template|compare] [output-dir] [zos-capture]" >&2
  exit 2
fi
