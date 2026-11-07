"""Mac setup import checks only: no device enumeration, PIN or signature."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

root = Path(__file__).resolve().parent
if sys.platform != "darwin" or sys.version_info[:2] != (3, 12):
    raise SystemExit("STOP: bundled Mac Python 3.12 required")
sys.path[:0] = [str(root / "site"), str(root / "code/src"), str(root / "code")]
manifest = json.loads((root / "DEPENDENCIES.json").read_text())
arch = platform.machine()
for name, item in manifest[arch]["wheels"].items():
    if importlib.metadata.version(name) != item["version"]:
        raise SystemExit("STOP: dependency version mismatch")
# Imports load extensions and the OS PC/SC framework; never enumerate a token.
from ykman.device import list_all_devices
from yubikit.piv import PivSession
from smartcard import scard
from tools import human_signing
from lightyear_execution.signing_key_a import PUBLIC_KEYS
expected = {
    "controller-receipt": "58c97a1c25b649a8d61b4b36afe5ae8099d953720892f97764021a343e533c8c",
    "candidate-commit": "a0627e8ffe1c74f610b92175b0486e37ef0552b503976fba5a983f268eaa677a",
}
for role, digest in expected.items():
    if hashlib.sha256(PUBLIC_KEYS[role][0]).hexdigest() != digest:
        raise SystemExit("STOP: public key mismatch")
print("Python:", platform.python_version(), "architecture:", arch)
print("Import checks complete; no device access or signing performed.")
print("Source:", (root / "SOURCE_COMMIT").read_text().strip())
