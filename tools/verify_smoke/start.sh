#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
exec 9>/run/lock/lightyear-verify-smoke.lock
flock -n 9 || exit 1
cd /opt/lightyear-verify
python3 -I /opt/lightyear-verify/tools/verify_smoke/provision.py verify
bash /opt/lightyear-verify/tools/verify_smoke/check.sh
if [[ ! -e /var/lib/lightyear-verify/session ]]; then
  runuser -u lyjudge -- env -i HOME=/home/lyjudge PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 /opt/lightyear-verify-venv/bin/lightyear-judge init \
    --data-root /var/lib/lightyear-verify/session --config /var/lib/lightyear-verify/config.json
fi
# A partially initialized session is not deleted or initialized again.
test -s /var/lib/lightyear-verify/session/task.json
test -s /var/lib/lightyear-verify/session/token
test -s /var/lib/lightyear-verify/session/authority.pem
bash /opt/lightyear-verify/tools/verify_smoke/check.sh
systemctl daemon-reload
systemctl start lightyear-verify-smoke.service
# Authenticated readiness probe executes only as lyagent. Token never appears in argv.
python3 -I /opt/lightyear-verify/tools/verify_smoke/agent.py \
  /opt/lightyear-verify-venv/bin/python -I /opt/lightyear-verify/tools/verify_smoke/ready.py
echo 'Judge ready on 127.0.0.1:8770. Budgets and keys preserved.'
echo 'Agent shell: sudo python3 -I /opt/lightyear-verify/tools/verify_smoke/agent.py'
