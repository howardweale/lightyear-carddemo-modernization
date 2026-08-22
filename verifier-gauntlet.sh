#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

"$LIGHTYEAR_PYTHON_BIN" -m unittest \
  tests.test_comparator_escape \
  tests.test_trust_boundaries \
  -v

"$LIGHTYEAR_PYTHON_BIN" -m carddemo_oracle validate-normalizations \
  --ledger "$project_dir/spec/comparison-normalizations.json"
