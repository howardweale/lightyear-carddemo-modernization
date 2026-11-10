"""Fixed public attempts inside a pre-exec-launched NO-KEY worker.

This module NEVER applies or relaxes policy. Loading it and all worker imports
happens after the owner-launched helper execs it; baseline is explicitly unconfined.
"""
import ctypes as C
import errno
import os
import resource
import sys

OPERATIONS = ("none", "fork", "spawn", "exec-same", "exec-other", "mach-lookup", "ls-open")


def entry(fd):
    if sys.platform != "darwin" or not os.getuid() or not os.geteuid():
        raise ValueError("d01-worker-platform-refused")
    if not 3 <= fd <= 1024:
        raise ValueError("d01-worker-witness-refused")
    return dict(pid=os.getpid(), parent_pid=os.getppid(),
                nproc=list(resource.getrlimit(resource.RLIMIT_NPROC)))


def attempt(operation, fd, app):
    if operation not in OPERATIONS or operation == "none":
        raise ValueError("d01-attempt-refused")
    row = dict(operation=operation, status=None, child=None, reaped=None)
    sentinel = f"import os;os.write({fd},b'X');os._exit(17)"
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
