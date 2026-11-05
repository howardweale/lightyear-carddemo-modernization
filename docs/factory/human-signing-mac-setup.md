# Offline Mac setup for the human signing command

Planned account-local setup for DarkFactory: no administrator rights, network,
Homebrew, Xcode, existing Python changes or key/credential/management-key changes.
Not yet exercised on the Mac; setup and signing interoperability remain pending.
The USB bundle includes Python 3.12.16 for Apple Silicon and Intel, cryptography
46.0.3, yubikey-manager 5.9.2 and pinned binary dependencies.
Upstream runtime: [Astral portable Python](https://github.com/astral-sh/python-build-standalone/releases/tag/20261026).
Dependency filenames, source URLs and SHA-256 values are in DEPENDENCIES.json.
The bundle receipt supplies the exact source commit and outer archive SHA-256.

Keep every key unplugged. In the standard ceremony account, use Finder to copy
lightyear504.zip from USB to Downloads. Compare the hash with the value supplied
separately in chat. Stop on any mismatch, error, administrator prompt or security
block; do not remove quarantine, change security settings or repair by guessing.
Use a fresh destination; setup refuses an existing runtime/site directory.

1. Open Terminal and type: `cd ~/Downloads`
2. Type: `shasum -a 256 lightyear504.zip` and compare all 64 digits with chat.
3. Only after a match: `ditto -x -k lightyear504.zip ~/`
4. Type: `cd ~/lightyear504`
5. Type: `/bin/bash setup.sh` and confirm UNPLUGGED.
6. Type: `/bin/bash sign.sh --help`

Setup verifies the internal manifest before unpacking the runtime, uses only
local hash-pinned wheels, and checks imports and both public PEM digests.
It never discovers a device, requests a PIN or signs. Retain the printed source
and import-check result. Setup estimate: 10–15 minutes after USB transfer.
Planned interop: 30–60 minutes in a separately confirmed attended window, with
reviewed public packets for both roles, original deadlines and no automatic retry.
Exact session arguments will be supplied as files to avoid long manual typing.
No production admission, Tower import, merge or native/P5 qualification follows
from setup or an interoperability result.
