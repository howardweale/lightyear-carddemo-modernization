#!/usr/bin/env bash
# APT may exhaust per-file retries during a transient snapshot index outage.
# Retry the complete refresh, never accepting partial or unverified indexes.
set -euo pipefail
export LC_ALL=C
for attempt in 1 2 3; do
  if apt-get -o APT::Update::Error-Mode=any update; then
    exit 0
  else
    status=$?
  fi
  if [[ $attempt == 3 ]]; then
    echo "Snapshot index refresh failed after $attempt attempts (exit $status)." >&2
    exit "$status"
  fi
  delay=$((attempt * 10))
  echo "Snapshot index refresh failed (exit $status); retrying in ${delay}s." >&2
  sleep "$delay"
done
