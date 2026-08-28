#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-verify}"
legacy_root="${2:-${CARDDEMO_UPSTREAM_ROOT:-$project_dir/../carddemo-upstream}}"

case "$action" in
  build)
    rm -f \
      "$project_dir/data-modernization/rehearsal/plan.json" \
      "$project_dir/data-modernization/rehearsal/cutover.approval.json" \
      "$project_dir/data-modernization/rehearsal/checkpoint.json" \
      "$project_dir/data-modernization/rehearsal/receipt.json"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data rehearse-offline \
      --project-root "$project_dir" --output-root "$project_dir"
    ;;
  verify)
    output="$project_dir/work/migration-rehearsal-verify"
    rm -rf "$output"
    mkdir -p "$output"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data build \
      --legacy-root "$legacy_root" --output-root "$output" >/dev/null
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data rehearse-offline \
      --project-root "$output" --output-root "$output" >/dev/null
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_data validate-rehearsal \
      --project-root "$output"
    for relative in plan.json cutover.approval.json checkpoint.json receipt.json; do
      cmp \
        "$project_dir/data-modernization/rehearsal/$relative" \
        "$output/data-modernization/rehearsal/$relative"
    done
    "$LIGHTYEAR_PYTHON_BIN" -m unittest tests.test_migration_rehearsal -v
    echo "AUTHFRDS offline CDC, resume, dual-target reconciliation, cutover, and rollback rehearsal is deterministic."
    ;;
  *)
    echo "Usage: ./migration-rehearsal.sh [build|verify] [optional-carddemo-upstream-root]" >&2
    exit 2
    ;;
esac
