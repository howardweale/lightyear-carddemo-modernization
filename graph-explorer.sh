#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
cd "$project_dir"
exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph serve "$@"
