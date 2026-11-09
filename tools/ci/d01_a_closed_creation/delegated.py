"""CI-only delegated LaunchServices probes; never a closed-creation verdict."""
import ctypes as C
import json
import os
from pathlib import Path
import plistlib
import resource
import signal
import subprocess
import sys
import tempfile
import time
import uuid

SERVICE = b"com.apple.coreservices.launchservicesd"
BOOTSTRAP_NOT_PRIVILEGED = 1100
LS_NO_LAUNCH_PERMISSION = -10826


def worker(policy, operation, app):
    """Resolve API entry points before applying the unchanged deny-default policy."""
    signal.alarm(8)
    if sys.platform != "darwin" or os.getuid() == 0 or os.geteuid() == 0:
        raise RuntimeError("non-root macOS only")
    lib = C.CDLL("/usr/lib/libSystem.B.dylib")
    box = C.CDLL("/usr/lib/libsandbox.dylib")
    box.sandbox_init.argtypes = [C.c_char_p, C.c_uint64, C.POINTER(C.c_void_p)]
    box.sandbox_init.restype = C.c_int
    lib.bootstrap_look_up.argtypes = [C.c_uint, C.c_char_p, C.POINTER(C.c_uint)]
    lib.bootstrap_look_up.restype = C.c_int
    bootstrap = C.c_uint.in_dll(lib, "bootstrap_port").value
    port = C.c_uint()
    url = None
    if operation == "ls-open":
        cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        ls = C.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
            C.c_void_p, C.c_char_p, C.c_long, C.c_ubyte]
        cf.CFURLCreateFromFileSystemRepresentation.restype = C.c_void_p
        ls.LSOpenCFURLRef.argtypes = [C.c_void_p, C.c_void_p]
        ls.LSOpenCFURLRef.restype = C.c_int32
        raw = os.fsencode(app)
        url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), 1)
        if not url:
            raise RuntimeError("CFURL preparation unavailable")
    row = {"pid": os.getpid(), "uid": os.getuid(), "euid": os.geteuid(),
           "policy": policy, "operation": operation, "sandbox_rc": None}
    if policy == "combined":
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    if policy != "baseline":
        error = C.c_void_p()
        row["sandbox_rc"] = box.sandbox_init(b"(version 1)(deny default)", 0, C.byref(error))
        if row["sandbox_rc"] != 0:
            raise RuntimeError("sandbox unavailable")
    row["nproc"] = list(resource.getrlimit(resource.RLIMIT_NPROC))
    # Different workers exercise lookup and the actual open-style API request.
    # Framework loading can acquire inherited capabilities; that is not hidden.
    if operation == "mach-lookup":
        row["status"] = lib.bootstrap_look_up(bootstrap, SERVICE, C.byref(port))
        row["port_present"] = bool(port.value)
    elif operation == "ls-open":
        row["status"] = ls.LSOpenCFURLRef(url, None)
    else:
        raise RuntimeError("unknown delegated operation")
    os.write(1, (json.dumps(row) + "\n").encode())
    os._exit(0)  # Process exit releases ports/CF objects, with no cleanup API calls.


def application(root, token):
    app = root / (token + ".app")
    contents = app / "Contents"
    executable = contents / "MacOS" / "Witness"
    executable.parent.mkdir(parents=True)
    witness = root / (token + ".witness")
    # No external commands, persistent launch agent, signing, or installation.
    # A successful LaunchServices request must cause this separate app to run.
    quoted = "'" + str(witness).replace("'", "'\\''") + "'"
    script = "#!/bin/sh\nset -C\nprintf '%s %s %s\\n' '" + token + "' \"$$\" \"$PPID\" > " + quoted + "\n"
    executable.write_text(script, encoding="utf-8")
    executable.chmod(0o700)
    (contents / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "org.lightyear.d01probe." + token,
        "CFBundleExecutable": "Witness", "CFBundlePackageType": "APPL",
        "CFBundleName": "D01 public witness", "CFBundleVersion": "1",
        "LSBackgroundOnly": True,
    }))
    return app, witness


def delegated(deadline):
    rows = []
    # The outer original deadline is shared with all existing direct probes.
    # Retain this disposable directory through report completion to catch witnesses.
    root = Path(tempfile.mkdtemp(prefix="d01-delegated-")).resolve()
    watched = []
    for policy in ("baseline", "sandbox", "combined"):
        for operation in ("mach-lookup", "ls-open"):
            row = {"policy": policy, "operation": operation,
                   "observation": "UNKNOWN", "qualified": False}
            process = None
            try:
                token = uuid.uuid4().hex
                app, witness = application(root, token)
                watched.append((row, witness))
                end = min(deadline, time.monotonic() + 8)
                if end <= time.monotonic():
                    raise TimeoutError("original deadline expired")
                process = subprocess.Popen(
                    [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                     policy, operation, str(app)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
                    start_new_session=True,
                )
                out, err = process.communicate(timeout=max(0.001, end-time.monotonic()))
                row.update(returncode=process.returncode,
                           stderr=err.decode("utf-8", "replace")[-4096:])
                if process.returncode != 0:
                    raise RuntimeError("delegated worker unavailable")
                report = json.loads(out)
                row["report"] = report
                if (report["pid"] != process.pid or report["uid"] != os.getuid() or
                        report["euid"] != os.geteuid() or report["policy"] != policy or
                        report["operation"] != operation):
                    raise RuntimeError("delegated worker identity mismatch")
                if policy != "baseline" and report["sandbox_rc"] != 0:
                    raise RuntimeError("sandbox not applied")
                if policy == "combined" and report["nproc"] != [0, 0]:
                    raise RuntimeError("zero hard limit lost")
                if policy == "baseline":
                    if report["status"] != 0:
                        raise RuntimeError("unrestricted service/request unavailable")
                    if operation == "mach-lookup":
                        if not report["port_present"]:
                            raise RuntimeError("lookup control has no send right")
                    else:
                        while not witness.exists() and time.monotonic() < end:
                            time.sleep(min(0.05, max(0, end-time.monotonic())))
                        fields = witness.read_text().split()
                        if (len(fields) != 3 or fields[0] != token or
                                int(fields[1]) <= 0 or int(fields[1]) == process.pid or
                                int(fields[2]) == process.pid):
                            raise RuntimeError("independent delegated launch witness missing")
                        row["witness"] = fields
                    row["observation"] = "POSITIVE_CONTROL_OBSERVED"
                else:
                    expected = (BOOTSTRAP_NOT_PRIVILEGED if operation == "mach-lookup"
                                else LS_NO_LAUNCH_PERMISSION)
                    if report["status"] != expected or report.get("port_present", False):
                        raise RuntimeError("no explicit service permission refusal")
                    if witness.exists():
                        raise RuntimeError("delegated launch escaped")
                    row["observation"] = "PERMISSION_REFUSAL_OBSERVED"
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
                rows.append(row)
    for row, witness in watched:
        if row["policy"] != "baseline" and witness.exists():
            row.update(observation="UNKNOWN", error="late delegated launch witness")
    controls = {r["operation"]: r["observation"] for r in rows if r["policy"] == "baseline"}
    for row in rows:
        if controls.get(row["operation"]) != "POSITIVE_CONTROL_OBSERVED":
            row.update(observation="UNKNOWN", control="missing successful unrestricted control")
    # Permission errors do not identify every internal denial point. Missing
    # witnesses alone never establish denial, and finite observation is not closure.
    return rows


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("baseline", "sandbox", "combined"):
        raise SystemExit("CI worker arguments required")
    worker(*sys.argv[1:])
