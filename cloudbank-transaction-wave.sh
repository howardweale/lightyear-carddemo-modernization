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
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_transaction_wave.py" \
      "$action" --project-root "$project_dir"
    ;;
  verify-source)
    [[ $# -eq 1 ]] || { echo "verify-source requires SOURCE_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_transaction_wave.py" \
      verify-source --source-root "$1"
    ;;
  admit)
    [[ $# -eq 4 ]] || { echo "admit requires SOURCE_ROOT MS57_RECEIPT OUTPUT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_transaction_wave.py" admit \
      --project-root "$project_dir" --source-root "$1" --ms57-receipt "$2" \
      --output "$3" --signer "$4"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_transaction_wave.py" \
      verify-receipt --project-root "$project_dir" --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-transaction-wave.sh [build|verify|verify-source SOURCE_ROOT|admit SOURCE_ROOT MS57_RECEIPT OUTPUT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
