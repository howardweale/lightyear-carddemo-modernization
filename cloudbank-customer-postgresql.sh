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
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_customer_postgresql.py" \
      "$action" --project-root "$project_dir"
    ;;
  verify-source)
    [[ $# -eq 1 ]] || { echo "verify-source requires SOURCE_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_customer_postgresql.py" \
      verify-source --source-root "$1"
    ;;
  native-postgresql)
    [[ $# -eq 5 ]] || { echo "native-postgresql requires SOURCE_ROOT ORACLE_RECEIPT IMAGE_ID_SHA256 OUTPUT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_customer_postgresql.py" \
      native-postgresql --source-root "$1" --oracle-receipt "$2" \
      --postgresql-image-id-sha256 "$3" --output "$4" --signer "$5"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_customer_postgresql.py" \
      verify-receipt --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-customer-postgresql.sh [build|verify|verify-source SOURCE_ROOT|native-postgresql SOURCE_ROOT ORACLE_RECEIPT IMAGE_ID_SHA256 OUTPUT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
