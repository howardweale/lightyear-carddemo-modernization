"""Public macOS kernel-denial experiments; never a qualification verdict."""
import errno
import hashlib
import json
import os
import platform
import runpy
from pathlib import Path
import signal
import subprocess
import sys
import time

CREATION = ("fork", "raw-fork", "vfork", "spawn", "spawn-suspended")
EXEC = ("exec", "spawn-setexec")
POLICIES = ("baseline", "rlimit", "sandbox", "combined")


def experiment(binary, policy, operation, deadline):
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}
    process = None
    result = {"policy": policy, "operation": operation}
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("original experiment deadline expired")
        process = subprocess.Popen(
            [str(binary), policy, operation, str(write_fd)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            pass_fds=(write_fd,), start_new_session=True,
        )
        os.close(write_fd)
        write_fd = -1
        stdout, stderr = process.communicate(timeout=max(0.001, deadline-time.monotonic()))
        witness = bytearray()
        while True:
            try:
                part = os.read(read_fd, 4096)
            except BlockingIOError:
                raise RuntimeError("witness channel still open after worker exit")
            if not part:
                break
            witness.extend(part)
            if len(witness) > 16:
                raise RuntimeError("unexpected witness volume")
        reports = [json.loads(line) for line in stdout.decode("utf-8").splitlines()]
        result.update(returncode=process.returncode, worker_pid=process.pid,
                      reports=reports, witness_hex=witness.hex(),
                      stderr=stderr.decode("utf-8", "replace")[-4096:])
        if process.returncode not in (0, 17) or not reports:
            raise RuntimeError("worker/policy unavailable or incomplete")
        last = reports[-1]
        if last["pid"] != process.pid or last["uid"] == 0 or last["euid"] == 0:
            raise RuntimeError("worker identity/root refused")
        replacement = operation in EXEC
        expected_denial = policy != "baseline" and not (policy == "rlimit" and replacement)
        if expected_denial:
            allowed_errors = {errno.EAGAIN} if policy == "rlimit" else {errno.EPERM, errno.EACCES}
            if policy == "combined":
                allowed_errors.add(errno.EAGAIN)
            if (len(reports) != 1 or last["kind"] != "denied" or
                    last["errno"] not in allowed_errors or last["child"] != 0 or
                    witness or process.returncode != 0):
                raise RuntimeError("creation/exec was not explicitly denied")
            if policy in ("rlimit", "combined") and (last["soft"] or last["hard"]):
                raise RuntimeError("zero hard limit lost")
            if policy in ("sandbox", "combined") and last["sandbox_rc"] != 0:
                raise RuntimeError("sandbox not applied")
            if operation == "raise-fork" and (
                    last["raise_rc"] != -1 or last["raise_errno"] != errno.EPERM):
                raise RuntimeError("worker could raise hard limit")
            result["observation"] = "KERNEL_DENIAL_OBSERVED"
        else:
            wanted = "exec-entered" if replacement else "created"
            if last["kind"] != wanted or witness != b"X":
                raise RuntimeError("positive control did not create/exec")
            if replacement and process.returncode != 17:
                raise RuntimeError("replacement control exit mismatch")
            if not replacement and (last["child"] <= 0 or process.returncode != 0):
                raise RuntimeError("child creation control exit mismatch")
            result["observation"] = "POSITIVE_CONTROL_OBSERVED"
    except Exception as exc:
        result.update(observation="UNKNOWN", error=str(exc))
    finally:
        if process is not None and process.poll() is None:
            # Disposable probe cleanup, not arbitrary-descendant closure evidence.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                result["cleanup"] = "UNKNOWN"
        if write_fd != -1:
            os.close(write_fd)
        os.close(read_fd)
    return result


def main():
    if platform.system() != "Darwin" or os.getuid() == 0 or len(sys.argv) != 3:
        raise SystemExit("macOS non-root CI only; binary and output required")
    binary = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2])
    deadline = time.monotonic() + 240
    rows = []
    for policy in POLICIES:
        operations = CREATION + EXEC
        if policy in ("rlimit", "combined"):
            operations += ("raise-fork",)
        if policy in ("sandbox", "combined"):
            operations += ("relax-fork",)
        for operation in operations:
            rows.append(experiment(binary, policy, operation, deadline))
    delegated = runpy.run_path(str(Path(__file__).with_name("delegated.py")))
    rows.extend(delegated["delegated"](deadline))
    report = {
        "schema": "d01-a-closed-creation-feasibility/1",
        "platform": platform.platform(), "machine": platform.machine(),
        "python": sys.version, "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "rows": rows, "qualified": False, "closed_creation_established": False,
        "owner_death": "UNKNOWN", "guardian_death": "UNKNOWN",
        "remaining": [
            "Independent prelaunch enforcement/identity binding in the actual workload",
            "Other inherited Mach/IPC capabilities, delegated services and delayed launches",
            "Installed operator OS/build, privilege transitions and workload compatibility",
            "Races, multithreaded attempts, original-deadline owner/guardian cleanup",
        ],
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(json.dumps(row, sort_keys=True), flush=True)
    # Any unsupported API, missing control, escape or incomplete observation is red.
    # Even green validates only these direct/delegated experiments, never A feasibility.
    if any(row["observation"] == "UNKNOWN" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
