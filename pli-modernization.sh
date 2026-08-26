#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/extensions/runtime:$project_dir/src"

action="${1:-verify}"
canonical="$project_dir/extensions/pli/modernization"
generated="$project_dir/work/pli-modernization-$action"

build_outputs() {
  local output_root="$1"
  rm -rf "$output_root"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions build-pli-proof \
    --project-root "$project_dir" \
    --graph "$project_dir/knowledge/graph.snapshot.json.gz" \
    --fragment "$project_dir/extensions/pli/pli.fragment.json" \
    --output-root "$output_root"
}

case "$action" in
  build)
    build_outputs "$generated"
    mkdir -p "$canonical"
    cp "$generated/"*.json "$canonical/"
    ;;
  verify)
    build_outputs "$generated"
    "$LIGHTYEAR_PYTHON_BIN" -m unittest extensions.tests.test_pli_modernization -v
    for expected in "$canonical/"*.json; do
      cmp "$expected" "$generated/$(basename "$expected")"
    done
    ;;
  *)
    echo "Usage: ./pli-modernization.sh [build|verify]" >&2
    exit 2
    ;;
esac

"$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions validate-pli-proof \
  --project-root "$project_dir" \
  --graph "$project_dir/knowledge/graph.snapshot.json.gz" \
  --fragment "$project_dir/extensions/pli/pli.fragment.json" \
  --receipt "$canonical/development.receipt.json"
echo "Mixed PL/I, COBOL-call, and Db2 development proof is deterministic; live z/OS equivalence remains blocked."
