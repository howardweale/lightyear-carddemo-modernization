#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
unset PYTHONHOME PYTHONPATH
exec runtime/python/bin/python3 -I run.py "$@"
