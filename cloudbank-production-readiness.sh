#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
shift || true

case "$action" in
  build|verify)
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_readiness.py" "$action" --project-root "$project_dir"
    ;;
  verify-source)
    [[ $# -eq 1 ]] || { echo "verify-source requires SOURCE_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_readiness.py" verify-source --source-root "$1"
    ;;
  materialize)
    [[ $# -eq 2 ]] || { echo "materialize requires SOURCE_ROOT OUTPUT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_readiness.py" materialize --project-root "$project_dir" --source-root "$1" --output "$2"
    ;;
  render)
    [[ $# -eq 4 ]] || { echo "render requires MS64_RECEIPT IMAGE_LOCK ENVIRONMENT OUTPUT_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_readiness.py" render --ms64-receipt "$1" --image-lock "$2" --environment "$3" --output-root "$4"
    ;;
  run)
    [[ $# -eq 7 ]] || { echo "run requires SOURCE_ROOT MS64_RECEIPT IMAGE_LOCK ENVIRONMENT OBSERVATION OUTPUT_ROOT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_readiness.py" run --project-root "$project_dir" --source-root "$1" --ms64-receipt "$2" --image-lock "$3" --environment "$4" --observation "$5" --output-root "$6" --signer "$7"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_readiness.py" verify-receipt --project-root "$project_dir" --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-production-readiness.sh [build|verify|verify-source SOURCE_ROOT|materialize SOURCE_ROOT OUTPUT|render MS64_RECEIPT IMAGE_LOCK ENVIRONMENT OUTPUT_ROOT|run SOURCE_ROOT MS64_RECEIPT IMAGE_LOCK ENVIRONMENT OBSERVATION OUTPUT_ROOT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
