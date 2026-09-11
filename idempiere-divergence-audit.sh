#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
case "$action" in
  build|verify-source)
    source_root="${2:-}"
    if [[ -z "$source_root" ]]; then
      echo "Pinned iDempiere upstream checkout is required for $action." >&2
      exit 2
    fi
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/idempiere_divergence_audit.py" \
      "$action" --project-root "$project_dir" --source-root "$source_root"
    ;;
  verify)
    exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/idempiere_divergence_audit.py" \
      verify --project-root "$project_dir"
    ;;
  *)
    echo "Usage: ./idempiere-divergence-audit.sh [build|verify|verify-source] [IDEMPIERE_ROOT]" >&2
    exit 2
    ;;
esac
