#!/bin/bash
# Offline, account-local setup. No device discovery or signing.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
test "$(uname -s)" = Darwin
test "$(id -u)" != 0
case " $(id -G) " in *" 80 "*) echo "STOP: use the standard ceremony account."; exit 1;; esac
case "$(uname -m)" in arm64) arch=arm64;; x86_64) arch=x86_64;; *) exit 1;; esac
if test "$(sysctl -in sysctl.proc_translated 2>/dev/null || true)" = 1; then
  echo "STOP: reopen Terminal without Rosetta."; exit 1
fi
echo "Keep ALL keys unplugged. Setup never opens a device."
read -r -p "Type UNPLUGGED to continue: " answer
test "$answer" = UNPLUGGED
shasum -a 256 -c SHA256SUMS
test ! -e runtime
test ! -e site
mkdir -m 700 runtime site
tar -xzf "$arch/python.tar.gz" -C runtime
unset PYTHONHOME PYTHONPATH
runtime/python/bin/python3 -I -m pip --isolated install \
  --no-index --no-deps --only-binary=:all: --require-hashes \
  --find-links "$arch" --target site -r "$arch/requirements.txt"
runtime/python/bin/python3 -I check.py
echo "Setup finished. Keep keys unplugged until a separate attended signing session."
