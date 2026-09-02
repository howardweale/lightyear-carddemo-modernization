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
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_dark_factory.py" \
      "$action" --project-root "$project_dir"
    ;;
  verify-source)
    [[ $# -eq 1 ]] || { echo "verify-source requires SOURCE_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_dark_factory.py" \
      verify-source --source-root "$1"
    ;;
  run)
    [[ $# -eq 5 ]] || { echo "run requires SOURCE_ROOT ORACLE_RECEIPT POSTGRESQL_RECEIPT OUTPUT_ROOT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_dark_factory.py" run \
      --project-root "$project_dir" --source-root "$1" --oracle-receipt "$2" \
      --postgresql-receipt "$3" --output-root "$4" --signer "$5"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_dark_factory.py" verify-receipt \
      --project-root "$project_dir" --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-dark-factory.sh [build|verify|verify-source SOURCE_ROOT|run SOURCE_ROOT ORACLE_RECEIPT POSTGRESQL_RECEIPT OUTPUT_ROOT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
