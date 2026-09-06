#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
exec "$LIGHTYEAR_PYTHON_BIN" "$project_dir/tools/cloudbank_sql_ha.py" "$@"
