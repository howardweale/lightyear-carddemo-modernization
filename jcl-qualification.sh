#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
if [[ "$action" == "build" || "$action" == "verify" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_readiness.jcl "$action" --project-root "$project_dir"
fi
echo "Usage: ./jcl-qualification.sh [build|verify]" >&2
exit 2
