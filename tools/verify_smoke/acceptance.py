"""Optional root supervisor for a real Linux acceptance PLATFORM CHECK, never a model test."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time


def result_status(returncode, output):
    counts = re.findall(r"^Ran (\d+) tests?", output, re.MULTILINE)
    passed = (returncode == 0 and counts and int(counts[-1]) >= 5
              and "VERIFY_ACCEPTANCE:" in output
              and not re.search(r"skipped=\d+|\.\.\. skipped ", output))
    return "passed" if passed else "failed"


def main():
    import fcntl

    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Run as the administrator in the dedicated Ubuntu VM")
    lock = open("/run/lock/lightyear-verify-smoke.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.run(["systemctl", "is-active", "--quiet", "lightyear-verify-smoke.service"]).returncode == 0:
        raise SystemExit("Stop the manual judge first; no concurrent acceptance run")
    root = Path("/opt/lightyear-verify")
    venv = Path("/opt/lightyear-verify-venv/bin/python")
    subprocess.run(["python3", "-I", str(root / "tools/verify_smoke/provision.py"), "verify"], check=True)
    subprocess.run(["bash", str(root / "tools/verify_smoke/check.sh")], check=True)
    arch = {"aarch64": "arm64", "x86_64": "x86_64"}[platform.machine()]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = Path("/var/lib/lightyear-verify-smoke/platform") / (stamp + "-" + arch)
    folder.mkdir(mode=0o700, parents=True)
    start = time.monotonic()
    # Existing supervisor uses UID 1000 and 65534, not the manual service accounts.
    # All fixtures are synthetic/public; its canary is generated only in scratch.
    with (folder / "acceptance.log").open("xb") as log:
        rc = subprocess.run([str(venv), str(root / "tools/run_verify_acceptance.py")],
                            cwd=root, stdout=log, stderr=subprocess.STDOUT,
                            env={"PATH": "/usr/bin:/bin", "HOME": "/root", "LANG": "C.UTF-8",
                                 "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}).returncode
    output = (folder / "acceptance.log").read_bytes()
    report = {
        "schema": "verify-smoke-platform/1", "kind": "platform-check",
        "architecture": arch, "uname_machine": platform.machine(),
        "ubuntu": Path("/etc/os-release").read_text(), "kernel": platform.release(),
        "started_utc": stamp, "elapsed_seconds": round(time.monotonic() - start, 3),
        "exit_code": rc, "status": result_status(rc, output.decode(errors="replace")),
        "log_sha256": hashlib.sha256(output).hexdigest(), "model_calls": 0,
        "setup_sha256": hashlib.sha256(Path("/var/lib/lightyear-verify-smoke/setup.json").read_bytes()).hexdigest(),
        "claim": "Public-fixture platform check only; no live harness or Maintec equivalence claim",
        "acceptance_uids": {"judge": 1000, "agent": 65534},
    }
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['status']}: {folder / 'report.json'}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

