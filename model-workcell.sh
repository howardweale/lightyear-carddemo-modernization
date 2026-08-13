#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-validate}"
default_catalog="$project_dir/factory/evals/carddemo-v0.12-public.json"
catalog="${2:-$default_catalog}"

if [[ "$action" == "validate" ]]; then
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory validate-eval \
    --project-root "$project_dir" \
    --catalog "$catalog"
elif [[ "$action" == "evaluate" ]]; then
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "OPENAI_API_KEY is required for a live model evaluation" >&2
    exit 2
  fi
  if [[ -z "${LIGHTYEAR_MODEL_INPUT_USD_PER_MILLION:-}" || \
        -z "${LIGHTYEAR_MODEL_OUTPUT_USD_PER_MILLION:-}" ]]; then
    echo "Model input/output prices are required so the evaluation cost budget can be enforced" >&2
    exit 2
  fi
  output="${3:-$project_dir/work/model-evaluation-$(date -u +%Y%m%dT%H%M%SZ)}"
  if "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory evaluate \
      --project-root "$project_dir" \
      --catalog "$catalog" \
      --output-root "$output" \
      --provider openai; then
    evaluation_code=0
  else
    evaluation_code=$?
  fi
  echo "MODEL_EVALUATION=$output"
  exit "$evaluation_code"
elif [[ "$action" == "resume" ]]; then
  output="${2:-}"
  catalog="${3:-$default_catalog}"
  if [[ -z "$output" ]]; then
    echo "Usage: ./model-workcell.sh resume <evaluation-output> [catalog.json]" >&2
    exit 2
  fi
  if [[ -z "${OPENAI_API_KEY:-}" || \
        -z "${LIGHTYEAR_MODEL_INPUT_USD_PER_MILLION:-}" || \
        -z "${LIGHTYEAR_MODEL_OUTPUT_USD_PER_MILLION:-}" ]]; then
    echo "OPENAI_API_KEY and model input/output prices are required to resume" >&2
    exit 2
  fi
  if "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory evaluate \
      --project-root "$project_dir" \
      --catalog "$catalog" \
      --output-root "$output" \
      --provider openai \
      --resume; then
    evaluation_code=0
  else
    evaluation_code=$?
  fi
  echo "MODEL_EVALUATION=$output"
  exit "$evaluation_code"
else
  echo "Usage: ./model-workcell.sh [validate|evaluate] [catalog.json] [output]" >&2
  echo "       ./model-workcell.sh resume <evaluation-output> [catalog.json]" >&2
  exit 2
fi
