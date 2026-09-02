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
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_executable_baseline.py" \
      "$action" --project-root "$project_dir"
    ;;
  verify-source)
    [[ $# -eq 1 ]] || { echo "verify-source requires SOURCE_ROOT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_executable_baseline.py" \
      verify-source --source-root "$1"
    ;;
  source-build)
    [[ $# -eq 3 ]] || { echo "source-build requires SOURCE_ROOT OUTPUT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_executable_baseline.py" \
      source-build --source-root "$1" --output "$2" --signer "$3"
    ;;
  oracle-runtime)
    [[ $# -eq 5 ]] || { echo "oracle-runtime requires SOURCE_ROOT BUILD_RECEIPT IMAGE_ID_SHA256 OUTPUT SIGNER" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_executable_baseline.py" \
      oracle-runtime --source-root "$1" --build-receipt "$2" \
      --oracle-image-id-sha256 "$3" --output "$4" --signer "$5"
    ;;
  verify-receipt)
    [[ $# -eq 1 ]] || { echo "verify-receipt requires RECEIPT" >&2; exit 2; }
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_executable_baseline.py" \
      verify-receipt --receipt "$1"
    ;;
  *)
    echo "Usage: ./cloudbank-executable-baseline.sh [build|verify|verify-source SOURCE_ROOT|source-build SOURCE_ROOT OUTPUT SIGNER|oracle-runtime SOURCE_ROOT BUILD_RECEIPT IMAGE_ID_SHA256 OUTPUT SIGNER|verify-receipt RECEIPT]" >&2
    exit 2
    ;;
esac
