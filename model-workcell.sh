#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-validate}"
catalog="${2:-$project_dir/factory/evals/carddemo-v0.12-public.json}"

if [[ "$action" == "validate" ]]; then
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory validate-eval \
    --project-root "$project_dir" \
    --catalog "$catalog"
elif [[ "$action" == "evaluate" ]]; then
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "OPENAI_API_KEY is required for a live model evaluation" >&2
    exit 2
  fi
  output="$project_dir/work/model-evaluation-$(date -u +%Y%m%dT%H%M%SZ)"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory evaluate \
    --project-root "$project_dir" \
    --catalog "$catalog" \
    --output-root "$output" \
    --provider openai
  echo "MODEL_EVALUATION=$output"
else
  echo "Usage: ./model-workcell.sh [validate|evaluate] [catalog.json]" >&2
  exit 2
fi
