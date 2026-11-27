"""CI-only concurrent samples with independent witnesses; never race closure."""
import errno
import json
import os
import signal
import subprocess
import time


def threaded(binary, deadline):
    rows = []
    for phase in ("threads-before-policy", "threads-after-policy"):
        for operation in ("fork", "spawn"):
            for policy in ("baseline", "combined"):
                row = dict(policy=policy, operation="threaded-" + operation,
                           phase=phase, observation="UNKNOWN", qualified=False)
                process = None
                read_fd, write_fd = os.pipe()
                os.set_blocking(read_fd, False)
                try:
                    end = min(deadline, time.monotonic() + 8)
                    if time.monotonic() >= end:
                        raise TimeoutError("original deadline expired")
                    process = subprocess.Popen(
                        [str(binary), policy, phase, operation, str(write_fd)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
                        pass_fds=(write_fd,), start_new_session=True)
                    os.close(write_fd)
                    write_fd = -1
                    out, err = process.communicate(timeout=max(0.001, end-time.monotonic()))
                    witness = bytearray()
                    while True:
                        try:
                            part = os.read(read_fd, 4096)
                        except BlockingIOError:
                            raise RuntimeError("witness channel still open") from None
                        if not part:
                            break
                        witness.extend(part)
                        if len(witness) > 16:
                            raise RuntimeError("unexpected witness count")
                    row.update(returncode=process.returncode, witness_hex=witness.hex(),
                               stderr=err.decode("utf-8", "replace")[-4096:])
                    if process.returncode != 0:
                        raise RuntimeError("thread/policy/API unavailable")
                    report = json.loads(out)
                    row["report"] = report
                    attempts = report["attempts"]
                    if (report["pid"] != process.pid or report["uid"] != os.getuid() or
                            report["euid"] != os.geteuid() or not report["uid"] or
                            report["ready_threads"] != 4 or len(attempts) != 16 or
                            {(a["thread"], a["iteration"]) for a in attempts} !=
                            {(t, i) for t in range(4) for i in range(4)}):
                        raise RuntimeError("thread identity or attempt inventory mismatch")
                    if policy == "baseline":
                        if (witness != b"X" * 16 or
                                any(a["status"] != 0 or a["child"] <= 0 or
                                    a["reaped"] != 1 for a in attempts) or
                                len({a["child"] for a in attempts}) != 16):
                            raise RuntimeError("concurrent positive control incomplete")
                        row["observation"] = "POSITIVE_CONTROL_OBSERVED"
                    else:
                        if (report["sandbox_rc"] != 0 or report["nproc"] != [0, 0] or
                                witness or any(a["status"] not in
                                    (errno.EAGAIN, errno.EPERM, errno.EACCES) or
                                    a["child"] != 0 or a["reaped"] != 0 for a in attempts)):
                            raise RuntimeError("concurrent creation not explicitly refused")
                        row["observation"] = "KERNEL_DENIAL_OBSERVED"
                except Exception as exc:
                    row.update(observation="UNKNOWN", error=str(exc))
                finally:
                    if process is not None and process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            row.update(observation="UNKNOWN", cleanup="UNKNOWN")
                    if write_fd != -1:
                        os.close(write_fd)
                    os.close(read_fd)
                    rows.append(row)
    controls = {(r["phase"], r["operation"]): r["observation"]
                for r in rows if r["policy"] == "baseline"}
    for row in rows:
        if controls.get((row["phase"], row["operation"])) != "POSITIVE_CONTROL_OBSERVED":
            row.update(observation="UNKNOWN", control="matching positive control missing")
    return rows
