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
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_qualification.py" \
      "$action" --project-root "$project_dir"
    ;;
  verify-source)
    [[ $# -eq 1 ]] || { echo "verify-source requires SOURCE_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_qualification.py" \
      verify-source --source-root "$1"
    ;;
  run)
    [[ $# -eq 4 ]] || { echo "run requires SOURCE_ROOT MS56_RECEIPT OUTPUT_ROOT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_qualification.py" run \
      --project-root "$project_dir" --source-root "$1" --ms56-receipt "$2" \
      --output-root "$3" --signer "$4"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_production_qualification.py" \
      verify-receipt --project-root "$project_dir" --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-production-qualification.sh" \
      "[build|verify|verify-source SOURCE_ROOT|run SOURCE_ROOT MS56_RECEIPT OUTPUT_ROOT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
