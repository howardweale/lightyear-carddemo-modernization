"""CI-only post-observation diagnostics; no policy changes or qualification."""
import datetime
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time

CAP = 32768
KERNEL_CAP = 512 * 1024
IPS_CAP = 2 * 1024 * 1024
IPS_TOTAL = 8 * 1024 * 1024
EXPECTED = {("S1", "none"), ("S2", "none")} | {
    ("S1", op) for op in
    ("fork", "spawn", "exec-same", "exec-other", "mach-lookup", "ls-open")}
DENIAL = re.compile(r"Sandbox:\s+[^(\r\n]+\((\d+)\)\s+deny(?:\(\d+\))?\s")


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def read_regular(path, cap):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
            raise ValueError("file type or size bound")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(cap + 1)
        after = os.fstat(fd)
        if (len(raw) > cap or len(raw) != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError("file changed or exceeded bound")
        return raw
    finally:
        os.close(fd)


def confined_pids(raw):
    report = json.loads(raw)
    if report.get("schema") != "d01-nokey-preexec-prototype/1":
        raise ValueError("observation schema")
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != 16:
        raise ValueError("observation inventory")
    selected = {}
    for row in rows:
        if row.get("policy") != "combined":
            continue
        key = (row.get("case"), row.get("operation"))
        frames = [f["message"] for f in row.get("frames", [])
                  if f.get("message", {}).get("kind") == "d01-preexec"]
        if key not in EXPECTED or key in selected or len(frames) != 1:
            raise ValueError("confined inventory or preexec frame")
        frame = frames[0]
        pid = frame.get("pid")
        if (type(pid) is not int or not 0 < pid < 2**31 or
                frame.get("sandbox_rc") != 0 or frame.get("nproc") != [0, 0] or
                row.get("pid", pid) != pid or row.get("reaped") is not True):
            raise ValueError("confined PID/policy/reap")
        selected[key] = pid
    if set(selected) != EXPECTED or len(set(selected.values())) != 8:
        raise ValueError("incomplete or reused PID inventory")
    return selected


def log_command(pids):
    matches = " OR ".join('eventMessage CONTAINS "(' + str(p) + ')"'
                          for p in sorted(pids))
    predicate = ('process == "kernel" AND eventMessage CONTAINS "Sandbox:" '
                 'AND eventMessage CONTAINS "deny" AND (' + matches + ')')
    return ["/usr/bin/log", "show", "--last", "10m", "--style", "compact",
            "--predicate", predicate]


def capture(command, deadline):
    """One query; bounded combined stdout/stderr, no shell, retry or privilege."""
    result = dict(stdout=b"", stderr=b"", overflow=False, timed_out=False,
                  eof=False, returncode=None)
    proc = None
    streams = selectors.DefaultSelector()
    try:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for name in ("stdout", "stderr"):
            pipe = getattr(proc, name)
            os.set_blocking(pipe.fileno(), False)
            streams.register(pipe, selectors.EVENT_READ, name)
        used = 0
        while streams.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result["timed_out"] = True
                break
            for key, _ in streams.select(min(0.1, remaining)):
                part = os.read(key.fileobj.fileno(), min(4096, KERNEL_CAP + 1 - used))
                if not part:
                    streams.unregister(key.fileobj)
                    continue
                used += len(part)
                result[key.data] += part
                if used > KERNEL_CAP:
                    result["overflow"] = True
                    break
            if result["overflow"]:
                break
        result["eof"] = not streams.get_map()
        if result["eof"]:
            proc.wait(timeout=max(0.001, deadline - time.monotonic()))
    except Exception as error:
        result["error"] = type(error).__name__
    finally:
        streams.close()
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                result["error"] = "unreaped log query"
            result["returncode"] = proc.returncode
            proc.stdout.close()
            proc.stderr.close()
    return result


def kernel_records(raw, pids):
    """Second exact-PID filter; neither kernel emitter PID nor PID substrings."""
    records, used, overflow = [], 2, False
    for line in raw.decode("utf-8", errors="replace").splitlines(keepends=True):
        match = DENIAL.search(line)
        if match is None or int(match[1]) not in pids:
            continue
        if not line.endswith("\n"):
            overflow = True  # Never present a truncated denial as complete.
            continue
        item = dict(pid=int(match[1]), line=line.rstrip("\r\n"))
        size = len(encoded(item).encode("ascii")) + 1
        if used + size > KERNEL_CAP:
            overflow = True
            break
        records.append(item)
        used += size
    return records, overflow


def crash_fields(raw, pids, now):
    """Apple IPS: one metadata JSON object followed by one report JSON object."""
    text = raw.decode("utf-8")
    decoder = json.JSONDecoder()
    metadata, offset = decoder.raw_decode(text.lstrip())
    rest = text.lstrip()[offset:].lstrip()
    report, end = decoder.raw_decode(rest)
    if rest[end:].strip() or not isinstance(metadata, dict) or not isinstance(report, dict):
        raise ValueError("IPS shape")
    pid = report.get("pid")
    name = report.get("procName")
    if type(pid) is not int or pid not in pids or not isinstance(name, str):
        return None
    if not name.startswith("python3"):
        return None
    captured = datetime.datetime.fromisoformat(report["captureTime"])
    if captured.tzinfo is None or not 0 <= now - captured.timestamp() <= 600:
        return None
    fields = {k: report[k] for k in ("termination", "asi") if k in report}
    if not fields or any(not isinstance(v, dict) for v in fields.values()):
        raise ValueError("IPS termination/ASI missing or malformed")
    # No raw report, stack, environment, binary images, path or incident metadata.
    return dict(pid=pid, **fields)


def crash_records(directory, pids, now, deadline):
    records, errors, seen, read_bytes, used = [], [], set(), 0, 2
    candidates = []
    try:
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries):
                if count >= 512 or time.monotonic() >= deadline:
                    raise ValueError("directory/time bound")
                if not (entry.name.startswith("python3") and entry.name.endswith(".ips")):
                    continue
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or not 0 <= now - info.st_mtime <= 600:
                    continue
                if len(candidates) >= 64:
                    raise ValueError("crash inventory bound")
                candidates.append(Path(entry.path))
    except Exception as error:
        errors.append(type(error).__name__)
    for path in sorted(candidates):
        try:
            if time.monotonic() >= deadline or read_bytes >= IPS_TOTAL:
                raise ValueError("crash total/time bound")
            raw = read_regular(path, min(IPS_CAP, IPS_TOTAL - read_bytes))
            read_bytes += len(raw)
            item = crash_fields(raw, pids, now)
            if item is None:
                continue
            size = len(encoded(item).encode("ascii")) + 1
            if used + size > CAP:
                raise ValueError("selected crash fields output bound")
            records.append(item)
            used += size
            seen.add(item["pid"])
        except Exception as error:
            errors.append(type(error).__name__)
            if len(errors) >= 16:
                break
    return dict(records=records, missing_pids=sorted(pids - seen),
                errors=errors, input_bytes=read_bytes,
                status="UNKNOWN" if errors or pids - seen else "FIELDS_COLLECTED")


