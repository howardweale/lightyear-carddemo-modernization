"""Fixed public attempts inside a pre-exec-launched NO-KEY worker.

Loading this module and all worker imports happens after the owner-launched
helper execs it; baseline is explicitly unconfined. Optional regression helper
attempts raise/relax adversarially; success never establishes containment.
"""
import ctypes as C
import errno
import hashlib
import json
from pathlib import Path
import stat
import os
import resource
import sys

ORIGINAL_OPERATIONS = ("none", "fork", "spawn", "exec-same", "exec-other", "mach-lookup", "ls-open")

NATIVE_OPERATIONS = ("raw-fork", "vfork", "spawn-suspended", "spawn-setexec", "raise-fork", "relax-fork", "concurrent-fork", "concurrent-spawn")
OPERATIONS = ORIGINAL_OPERATIONS + NATIVE_OPERATIONS

def native_attempt(operation, fd, digest, original, cleanup):
    # Public, bounded diagnostics only. No exception message/path is returned.
    # Failure remains UNKNOWN; it is never a kernel-refusal observation.
    phase = "runtime-path"
    rc = None
    try:
        helper = Path(sys.base_prefix).resolve(strict=True) / "lib/d01-regression.dylib"
        phase = "helper-path"
        if helper.resolve(strict=True) != helper or helper.is_symlink():
            raise ValueError("d01-native-path-refused")
        phase = "helper-stat"
        info = helper.stat()
        phase = "helper-bytes"
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                info.st_mode & 0o222 or type(digest) is not str or len(digest) != 64 or
                hashlib.sha256(helper.read_bytes()).hexdigest() != digest):
            raise ValueError("d01-native-bytes-refused")
        phase = "library-load"
        lib = C.CDLL(str(helper), use_errno=True)
        lib.d01_attempt.argtypes = [C.c_char_p, C.c_char_p, C.c_int, C.c_double, C.c_double, C.c_char_p, C.c_size_t]
        lib.d01_attempt.restype = C.c_int
        output = C.create_string_buffer(16384)
        phase = "interpreter-path"
        interpreter = os.fsencode(Path(sys.executable).resolve())
        phase = "native-call"
        rc = lib.d01_attempt(operation.encode("ascii"), interpreter,
                            fd, original, cleanup, output, len(output))
        if rc or not output.value or len(output.value) >= len(output)-1:
            raise ValueError("d01-native-call-incomplete")
        phase = "result-decode"
        result = json.loads(output.value)
        if not isinstance(result, dict) or result.get("operation") != operation:
            raise ValueError("d01-native-operation-mismatch")
        result["native_sha256"] = digest
        return result
    except Exception as error:
        number = getattr(error, "errno", None)
        number = number if type(number) is int and -4096 <= number <= 4096 else None
        name = type(error).__name__
        if name not in ("PermissionError", "FileNotFoundError", "OSError", "ValueError",
                        "TypeError", "AttributeError", "JSONDecodeError"):
            name = "Exception"
        return dict(operation=operation, native_failure_phase=phase,
                    native_failure_type=name, native_errno=number, native_rc=rc)


def entry(fd):
    if sys.platform != "darwin" or not os.getuid() or not os.geteuid():
        raise ValueError("d01-worker-platform-refused")
    if not 3 <= fd <= 1024:
        raise ValueError("d01-worker-witness-refused")
    return dict(pid=os.getpid(), parent_pid=os.getppid(),
                nproc=list(resource.getrlimit(resource.RLIMIT_NPROC)))


def attempt(operation, fd, app, *, native_sha256=None, original=None, cleanup=None):
    if operation not in OPERATIONS or operation == "none":
        raise ValueError("d01-attempt-refused")
    if operation in NATIVE_OPERATIONS:
        return native_attempt(operation, fd, native_sha256, original, cleanup)
    row = dict(operation=operation, status=None, child=None, reaped=None)
    sentinel = f"import os;os.write({fd},b'X');os._exit(17)"
    if native_sha256 is not None and operation == "exec-same":
        sentinel = ("import os,json,resource,sys;print(json.dumps(dict(kind='d01-replacement',"
                    "operation='exec-same',interpreter=os.path.realpath(sys.executable),pid=os.getpid(),parent_pid=os.getppid(),"
                    "nproc=list(resource.getrlimit(resource.RLIMIT_NPROC)))),flush=True);" + sentinel)
    if operation in ("fork", "spawn", "exec-same", "exec-other"):
        try:
            if operation == "fork":
                child = os.fork()
                if child == 0:
                    try:
                        os.write(fd, b"X")
                    except BaseException:
                        os._exit(122)
                    os._exit(17)
            elif operation == "spawn":
                child = os.posix_spawn(sys.executable,
                    [sys.executable, "-I", "-B", "-c", sentinel],
                    {"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
            elif operation == "exec-same":
                os.execve(sys.executable, [sys.executable, "-I", "-B", "-c", sentinel],
                          {"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
                raise AssertionError("exec returned")
            else:
                os.execve("/bin/sh", ["/bin/sh", "-c", f"printf X >&{fd}; exit 17"],
                          {"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
                raise AssertionError("exec returned")
            row.update(status=0, child=child)
            got, status = os.waitpid(child, 0)
            row.update(reaped=got == child, wait_status=status)
        except OSError as error:
            row["status"] = error.errno
        return row
    if operation == "mach-lookup":
        lib = C.CDLL("/usr/lib/libSystem.B.dylib")
        lib.bootstrap_look_up.argtypes = [C.c_uint, C.c_char_p, C.POINTER(C.c_uint)]
        lib.bootstrap_look_up.restype = C.c_int
        port = C.c_uint()
        bootstrap = C.c_uint.in_dll(lib, "bootstrap_port").value
        row.update(status=lib.bootstrap_look_up(bootstrap,
                    b"com.apple.coreservices.launchservicesd", C.byref(port)),
                   port_present=bool(port.value))
        return row
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
        raise ValueError("d01-CFURL-unavailable")
    row["status"] = ls.LSOpenCFURLRef(url, None)
    return row
