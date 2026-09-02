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
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_checks_messaging.py" "$action" --project-root "$project_dir"
    ;;
  verify-source)
    [[ $# -eq 1 ]] || { echo "verify-source requires SOURCE_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_checks_messaging.py" verify-source --source-root "$1"
    ;;
  materialize)
    [[ $# -eq 2 ]] || { echo "materialize requires SOURCE_ROOT OUTPUT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_checks_messaging.py" materialize --project-root "$project_dir" --source-root "$1" --output "$2"
    ;;
  run)
    [[ $# -eq 4 ]] || { echo "run requires SOURCE_ROOT MS62_RECEIPT OUTPUT_ROOT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_checks_messaging.py" run --project-root "$project_dir" --source-root "$1" --ms62-receipt "$2" --output-root "$3" --signer "$4"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_checks_messaging.py" verify-receipt --project-root "$project_dir" --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-checks-messaging.sh [build|verify|verify-source SOURCE_ROOT|materialize SOURCE_ROOT OUTPUT|run SOURCE_ROOT MS62_RECEIPT OUTPUT_ROOT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
