#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
tool="$project_dir/tools/cloudbank_platform_qualification.py"
action="${1:-verify}"
shift || true

case "$action" in
  build|verify)
    exec "$LIGHTYEAR_PYTHON_BIN" "$tool" "$action" --project-root "$project_dir"
    ;;
  preflight)
    [[ $# -eq 2 ]] || { echo "preflight requires PROFILE OUTPUT_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$tool" preflight --profile "$1" --output-root "$2"
    ;;
  admit)
    [[ $# -eq 6 ]] || { echo "admit requires MS65_RECEIPT MS66_RECEIPT PROFILE OBSERVATION OUTPUT_ROOT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$tool" admit --project-root "$project_dir" \
      --ms65-receipt "$1" --ms66-receipt "$2" --profile "$3" --observation "$4" \
      --output-root "$5" --signer "$6"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$tool" verify-receipt --project-root "$project_dir" --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-platform-qualification.sh [build|verify|preflight PROFILE OUTPUT_ROOT|admit MS65_RECEIPT MS66_RECEIPT PROFILE OBSERVATION OUTPUT_ROOT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
