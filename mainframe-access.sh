#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/extensions/runtime:$project_dir/src"

action="${1:-verify}"
profile="$project_dir/extensions/adapters/mainframe-access.profile.json"
graph="$project_dir/knowledge/graph.snapshot.json.gz"

case "$action" in
  verify)
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions campaign-validate \
      --profile "$profile" --graph "$graph" \
      --capture-root "$project_dir/extensions/adapters/campaign"
    ;;
  simulate)
    output="${2:-$project_dir/work/mainframe-access-simulated}"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions campaign-fixture \
      --profile "$profile" --graph "$graph" \
      --responses "$project_dir/extensions/adapters/fixtures/mainframe-access.simulated.responses.json" \
      --output-root "$output"
    ;;
  live)
    base_url="${2:?Usage: ./mainframe-access.sh live HTTPS-BASE-URL KEY-ID [OUTPUT]}"
    key_id="${3:?Usage: ./mainframe-access.sh live HTTPS-BASE-URL KEY-ID [OUTPUT]}"
    output="${4:-$project_dir/work/mainframe-access-live}"
    : "${LIGHTYEAR_MAINFRAME_BEARER:?Set LIGHTYEAR_MAINFRAME_BEARER}"
    : "${LIGHTYEAR_EXTENSION_EVIDENCE_KEY:?Set LIGHTYEAR_EXTENSION_EVIDENCE_KEY}"
    "$LIGHTYEAR_PYTHON_BIN" -m lightyear_extensions campaign-live \
      --profile "$profile" --graph "$graph" --base-url "$base_url" \
      --key-id "$key_id" --output-root "$output"
    ;;
  *)
    echo "Usage: ./mainframe-access.sh [verify|simulate [output]|live HTTPS-BASE-URL KEY-ID [output]]" >&2
    exit 2
    ;;
esac
