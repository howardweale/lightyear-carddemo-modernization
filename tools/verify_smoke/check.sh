#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || exit 1
cd /opt/lightyear-verify
aa-status --enabled
# Confirm a loaded bwrap policy, not merely an active AppArmor LSM.
aa-status --json | python3 -I -c 'import json,sys; p=json.load(sys.stdin)["profiles"]; assert any("bwrap" in n for n in p), "bwrap AppArmor profile not loaded"'
runuser -u lyjudge -- bwrap --unshare-all --ro-bind / / --proc /proc --dev /dev /usr/bin/true
test -d /var/lib/lightyear-verify/evaluation
test -f /opt/lightyear-verify/src/lightyear_judge/service.py
# Before init, absence of the key is explicit; start.sh repeats this after creation.
runuser -u lyagent -- test ! -r /var/lib/lightyear-verify/session/authority.pem
runuser -u lyagent -- test ! -r /var/lib/lightyear-verify/evaluation
runuser -u lyagent -- test ! -w /opt/lightyear-verify/src/lightyear_judge/service.py
runuser -u lyjudge -- /opt/lightyear-verify-venv/bin/python -I -c \
  'import pwd; from lightyear_judge.sandbox import require_trusted_installation; require_trusted_installation(pwd.getpwnam("lyagent").pw_uid)'
echo 'PASS: AppArmor active, bwrap namespaces, key/evaluation/install separation and trusted installation.'
