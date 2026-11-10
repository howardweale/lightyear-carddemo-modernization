"""CI-only binding evidence. UNKNOWN is red, including all negative LS rows."""
import errno
import hashlib
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from lightyear_execution.mac_owner_process import _OwnedWorker, _receive
from lightyear_execution.mac_owner_preexec import PreExecBinding, OPERATIONS


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def application(root):
    token = uuid.uuid4().hex
    app, witness = root / (token + ".app"), root / (token + ".witness")
    contents = app / "Contents"
    executable = contents / "MacOS" / "Witness"
    executable.parent.mkdir(parents=True)
    quoted = "'" + str(witness).replace("'", "'\\''") + "'"
    executable.write_text("#!/bin/sh\nset -C\nprintf '%s %s %s\\n' '" + token +
                          "' \"$$\" \"$PPID\" > " + quoted + "\n")
    executable.chmod(0o700)
    (contents / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "org.lightyear.d01binding." + token,
        "CFBundleExecutable": "Witness", "CFBundlePackageType": "APPL",
        "CFBundleName": "D01 binding witness", "CFBundleVersion": "1",
        "LSBackgroundOnly": True,
    }))
    return app, witness, token


def collect(launcher, root, case, operation, policy, deadline):
    row = dict(case=case, operation=operation, policy=policy, observation="UNKNOWN",
               qualified=False, owner_death="UNKNOWN", guardian_death="UNKNOWN")
    app, app_witness, token = application(root)
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    worker = None
    frames = []
    stopped = False
    original = min(deadline, time.monotonic() + 15)
    cleanup = original + 5  # Original fixed bound; never renewed for a failed step.
    row.update(original_deadline=original, cleanup_deadline=cleanup)
    def stop():
        nonlocal stopped
        if not stopped and worker is not None and worker.pid is not None:
            stopped = True
            worker.request_stop()
    try:
        if time.monotonic() >= original:
            raise TimeoutError("original deadline expired before launch")
        source = ROOT / "src/lightyear_execution/mac_owner_process.py"
        probe = source.with_name("mac_owner_preexec_probe.py")
        binding = PreExecBinding(str(launcher), sha(launcher), sha(source), sha(probe),
            sha(Path(sys.executable).resolve()), str(Path(sys.base_prefix).resolve()),
            str(app), write_fd, operation, policy)
        worker = _OwnedWorker("child", case, original, cleanup, preexec=binding)
        worker.start()
        os.close(write_fd)
        write_fd = -1
        while time.monotonic() < cleanup:
            if time.monotonic() >= original:
                stop()
            try:
                if worker.channel.poll(min(0.02, max(0, cleanup-time.monotonic()))):
                    message = _receive(worker.channel)
                    frames.append(dict(at=time.monotonic(), message=message))
                    if len(frames) > 16:
                        raise ValueError("bounded frame inventory exceeded")
                    if message["kind"] == "completed":
                        stop()
            except EOFError:
                break
        stop()
        worker.join(max(0, cleanup-time.monotonic()))
        if worker.is_alive():
            worker.terminate()
            row["forced"] = True
            worker.join(max(0, cleanup-time.monotonic()))
        row.update(pid=worker.pid, exitcode=worker.exitcode, frames=frames)
        witness = bytearray()
        while True:
            part = os.read(read_fd, 32)  # Open writer yields UNKNOWN, never absence.
            if not part:
                break
            witness.extend(part)
            if len(witness) > 1:
                raise ValueError("unexpected witness inventory")
        row["witness_hex"] = witness.hex()
        if operation == "ls-open" and policy == "baseline":
            while not app_witness.exists() and time.monotonic() < original:
                time.sleep(min(0.02, max(0, original-time.monotonic())))
        if app_witness.exists():
            fields = app_witness.read_text().split()
            row["launch_witness"] = fields
            if (len(fields) != 3 or fields[0] != token or int(fields[1]) <= 0 or
                    int(fields[1]) == worker.pid or int(fields[2]) == worker.pid):
                raise ValueError("independent launch witness invalid")
        messages = [f["message"] for f in frames]
        kinds = [m["kind"] for m in messages]
        expected_tail = (["identity", "ready", "completed"] if operation == "none"
                         else ["identity", "ready", "d01-attempt", "completed"])
        exec_control = operation.startswith("exec-") and witness == b"X" and worker.exitcode == 17
        expected = ["d01-preexec", "d01-entry"] + (
            ["identity", "ready"] if exec_control else expected_tail)
        if kinds != expected or row.get("forced") or worker.exitcode is None:
            raise ValueError("worker protocol, readiness, completion or reap unknown")
        pre, entry, identity = messages[:3]
        if (pre["pid"] != worker.pid or entry["pid"] != worker.pid or
                entry["parent_pid"] != os.getpid() or identity["pid"] != worker.pid or
                identity["parent_pid"] != os.getpid() or identity["role"] != "child" or
                entry["nproc"] != pre["nproc"] or
                any(f["at"] >= original for f in frames)):
            raise ValueError("preexec/entry/identity/deadline mismatch")
        if policy == "combined" and (pre["sandbox_rc"] != 0 or entry["nproc"] != [0, 0]):
            raise ValueError("prelaunch policy or zero limit missing")
        if policy == "baseline" and pre["sandbox_rc"] != -99:
            raise ValueError("baseline policy unexpectedly active")
        if exec_control:
            if policy != "baseline":
                raise ValueError("exact pre-exec permission replayed: image replacement observed")
            row["observation"] = "POSITIVE_CONTROL_OBSERVED"
            return row, app_witness
        if worker.exitcode != 0:
            raise ValueError("worker exit not clean")
        if operation == "none":
            if witness or app_witness.exists():
                raise ValueError("unexpected witness during normal work")
            row["observation"] = "NORMAL_WORK_OBSERVED"
            return row, app_witness
        attempted = messages[-2]
        row["attempt"] = attempted
        if attempted["operation"] != operation:
            raise ValueError("attempt identity mismatch")
        status = attempted["status"]
        if policy == "baseline":
            if operation in ("fork", "spawn"):
                if (status != 0 or not attempted["child"] or attempted["reaped"] is not True or
                        witness != b"X" or not os.WIFEXITED(attempted["wait_status"]) or
                        os.WEXITSTATUS(attempted["wait_status"]) != 17):
                    raise ValueError("creation control missing")
            elif operation == "mach-lookup":
                if status != 0 or attempted.get("port_present") is not True or witness:
                    raise ValueError("lookup control missing")
            elif operation == "ls-open":
                if status != 0 or "launch_witness" not in row or witness:
                    raise ValueError("launch control missing")
            else:
                raise ValueError("exec positive control missing")
            row["observation"] = "POSITIVE_CONTROL_OBSERVED"
        else:
            if witness or app_witness.exists() or attempted.get("child") is not None:
                raise ValueError("process or launch witness observed")
            if operation == "ls-open":
                # No status, including -10826, establishes this denial point.
                raise ValueError("LaunchServices denial point not isolated")
            if operation == "mach-lookup":
                if status != 1100 or attempted.get("port_present") is not False:
                    raise ValueError("lookup explicit refusal missing")
                row["observation"] = "LOOKUP_REFUSAL_OBSERVED"
            else:
                if status not in (errno.EPERM, errno.EACCES, errno.EAGAIN):
                    raise ValueError("explicit kernel refusal missing")
                row["observation"] = "KERNEL_REFUSAL_OBSERVED"
    except Exception as error:
        row.update(observation="UNKNOWN", error=str(error), frames=frames)
    finally:
        stop()
        if worker is not None and worker.pid is not None:
            if worker.is_alive():
                worker.terminate()
                worker.join(max(0, cleanup-time.monotonic()))
            row.update(exitcode=worker.exitcode, reaped=worker.exitcode is not None)
            if worker.exitcode is not None:
                worker.close()
        if write_fd != -1:
            os.close(write_fd)
        os.close(read_fd)
    return row, app_witness


