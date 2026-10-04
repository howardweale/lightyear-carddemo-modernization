#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
exec 9>/run/lock/lightyear-verify-smoke.lock
flock -n 9 || exit 1
systemctl stop lightyear-verify-smoke.service
echo 'Judge stopped. Session, receipts, keys, logs and cumulative ledger preserved.'