def collect(observation):
    start, now = time.monotonic(), time.time()
    result = dict(schema="d01-startup-os-diagnostics/1", qualified=False,
                  observation="UNKNOWN", policy_changed=False, pids=[])
    try:
        selected = confined_pids(read_regular(observation, 256 * 1024))
        pids = set(selected.values())
        result["pids"] = [dict(case=k[0], operation=k[1], pid=v)
                          for k, v in sorted(selected.items())]
        output = capture(log_command(pids), min(start + 10, time.monotonic() + 10))
        records, overflow = kernel_records(output["stdout"], pids)
        incomplete = (output["overflow"] or output["timed_out"] or not output["eof"]
                      or output["returncode"] != 0 or "error" in output or overflow)
        result["kernel"] = dict(
            records=records, status="UNKNOWN" if incomplete or not records else "LINES_COLLECTED",
            returncode=output["returncode"], overflow=output["overflow"] or overflow,
            timed_out=output["timed_out"], eof=output["eof"], error=output.get("error"),
            query_stderr_present=bool(output["stderr"]))
        result["crash"] = crash_records(
            Path.home() / "Library/Logs/DiagnosticReports", pids, now, start + 30)
        result["limits"] = [
            "One log query; 512 KiB combined raw pipe cap and 512 KiB escaped selected-line cap",
            "IPS: 512 directory entries, 64 files, 2 MiB/file, 8 MiB input, 32 KiB escaped selected fields",
            "30-second collector budget; log query 10 seconds plus at most 1 second reap",
            "Ten-minute PID/time correlation is diagnostic, not birth-identity proof",
            "Missing, delayed, unavailable, truncated or silent diagnostics remain UNKNOWN",
            "No retries, sudo, sysctl changes, mach grants, sandbox changes or qualification"]
    except Exception as error:
        result["error"] = type(error).__name__
    return result


def main():
    if sys.platform != "darwin" or os.environ.get("GITHUB_ACTIONS") != "true" or len(sys.argv) != 3:
        raise SystemExit("hosted macOS CI and explicit input/output required")
    result = collect(Path(sys.argv[1]))
    public = encoded(result) + "\n"
    with Path(sys.argv[2]).open("x", encoding="ascii", newline="\n") as stream:
        stream.write(public)
    print(public, end="", flush=True)
    # Read-only diagnostic collection never replaces the observation verdict.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
