#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-}"
shift || true
case "$action" in
  sign)
    catalog="${1:-}"
    envelope="${2:-}"
    issuer="${3:-external-evaluation-controller}"
    [[ -n "$catalog" && -n "$envelope" ]] || {
      echo "Usage: ./quality-gate.sh sign <catalog.json> <envelope.json> [issuer]" >&2
      exit 2
    }
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory sign-eval-catalog \
      --catalog "$catalog" --output "$envelope" --issuer "$issuer"
    ;;
  validate)
    envelope="${1:-}"
    [[ -n "$envelope" ]] || {
      echo "Usage: ./quality-gate.sh validate <envelope.json>" >&2
      exit 2
    }
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory validate-sealed-eval \
      --envelope "$envelope"
    ;;
  evaluate)
    envelope="${1:-}"
    output="${2:-$project_dir/work/sealed-evaluation-$(date -u +%Y%m%dT%H%M%SZ)}"
    [[ -n "$envelope" ]] || {
      echo "Usage: ./quality-gate.sh evaluate <envelope.json> [output]" >&2
      exit 2
    }
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory evaluate \
      --project-root "$project_dir" --sealed-envelope "$envelope" \
      --output-root "$output" --provider openai
    echo "SEALED_EVALUATION=$output"
    ;;
  compare)
    [[ "$#" -ge 2 ]] || {
      echo "Usage: ./quality-gate.sh compare <receipt.json> <receipt.json> [...]" >&2
      exit 2
    }
    command=("$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory compare-evals)
    for receipt in "$@"; do command+=(--receipt "$receipt"); done
    "${command[@]}"
    ;;
  *)
    echo "Usage: ./quality-gate.sh [sign|validate|evaluate|compare] ..." >&2
    exit 2
    ;;
esac
