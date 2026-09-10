#!/usr/bin/env python3
"""Run the network regression suite through Kubernetes v1.35's actual API types."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    go = shutil.which("go")
    if not go:
        raise SystemExit("Go 1.25 or newer is required for the Kubernetes API representation test")
    with tempfile.TemporaryDirectory(prefix="network-kubernetes-api-") as directory:
        binary = Path(directory) / ("roundtrip.exe" if os.name == "nt" else "roundtrip")
        subprocess.run([go, "build", "-buildvcs=false", "-mod=readonly", "-o", str(binary), "."],
                       cwd=ROOT / "tools/testdata/network-kubernetes-api", check=True, timeout=240)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "LIGHTYEAR_NETWORK_API_ROUNDTRIP": str(binary)}
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                 "-p", "test_cloudbank_network_enforcement.py", "-v"],
                                cwd=ROOT, env=env, timeout=180)
        if result.returncode:
            return result.returncode
    print("MS67_KUBERNETES_API_ROUNDTRIP=PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
