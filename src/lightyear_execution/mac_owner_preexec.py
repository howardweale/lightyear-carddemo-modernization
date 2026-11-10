"""Opt-in NO-KEY pre-exec binding; not reachable through the rehearsal CLI."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import sys

OPERATIONS = ("none", "fork", "spawn", "exec-same", "exec-other", "mach-lookup", "ls-open")


def _file(path, digest):
    resolved = Path(path).resolve(strict=True)
    info = resolved.stat()
    if (str(resolved) != str(path) or not stat.S_ISREG(info.st_mode) or
            info.st_uid != os.getuid() or info.st_mode & 0o022 or
            type(digest) is not str or len(digest) != 64 or
            hashlib.sha256(resolved.read_bytes()).hexdigest() != digest):
        raise ValueError("d01-bound-file-refused")
    return resolved


@dataclass(frozen=True)
class PreExecBinding:
    """Only a public CI caller supplies these exact locally measured bindings.

    This is not an immutable filesystem or OS birth-time attestation. The gap
    between parent hash checks and exec is an unresolved race, never qualified.
    """
    launcher: str
    launcher_sha256: str
    worker_sha256: str
    probe_sha256: str
    interpreter_sha256: str
    runtime: str
    app: str
    witness_fd: int
    operation: str = "none"
    policy: str = "combined"

    def command(self, argv):
        if (sys.platform != "darwin" or not os.getuid() or not os.geteuid() or
                self.policy not in ("baseline", "combined") or self.operation not in OPERATIONS or
                type(self.witness_fd) is not int or not 3 <= self.witness_fd <= 1024):
            raise ValueError("d01-binding-refused")
        worker = Path(__file__).with_name("mac_owner_process.py").resolve(strict=True)
        interpreter = Path(sys.executable).resolve(strict=True)
        if (len(argv) != 9 or argv[:4] != [sys.executable, "-I", "-B", str(worker)] or
                argv[4:6] != ["--worker", "child"] or argv[6] not in ("S1", "S2")):
            raise ValueError("d01-fixed-worker-only")
        _file(self.launcher, self.launcher_sha256)
        _file(str(worker), self.worker_sha256)
        _file(str(worker.with_name("mac_owner_preexec_probe.py")), self.probe_sha256)
        # The installed runtime can be root-owned; pin bytes and exact canonical path.
        if hashlib.sha256(interpreter.read_bytes()).hexdigest() != self.interpreter_sha256:
            raise ValueError("d01-interpreter-changed")
        runtime, app = Path(self.runtime).resolve(strict=True), Path(self.app).resolve(strict=True)
        if (str(runtime) != self.runtime or str(app) != self.app or not runtime.is_dir() or
                not app.is_dir() or runtime in map(Path, ("/", "/usr", "/System", "/Library")) or
                not interpreter.is_relative_to(runtime) or not stat.S_ISFIFO(os.fstat(self.witness_fd).st_mode)):
            raise ValueError("d01-runtime-input-or-witness-refused")
        for path in (self.launcher, str(worker), str(interpreter), self.runtime, self.app):
            if any(ord(c) < 32 or c in '\\"' for c in path):
                raise ValueError("d01-profile-metacharacter-refused")
        return [self.launcher, self.policy, self.runtime, self.app, str(interpreter),
                *argv[1:], "--d01-probe", self.operation, str(self.witness_fd), self.app]