def main():
    if len(sys.argv) != 3 or sys.platform != "darwin" or not os.getuid():
        raise SystemExit("non-root macOS CI and two paths required")
    launcher, output = Path(sys.argv[1]).resolve(strict=True), Path(sys.argv[2])
    root = Path(tempfile.mkdtemp(prefix="d01-bound-worker-")).resolve()
    deadline = time.monotonic() + 240
    rows, watched = [], []
    cases = [(case, "none") for case in ("S1", "S2")]
    cases += [("S1", operation) for operation in OPERATIONS if operation != "none"]
    for case, operation in cases:
        for policy in ("baseline", "combined"):
            row, witness = collect(launcher, root, case, operation, policy, deadline)
            rows.append(row)
            watched.append((row, witness))
    for row, witness in watched:
        if row["policy"] == "combined" and witness.exists():
            row.update(observation="UNKNOWN", error="late launch witness")
    controls = {(r["case"], r["operation"]): r["observation"]
                for r in rows if r["policy"] == "baseline"}
    normal = {(r["case"], r["policy"]): r["observation"]
              for r in rows if r["operation"] == "none"}
    for row in rows:
        if controls.get((row["case"], row["operation"])) not in (
                "NORMAL_WORK_OBSERVED", "POSITIVE_CONTROL_OBSERVED"):
            row.update(observation="UNKNOWN", control="matching unrestricted control missing")
        if row["operation"] != "none" and any(normal.get(("S1", p)) != "NORMAL_WORK_OBSERVED"
                                              for p in ("baseline", "combined")):
            row.update(observation="UNKNOWN", normal_work="normal S1 completion missing")
    report = dict(schema="d01-nokey-preexec-prototype/1", rows=rows, qualified=False,
        native_proof=False, production_workload_proof=False, closed_creation_established=False,
        owner_death="UNKNOWN", guardian_death="UNKNOWN", launcher_sha256=sha(launcher),
        worker_sha256=sha(ROOT/"src/lightyear_execution/mac_owner_process.py"),
        limits=["Exact-interpreter exec permission may be replayed; successful replacement is UNKNOWN/red",
                "All negative LS rows UNKNOWN; no internal denial point isolated",
                "S1/S2 prototype only; default S1-S7/rehearsal unchanged; S3 requires child creation",
                "Pre-exec/helper and runtime input races, inherited services and all-process cleanup unproved"])
    output.write_text(json.dumps(report, indent=2)+"\n")
    for row in rows:
        print(json.dumps(row, sort_keys=True), flush=True)
    if any(row["observation"] == "UNKNOWN" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
