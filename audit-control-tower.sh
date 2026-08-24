#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
cd "$project_dir"

action="${1:-build}"
if [[ "$action" == "build" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_audit build
elif [[ "$action" == "verify" ]]; then
  verification_dir="$project_dir/work/audit-control-tower-verify"
  generated="$verification_dir/audit.snapshot.json.gz"
  generated_json="$verification_dir/carddemo-intcalc-v0.19-demo.json"
  generated_markdown="$verification_dir/carddemo-intcalc-v0.19-demo.md"
  mkdir -p "$verification_dir"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_audit build \
    --output "$generated" \
    --dossier-json "$generated_json" \
    --dossier-markdown "$generated_markdown"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_audit validate --snapshot "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_audit validate
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_audit compare \
    --expected "$project_dir/audit/audit.snapshot.json.gz" \
    --actual "$generated"
  cmp "$project_dir/audit/dossiers/carddemo-intcalc-v0.19-demo.json" "$generated_json"
  cmp "$project_dir/audit/dossiers/carddemo-intcalc-v0.19-demo.md" "$generated_markdown"
  echo "Audit ledger, checkpoint, projections, policy decisions, and dossier are deterministic and valid."
else
  echo "Usage: ./audit-control-tower.sh [build|verify]" >&2
  exit 2
fi
