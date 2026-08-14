#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/python-runtime.sh"
lightyear_resolve_python
PYTHON="${PYTHON:-$LIGHTYEAR_PYTHON_BIN}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

command="${1:-status}"
shift || true
database="${LIGHTYEAR_DURABLE_DATABASE:-$ROOT/work/durable/control.sqlite3}"

case "$command" in
  init|status|recover|validate)
    exec "$PYTHON" -m lightyear_factory "durable-$command" --database "$database" "$@"
    ;;
  submit|lease|start|heartbeat|complete|fail)
    exec "$PYTHON" -m lightyear_factory "durable-$command" --database "$database" "$@"
    ;;
  conformance)
    exec "$PYTHON" -m lightyear_factory durable-conformance --project-root "$ROOT" "$@"
    ;;
  verify)
    "$PYTHON" -m unittest tests.test_durable_factory -v
    temp_root="$(mktemp -d "${TMPDIR:-/tmp}/lightyear-durable.XXXXXX")"
    trap 'rm -rf "$temp_root"' EXIT
    "$PYTHON" -m lightyear_factory durable-init --database "$temp_root/control.sqlite3" >/dev/null
    "$PYTHON" -m lightyear_factory durable-validate --database "$temp_root/control.sqlite3"
    "$PYTHON" -m lightyear_factory durable-conformance --project-root "$ROOT" \
      --output "$temp_root/conformance.receipt.json" >/dev/null
    cmp "$ROOT/factory/durable/conformance.receipt.json" "$temp_root/conformance.receipt.json"
    ;;
  *)
    echo "Usage: ./durable-factory.sh [init|submit|lease|start|heartbeat|complete|fail|recover|status|validate|conformance|verify] [options]" >&2
    exit 2
    ;;
esac
