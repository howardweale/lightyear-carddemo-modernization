#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
if [[ "$action" == "build" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.cobol build --project-root "$project_dir"
elif [[ "$action" == "verify" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.cobol verify --project-root "$project_dir"
else
  echo "Usage: ./cobol-qualification.sh [build|verify]" >&2
  exit 2
fi
