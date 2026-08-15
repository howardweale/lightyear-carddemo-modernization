#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
cd "$project_dir"

action="${1:-serve}"
shift || true
case "$action" in
  serve)
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph serve "$@"
    ;;
  validate)
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_control_tower validate "$@"
    ;;
  events)
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_control_tower events "$@"
    ;;
  verify)
    "$LIGHTYEAR_PYTHON_BIN" -m unittest tests.test_live_control_tower -v
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_control_tower validate \
      --database "$project_dir/work/control-tower/events.sqlite3"
    ;;
  *)
    echo "Usage: ./live-control-tower.sh [serve|validate|events|verify]" >&2
    exit 2
    ;;
esac
