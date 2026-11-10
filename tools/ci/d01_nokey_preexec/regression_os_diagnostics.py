"""Separate exact 32-row/16-confined-PID inventory for regression diagnostics."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from os_diagnostics import collect, encoded

EXPECTED = {("S1", "none"), ("S2", "none")} | {("S1", operation) for operation in (
    "fork", "spawn", "exec-same", "exec-other", "mach-lookup", "ls-open",
    "raw-fork", "vfork", "spawn-suspended", "spawn-setexec", "raise-fork", "relax-fork",
    "concurrent-fork", "concurrent-spawn")}


def confined_pids(raw):
    report = json.loads(raw)
    if report.get("schema") != "d01-bound-worker-regression/1":
        raise ValueError("regression observation schema")
    rows = report.get("rows")
    if type(rows) is not list or len(rows) != 32:
        raise ValueError("regression observation inventory")
    inventory, selected = set(), {}
    for row in rows:
        key = (row.get("case"), row.get("operation"))
        policy = row.get("policy")
        item = (*key, policy)
        if key not in EXPECTED or policy not in ("baseline", "combined") or item in inventory:
            raise ValueError("regression exact paired inventory")
        inventory.add(item)
        if policy != "combined":
            continue
        frames = [f["message"] for f in row.get("frames", [])
                  if f.get("message", {}).get("kind") == "d01-preexec"]
        if len(frames) != 1:
            raise ValueError("regression preexec frame")
        frame = frames[0]
        pid = frame.get("pid")
        if (type(pid) is not int or not 0 < pid < 2**31 or frame.get("sandbox_rc") != 0 or
                frame.get("nproc") != [0, 0] or row.get("pid", pid) != pid or
                row.get("reaped") is not True):
            raise ValueError("regression confined PID/policy/reap")
        selected[key] = pid
    if set(selected) != EXPECTED or len(set(selected.values())) != 16:
        raise ValueError("regression incomplete or reused PID inventory")
    return selected


def main():
    if sys.platform != "darwin" or os.environ.get("GITHUB_ACTIONS") != "true" or len(sys.argv) != 3:
        raise SystemExit("hosted macOS CI and explicit input/output required")
    result = collect(Path(sys.argv[1]), inventory=confined_pids)
    result["input_schema"] = "d01-bound-worker-regression/1"
    public = encoded(result) + "\n"
    with Path(sys.argv[2]).open("x", encoding="ascii", newline="\n") as stream:
        stream.write(public)
    print(public, end="", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
