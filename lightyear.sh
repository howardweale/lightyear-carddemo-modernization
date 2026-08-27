#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
action="${1:-doctor}"

case "$action" in
  doctor)
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph doctor --project-root "$project_dir"
    ;;
  demo)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph doctor --project-root "$project_dir"
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_knowledge_graph demo --project-root "$project_dir"
    ;;
  explorer)
    shift
    exec "$project_dir/graph-explorer.sh" "$@"
    ;;
  verify)
    "$project_dir/knowledge-graph.sh" verify
    "$project_dir/extension-foundation.sh" verify
    "$project_dir/pli-conformance.sh" verify
    "$project_dir/pli-modernization.sh" verify
    "$project_dir/pli-build-attestation.sh" verify
    "$project_dir/composite-estate.sh" verify
    "$LIGHTYEAR_PYTHON_BIN" -m unittest tests.test_semantic_inputs tests.test_composite_estate
    ;;
  *)
    echo "Usage: ./lightyear.sh [doctor|demo|explorer|verify]" >&2
    exit 2
    ;;
esac
