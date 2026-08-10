#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$project_dir/src"
cd "$project_dir"
exec python3 -m lightyear_knowledge_graph serve "$@"
