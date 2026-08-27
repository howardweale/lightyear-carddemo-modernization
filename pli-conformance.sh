#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/extensions/runtime:$project_dir/src"

action="${1:-verify}"
canonical="$project_dir/extensions/pli/conformance"
generated="$project_dir/work/pli-conformance-$action"

build_outputs() {
  local output_root="$1"
  rm -rf "$output_root"
  mkdir -p "$output_root"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions build-pli-conformance \
    --graph "$project_dir/knowledge/graph.snapshot.json.gz" \
    --corpus-root "$canonical/corpus" \
    --manifest "$canonical/corpus/manifest.json" \
    --support-matrix "$canonical/support-matrix.json" \
    --repository-root "$project_dir" \
    --golden-output "$output_root/golden-results.json" \
    --receipt "$output_root/coverage.receipt.json"
}

case "$action" in
  build)
    build_outputs "$generated"
    cp "$generated/golden-results.json" "$canonical/golden-results.json"
    cp "$generated/coverage.receipt.json" "$canonical/coverage.receipt.json"
    ;;
  verify)
    build_outputs "$generated"
    "$LIGHTYEAR_PYTHON_BIN" -m unittest extensions.tests.test_pli_conformance -v
    cmp "$canonical/golden-results.json" "$generated/golden-results.json"
    cmp "$canonical/coverage.receipt.json" "$generated/coverage.receipt.json"
    ;;
  *)
    echo "Usage: ./pli-conformance.sh [build|verify]" >&2
    exit 2
    ;;
esac

"$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions validate-pli-conformance \
  --graph "$project_dir/knowledge/graph.snapshot.json.gz" \
  --golden "$canonical/golden-results.json" \
  --receipt "$canonical/coverage.receipt.json"
echo "PL/I supported-subset coverage is deterministic and explicit; compiler and runtime equivalence remain blocked."
