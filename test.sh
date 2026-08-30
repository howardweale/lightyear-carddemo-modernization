#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

if [[ "${1:-complete}" == "unit-only" ]]; then
  export LIGHTYEAR_ALLOW_MISSING_UPSTREAM=1
  echo "INCOMPLETE: upstream-backed integration tests may be skipped." >&2
else
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_common prerequisites --project-root "$project_dir"
fi
exec "$LIGHTYEAR_PYTHON_BIN" -m unittest discover -s "$project_dir/tests" -v
