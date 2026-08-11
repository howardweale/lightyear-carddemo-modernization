#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"
cd "$project_dir"

action="${1:-build}"
if [[ "$action" == "build" ]]; then
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution build
elif [[ "$action" == "verify" ]]; then
  generated="$project_dir/work/hardened-execution-verify/conformance.receipt.json"
  mkdir -p "$(dirname "$generated")"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution build --output "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution validate --receipt "$generated"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution validate-evidence --receipt "$generated" >/dev/null
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution validate
  cmp "$project_dir/factory/execution/conformance.receipt.json" "$generated"
  echo "Hardened execution policy, OCI invocation, and conformance receipt are deterministic."
  echo "A live Docker or Podman probe is still required for production enforcement evidence."
elif [[ "$action" == "probe" ]]; then
  runtime="${2:-docker}"
  exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution probe --runtime "$runtime"
elif [[ "$action" == "admitted-run" ]]; then
  runtime="${2:-docker}"
  run_id="${3:-hardened-$(date -u +%Y%m%dT%H%M%SZ)}"
  : "${LIGHTYEAR_WORK_ORDER_SIGNING_KEY:?Set LIGHTYEAR_WORK_ORDER_SIGNING_KEY to at least 32 bytes}"
  : "${LIGHTYEAR_IDENTITY_SIGNING_KEY:?Set LIGHTYEAR_IDENTITY_SIGNING_KEY to at least 32 bytes}"
  evidence_dir="$project_dir/work/hardened-execution-runs/$run_id"
  signed_order="$evidence_dir/signed-work-order.json"
  factory_receipt="$project_dir/work/factory-runs/$run_id/receipt.json"
  mkdir -p "$evidence_dir"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution sign-work-order \
    --work-order "$project_dir/factory/work-orders/intcalc-repair.example.json" \
    --issuer operator:release \
    --key-id lightyear-release-operator \
    --output "$signed_order"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_factory run \
    --signed-work-order "$signed_order" \
    --source-root "$project_dir" \
    --runs-root "$project_dir/work/factory-runs" \
    --graph "$project_dir/knowledge/graph.snapshot.json.gz" \
    --provider local \
    --execution-runtime "$runtime" \
    --run-id "$run_id"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_execution validate-evidence \
    --receipt "$factory_receipt"
  "$LIGHTYEAR_PYTHON_BIN" -m lightyear_audit build \
    --execution-receipt "$factory_receipt" \
    --output "$evidence_dir/audit.snapshot.json.gz" \
    --dossier-json "$evidence_dir/release-dossier.json" \
    --dossier-markdown "$evidence_dir/release-dossier.md"
  echo "SIGNED_WORK_ORDER=$signed_order"
  echo "FACTORY_EXECUTION_RECEIPT=$factory_receipt"
  echo "LIVE_AUDIT_SNAPSHOT=$evidence_dir/audit.snapshot.json.gz"
  echo "LIVE_RELEASE_DOSSIER=$evidence_dir/release-dossier.json"
else
  echo "Usage: ./hardened-execution.sh [build|verify|probe [docker|podman]|admitted-run [docker|podman] [run-id]]" >&2
  exit 2
fi
