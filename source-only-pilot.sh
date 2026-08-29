#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/python-runtime.sh"
lightyear_resolve_python
export PYTHONPATH="$project_dir/src"

action="${1:-doctor}"
case "$action" in
  doctor|verify|compatibility)
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_pilot --project-root "$project_dir" "$action"
    ;;
  rehearse)
    output="${2:-$project_dir/work/source-only-pilot}"
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_pilot --project-root "$project_dir" rehearse \
      --output-root "$output"
    ;;
  intake)
    source_root="${2:?Usage: ./source-only-pilot.sh intake SOURCE APPROVAL-ID OUTPUT}"
    approval_id="${3:?Usage: ./source-only-pilot.sh intake SOURCE APPROVAL-ID OUTPUT}"
    output="${4:?Usage: ./source-only-pilot.sh intake SOURCE APPROVAL-ID OUTPUT}"
    mkdir -p "$output"
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_pilot --project-root "$project_dir" intake \
      --source-root "$source_root" --approval-id "$approval_id" \
      --source-label "Approved customer source-only intake" --output "$output/intake.manifest.json"
    ;;
  preflight)
    output="${2:?Usage: ./source-only-pilot.sh preflight OUTPUT}"
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_pilot --project-root "$project_dir" preflight \
      --intake "$output/intake.manifest.json" --output "$output/mainframe.preflight.json"
    ;;
  dossier)
    output="${2:?Usage: ./source-only-pilot.sh dossier OUTPUT}"
    exec "$LIGHTYEAR_PYTHON_BIN" -m lightyear_pilot --project-root "$project_dir" dossier \
      --intake "$output/intake.manifest.json" --preflight "$output/mainframe.preflight.json" \
      --output-json "$output/pilot.dossier.json" --output-md "$output/pilot.dossier.md"
    ;;
  *)
    echo "Usage: ./source-only-pilot.sh [doctor|verify|compatibility|rehearse|intake|preflight|dossier]" >&2
    exit 2
    ;;
esac
