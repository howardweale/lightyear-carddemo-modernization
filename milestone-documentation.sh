#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-verify}"
case "$command_name" in
  build|verify) ;;
  *)
    echo "usage: ./milestone-documentation.sh [build|verify]" >&2
    exit 2
    ;;
esac

python3 tools/generate_milestone_documentation.py "$command_name"
