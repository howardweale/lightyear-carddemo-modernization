#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

command="${1:-plan}"
manifest="${2:-$project_dir/factory/portfolio/carddemo-portfolio.json}"
plan="${3:-$project_dir/work/portfolio/carddemo-plan.json}"

case "$command" in
  plan)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory portfolio-plan \
      --project-root "$project_dir" --manifest "$manifest" --output "$plan"
    ;;
  sign)
    : "${LIGHTYEAR_PORTFOLIO_APPROVAL_KEY:?Set LIGHTYEAR_PORTFOLIO_APPROVAL_KEY first}"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory portfolio-sign \
      --plan "$plan" --output "${4:-$project_dir/work/portfolio/human-approval.json}" \
      --approver "${LIGHTYEAR_PORTFOLIO_APPROVER:-local-human-operator}"
    ;;
  run|resume)
    : "${LIGHTYEAR_PORTFOLIO_APPROVAL_KEY:?Set LIGHTYEAR_PORTFOLIO_APPROVAL_KEY first}"
    resume_args=()
    if [[ "$command" == "resume" ]]; then
      resume_args+=(--resume)
    fi
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory portfolio-run \
      --project-root "$project_dir" --manifest "$manifest" --plan "$plan" \
      --approval "${4:-$project_dir/work/portfolio/human-approval.json}" \
      --output-root "${5:-$project_dir/work/portfolio/carddemo-run}" \
      "${resume_args[@]}"
    ;;
  verify)
    output="$project_dir/work/portfolio-verify/carddemo-plan.json"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory portfolio-plan \
      --project-root "$project_dir" --manifest "$manifest" --output "$output" >/dev/null
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory portfolio-validate --plan "$output"
    ;;
  *)
    echo "Usage: ./portfolio-factory.sh [plan|sign|run|resume|verify] [manifest] [plan] [approval] [output]" >&2
    exit 2
    ;;
esac
