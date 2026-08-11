#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="$project_dir/work/factory-benchmark-$stamp"

source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
cd "$project_dir"

"$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory benchmark \
  --project-root "$project_dir" \
  --output-root "$output_dir" \
  "$@"

echo "Factory benchmark artifacts: $output_dir"
