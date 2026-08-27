#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src:$project_dir/extensions/runtime"

action="${1:-verify}"

case "$action" in
  verify)
    for catalog in \
      intcalc-v0.26-public.json \
      posttran-v0.26-public.json \
      creastmt-v0.26-public.json \
      acctpl1-v0.26-public.json; do
      "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory validate-eval \
        --project-root "$project_dir" \
        --catalog "$project_dir/factory/evals/$catalog" >/dev/null
    done
    "$LIGHTYEAR_PYTHON_BIN" -m unittest tests.test_multi_workload_qualification
    ;;
  qualify)
    shift
    plan="${1:-}"
    portfolio_run="${2:-}"
    output="${3:-}"
    if [[ -z "$plan" || -z "$portfolio_run" || -z "$output" ]]; then
      echo "Usage: ./factory-qualification.sh qualify <plan.json> <portfolio-run.json> <output.json> <evaluation.receipt.json>..." >&2
      exit 2
    fi
    shift 3
    if [[ "$#" -lt 8 ]]; then
      echo "Qualification requires at least eight receipts: two sealed runs for each of four workloads" >&2
      exit 2
    fi
    receipt_args=()
    for receipt in "$@"; do
      receipt_args+=(--evaluation-receipt "$receipt")
    done
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory qualify \
      --manifest "$project_dir/factory/qualification/manifest.json" \
      --portfolio-plan "$plan" \
      --portfolio-run "$portfolio_run" \
      --output "$output" \
      "${receipt_args[@]}"
    ;;
  *)
    echo "Usage: ./factory-qualification.sh [verify|qualify]" >&2
    exit 2
    ;;
esac
