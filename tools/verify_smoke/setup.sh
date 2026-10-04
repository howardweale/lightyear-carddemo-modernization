#!/usr/bin/env bash
# Run ONLY inside a dedicated Ubuntu 24.04 VM, as its administrator.
set -euo pipefail
umask 022
[[ $EUID == 0 ]] || { echo 'Run with sudo inside the VM.' >&2; exit 1; }
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || { echo 'Ubuntu 24.04 required.' >&2; exit 1; }
case "$(uname -m)" in aarch64|x86_64) ;; *) echo 'Unsupported CPU architecture.' >&2; exit 1;; esac
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd "$kit/../.." && pwd)
exec 9>/run/lock/lightyear-verify-smoke.lock
flock -n 9 || { echo 'Another smoke-kit operation is active.' >&2; exit 1; }
# Completed reruns only verify. Never upgrade a sealed task's runtime or reset budgets.
if [[ -f /var/lib/lightyear-verify-smoke/setup.json ]]; then
  python3 -I "$kit/provision.py" verify "$repo"
  bash /opt/lightyear-verify/tools/verify_smoke/check.sh
  exit
fi
if [[ -e /var/lib/lightyear-verify/session ]]; then
  echo 'Existing session without completed kit setup; refusing to modify it.' >&2; exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y apparmor apparmor-profiles bubblewrap acl openjdk-21-jdk-headless \
  python3-venv python3-pip maven git curl ca-certificates jq util-linux
for account in lyjudge lyagent; do
  if ! id "$account" >/dev/null 2>&1; then
    useradd --create-home --user-group --shell /bin/bash "$account"
    passwd -l "$account"
  fi
done
# This profile, not a global sysctl or an unconfined replacement, enables bwrap.
if [[ ! -f /etc/apparmor.d/bwrap-userns-restrict ]]; then
  install -o root -g root -m 0644 /usr/share/apparmor/extra-profiles/bwrap-userns-restrict \
    /etc/apparmor.d/bwrap-userns-restrict
fi
apparmor_parser -r /etc/apparmor.d/bwrap-userns-restrict
aa-status --enabled
python3 -I "$kit/provision.py" install "$repo"
python3 -m venv /opt/lightyear-verify-venv
/opt/lightyear-verify-venv/bin/pip install -e '/opt/lightyear-verify[verify]'
chown -R root:root /opt/lightyear-verify /opt/lightyear-verify-venv
chmod -R go-w /opt/lightyear-verify /opt/lightyear-verify-venv
cd /srv/dev
runuser -u lyagent -- env -i HOME=/home/lyagent PATH=/usr/bin:/bin LANG=C.UTF-8 \
  mvn -B -f /srv/dev/candidate-java/pom.xml package
runuser -u lyagent -- env -i HOME=/home/lyagent PATH=/usr/bin:/bin LANG=C.UTF-8 \
  python3 -I /opt/lightyear-verify/tools/verify_smoke/build_candidates.py /srv/dev
bash /opt/lightyear-verify/tools/verify_smoke/check.sh
python3 -I "$kit/provision.py" finish "$repo"
echo 'Setup complete: zero model calls. Next: sudo bash /opt/lightyear-verify/tools/verify_smoke/start.sh'
