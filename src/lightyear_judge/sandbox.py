"""Linux-only, empty-root candidate sandbox. There is no unsandboxed fallback."""

import os
import signal
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def require_trusted_installation(agent_uid):
    """Agent-writable executables/imports would bypass the separate-user boundary."""
    import grp
    import pwd

    account = pwd.getpwuid(agent_uid)
    groups = {
        account.pw_gid,
        *(g.gr_gid for g in grp.getgrall() if account.pw_name in g.gr_mem),
    }
    paths = [
        Path(__file__).resolve().parents[2],
        Path(sys.executable).absolute().parent.parent,
        Path(shutil.which("java") or "").resolve().parent.parent,
    ]
    checked = set()
    for root in paths:
        pending = [root, *root.parents, *root.rglob("*")]
        while pending:
            original = pending.pop()
            p = original.resolve()
            if p in checked:
                continue
            checked.add(p)
            while not p.exists():
                p = p.parent  # Optional distro src.zip links can be dangling.
            pending.extend(parent for parent in p.parents if parent not in checked)
            info = p.stat()
            if "system.posix_acl_access" in os.listxattr(p):
                raise ValueError("installation-acl-refused")
            # Sticky system temporary parents cannot replace another owner's child.
            sticky_parent = (
                p != root
                and info.st_mode & stat.S_ISVTX
                and info.st_uid != agent_uid
            )
            if (
                info.st_uid == agent_uid
                or (info.st_mode & 0o002 and not sticky_parent)
                or (
                    info.st_gid in groups and info.st_mode & 0o020 and not sticky_parent
                )
            ):
                raise ValueError("agent-writable-installation-refused")


def require_isolation(root, agent_uid):
    if not sys.platform.startswith("linux") or os.geteuid() == 0:
        raise ValueError("judge-requires-unprivileged-linux-user")
    if type(agent_uid) is not int or agent_uid <= 0 or agent_uid == os.geteuid():
        raise ValueError("separate-agent-user-required")
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("private-root-link-refused")
    info = root.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("private-root-must-be-owner-only")
    if not shutil.which("bwrap") or not shutil.which("java"):
        raise ValueError("sandbox-runtime-unavailable")


def limits():
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))


def command(jar, inputs, output, arguments):
    java = Path(shutil.which("java") or "").resolve()
    runtime = java.parent.parent
    if not (runtime / "bin/java").is_file():
        raise ValueError("java-runtime-unavailable")
    cmd = [
        shutil.which("bwrap"),
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        str(runtime),
        "/runtime",
    ]
    for folder in ("/lib", "/lib64", "/usr/lib"):
        if Path(folder).exists():
            cmd += ["--ro-bind", folder, folder]
    for folder in sorted(Path("/etc").glob("java-*-openjdk")):
        cmd += ["--ro-bind", str(folder), str(folder)]
    for file in ("/etc/ld.so.cache", "/etc/localtime"):
        if Path(file).exists():
            cmd += ["--ro-bind", file, file]
    cmd += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "67108864",
        "--tmpfs",
        "/tmp",
        "--size",
        "1048576",
        "--tmpfs",
        "/home",
        "--ro-bind",
        str(jar),
        "/candidate.jar",
        "--ro-bind",
        str(inputs),
        "/inputs",
        "--ro-bind",
        str(output),
        "/outputs",
    ]
    # Writable files, read-only parent: cannot create an unbounded number of outputs,
    # replace a file with a symlink, or smuggle other host paths into the evidence.
    for name in ("acctdata.txt", "transactions.txt", "candidate-receipt.json"):
        cmd += ["--bind", str(output / name), "/outputs/" + name]
    cmd += [
        "--chdir",
        "/tmp",
        "--setenv",
        "HOME",
        "/home",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--",
        "/runtime/bin/java",
        "-Xmx256m",
        "-XX:ActiveProcessorCount=2",
        "-XX:-UsePerfData",
        "-jar",
        "/candidate.jar",
        *arguments,
    ]
    return cmd


def run(jar, inputs, output, arguments, log, timeout=300):
    output.mkdir()
    for name in ("acctdata.txt", "transactions.txt", "candidate-receipt.json"):
        (output / name).touch(exist_ok=False)
    with log.open("xb") as stream:
        child = subprocess.Popen(
            command(jar, inputs, output, arguments),
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env={"PATH": "/usr/bin:/bin"},
            start_new_session=True,
            preexec_fn=limits,
        )
        try:
            rc = child.wait(timeout=timeout)
            status = "completed"
        except subprocess.TimeoutExpired:
            rc, status = None, "timed-out"
        finally:
            # Kill the entire process group even when the launcher exited. PID namespace
            # teardown also kills descendants; no candidate process survives its attempt.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=10)
    total = 0
    for p in output.rglob("*"):
        info = p.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("candidate-output-not-regular")
        total += info.st_size
    if total > 32 * 1024 * 1024:
        raise ValueError("candidate-output-too-large")
    return rc, status
