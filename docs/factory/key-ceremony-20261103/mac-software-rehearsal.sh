#!/bin/bash
# Howard-operated dummy exercise only. Do not run from an agent or CI session.
set -eu
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
tools=/usr/local/lightyear/bin
fail() { printf 'REFUSED: %s\n' "$1" >&2; exit 1; }
mode=${1:-}
if [ "$mode" = ceremony-notes ]; then
  cat <<'LIGHTYEAR_CEREMONY_NOTES'
HUMAN CEREMONY NOTES (3 November 2026; display only)
The completed keys must not be reset or regenerated for this rehearsal.
Install ykman using the admin account; perform token setup only in the
dedicated standard ceremony account. Never pass PINs/PUKs in command flags.
Howard reported AES-192 management keys and this plugin refusal:
  custom unprotected non-TDES management keys are not supported
For new-key setup with that refusal, the human compatibility step BEFORE
age-plugin-yubikey was:
  ykman piv access change-management-key --algorithm TDES --generate --protect
This script DOES NOT execute that command or any hardware-key operation.
The plugin's FIRST prompt is the CURRENT PIN (factory default only on an
untouched key), NOT a new PIN. Next: current PUK. Then: ONE new value used
for BOTH PIN and PUK. Enter values only in the private local prompts.
Key A needed a PIV reset after a mis-entry BEFORE any key generation.
That historical reset is NOT a recovery instruction for established keys.
Stop after a mis-entry and diagnose locally; do not guess or loop retries.
Reported settings: lightyear-A / lightyear-B; PIN once; touch always.
Keep PINs, PUKs, serials, identity files and private material in that account.
Two individual decryptions and each key alone on shared ciphertext were
reported complete. Logout was reported; it is not in-window ownership proof.
PIN once must not be described as PIN always. Production custody assessment
must account for the actual policy without silently changing any gate.
For the software-only dummy exercise below, keep all YubiKeys UNPLUGGED.
LIGHTYEAR_CEREMONY_NOTES
  exit 0
fi
if [ "$mode" = verify-logout ]; then
  [ "$(id -u)" = 0 ] || fail 'admin phase requires sudo'
  uid=${2:-}; record=${3:-}
  case "$uid" in ''|*[!0-9]*) fail 'numeric ceremony UID required';; esac
  [ "$uid" -ge 501 ] || fail 'ordinary ceremony UID required'
  case "$record" in /private/tmp/lightyear-software-rehearsal.*) ;; *) fail 'receipt directory';; esac
  [ -d "$record" ] && [ ! -L "$record" ] || fail 'receipt directory missing or linked'
  [ "$(stat -f %u "$record")" = "$uid" ] || fail 'receipt owner mismatch'
  [ -f "$record/roundtrip.txt" ] && [ ! -L "$record/roundtrip.txt" ] || fail 'roundtrip receipt missing'
  grep -qx 'Roundtrip=PASS' "$record/roundtrip.txt" || fail 'successful roundtrip not recorded'
  [ ! -e "$record/identity.txt" ] || fail 'exercise did not finish key cleanup'
  printf 'Check ceremony UID %s after actual logout, not fast switching.\n' "$uid"
  for observation in 1 2; do
    if pgrep -u "$uid" >/dev/null; then
      ps -axo uid,pid,ppid,comm | awk -v u="$uid" '$1==u'
      fail 'processes remain under ceremony UID'
    else
      code=$?; [ "$code" = 1 ] || fail 'process enumeration failed'
    fi
    printf 'Observation %s: no UID processes at %s\n' "$observation" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    [ "$observation" = 2 ] || sleep 5
  done
  # Print for Howard to record; never write as root into the user's directory.
  shasum -a 256 "$record/roundtrip.txt"
  printf 'PASS: two post-logout observations; not in-window ownership proof.\n'
  exit 0
fi
[ "$mode" = exercise ] || fail 'usage: ceremony-notes | exercise | verify-logout UID DIRECTORY'
[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || fail 'native arm64 macOS required'
[ "$(id -u)" -ge 501 ] || fail 'use non-root ceremony account'
printf 'Keep all YubiKeys unplugged. Type DUMMY to proceed with software keys only: '
read -r confirmation
[ "$confirmation" = DUMMY ] || fail 'not confirmed'
for entry in /usr/local/lightyear "$tools" "$tools/age" "$tools/age-keygen" "$tools/age-plugin-yubikey"; do
  [ -e "$entry" ] && [ ! -L "$entry" ] || fail 'missing or linked installed path'
  [ "$(stat -f %u "$entry")" = 0 ] || fail 'tools must be root-owned'
  permissions=$(stat -f %Lp "$entry")
  [ $((8#$permissions & 0022)) = 0 ] || fail 'group/other-writable tool path'
  [ ! -w "$entry" ] || fail 'ceremony account can write tool path'
done
for name in age age-keygen age-plugin-yubikey; do
  file "$tools/$name" | grep -q arm64 || fail 'tool lacks arm64 code'
done
[ "$("$tools/age" --version)" = v1.3.2 ] || fail 'age version mismatch'
[ "$("$tools/age-keygen" --version)" = v1.3.2 ] || fail 'age-keygen version mismatch'
"$tools/age-plugin-yubikey" --version | grep -Eq '(^| )0\.5\.1$' || fail 'plugin version mismatch'
record=$(mktemp -d /private/tmp/lightyear-software-rehearsal.XXXXXX)
cleanup() {
  # Exact files in the directory created above; no recursive removal or glob.
  rm -f "$record/identity.txt" "$record/dummy.txt" "$record/dummy.age" "$record/restored.txt"
}
trap cleanup EXIT
{
  printf 'Software-key rehearsal only\nUID=%s\nStart=%s\n' "$(id -u)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sw_vers
  shasum -a 256 "$tools/age" "$tools/age-keygen" "$tools/age-plugin-yubikey"
} > "$record/roundtrip.txt"
"$tools/age-keygen" -o "$record/identity.txt" 2>/dev/null
recipient=$("$tools/age-keygen" -y "$record/identity.txt")
printf 'LIGHTYEAR disposable software-key rehearsal. No production data.\n' > "$record/dummy.txt"
"$tools/age" -r "$recipient" -o "$record/dummy.age" "$record/dummy.txt"
"$tools/age" -d -i "$record/identity.txt" -o "$record/restored.txt" "$record/dummy.age"
cmp -s "$record/dummy.txt" "$record/restored.txt" || fail 'roundtrip differs'
{
  shasum -a 256 "$record/dummy.txt" "$record/dummy.age" "$record/restored.txt"
  printf 'Roundtrip=PASS\nEnd=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$record/roundtrip.txt"
cleanup
printf 'Roundtrip PASS. Ceremony UID: %s\nReceipt directory: %s\n' "$(id -u)" "$record"
printf 'Now LOG OUT via Apple menu. Verify from the admin account before logging back in.\n'

