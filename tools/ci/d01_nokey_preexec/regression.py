"""Independent CI-only 240-second regression experiment; no containment claim."""
import errno
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observe import collect, sha, ROOT
from lightyear_execution.mac_owner_preexec import ORIGINAL_OPERATIONS, NATIVE_OPERATIONS

REFUSALS = (errno.EPERM, errno.EACCES, errno.EAGAIN)


def classify(attempt, witness, policy, pid, parent_pid, digest):
    operation = attempt.get("operation")
    if operation == "spawn-setexec" and policy == "baseline":
        raise ValueError("SETEXEC control must replace the same worker image, not return a child")
    concurrent = operation in ("concurrent-fork", "concurrent-spawn")
    expected = [(thread, iteration) for thread in range(4) for iteration in range(4)] if concurrent else [(0, 0)]
    records = attempt.get("attempts")
    if (operation not in NATIVE_OPERATIONS or attempt.get("pid") != pid or
            attempt.get("parent_pid") != parent_pid or attempt.get("native_sha256") != digest or
            attempt.get("internal_error") != 0 or
            attempt.get("ready_threads") != (4 if concurrent else 0) or
            type(records) is not list or len(records) != len(expected)):
        raise ValueError("native inventory, identity or completion missing")
    if [(r.get("thread"), r.get("iteration")) for r in records] != expected:
        raise ValueError("native thread/iteration inventory mismatch")
    before, after = attempt.get("nproc_before"), attempt.get("nproc_after")
    if (type(before) is not list or len(before) != 2 or
            any(type(n) is not int or n < 0 for n in before) or
            type(after) is not list or len(after) != 2):
        raise ValueError("native limit inventory malformed")
    if policy == "combined" and (before != [0, 0] or after != [0, 0]):
        raise ValueError("native zero limit changed or missing")
    if operation == "raise-fork":
        request = attempt.get("requested_nproc")
        if policy == "baseline":
            if (request != [before[1], before[1]] or before[1] == 0 or
                    attempt.get("raise_rc") != 0 or after != request):
                raise ValueError("baseline limit setter control missing")
        elif (request != [1, 1] or attempt.get("raise_rc") != -1 or
              attempt.get("raise_errno") not in (errno.EPERM, errno.EACCES)):
            raise ValueError("hard-limit raise refusal missing")
    elif after != before:
        raise ValueError("unexpected native limit change")
    if operation == "relax-fork":
        if policy == "baseline" and attempt.get("relax_rc") != 0:
            raise ValueError("baseline policy setter control missing")
        if policy == "combined" and (attempt.get("relax_rc") != -1 or
                attempt.get("relax_errno") not in (errno.EPERM, errno.EACCES)):
            raise ValueError("sandbox relaxation refusal unproved; zero NPROC masks policy effect")
    children = []
    for record in records:
        if record.get("error") != 0 or record.get("forced") is not False or record.get("kill_status") != -1:
            raise ValueError("native forced cleanup or per-attempt error")
        status, child = record.get("status"), record.get("child")
        if type(status) is not int:
            raise ValueError("native API status missing")
        if policy == "baseline":
            wait = record.get("wait_status")
            if (status != 0 or type(child) is not int or child <= 0 or child == pid or
                    record.get("reaped") is not True or type(wait) is not int or
                    not os.WIFEXITED(wait) or os.WEXITSTATUS(wait) != 17 or
                    (operation == "spawn-suspended" and record.get("resume_status") != 0)):
                raise ValueError("native creation control/reap missing")
            children.append(child)
        elif (status not in REFUSALS or child is not None or record.get("reaped") is not False or
              record.get("wait_status") is not None or record.get("resume_status") is not None):
            raise ValueError("native explicit refusal or no-child accounting missing")
    if policy == "baseline":
        if len(set(children)) != len(expected) or witness != b"X" * len(expected):
            raise ValueError("native distinct children or independent witness missing")
        return "POSITIVE_CONTROL_OBSERVED"
    if witness:
        raise ValueError("native child witness observed")
    return "KERNEL_REFUSAL_OBSERVED"


def require_controls(rows):
    controls = {(r["case"], r["operation"]): r["observation"] for r in rows if r["policy"] == "baseline"}
    normal = {(r["case"], r["policy"]): r["observation"] for r in rows if r["operation"] == "none"}
    for row in rows:
        if controls.get((row["case"], row["operation"])) not in ("NORMAL_WORK_OBSERVED", "POSITIVE_CONTROL_OBSERVED"):
            row.update(observation="UNKNOWN", control="matching unrestricted control missing")
        if row["operation"] != "none" and any(normal.get(("S1", policy)) != "NORMAL_WORK_OBSERVED"
                                              for policy in ("baseline", "combined")):
            row.update(observation="UNKNOWN", normal_work="normal S1 completion missing")

def main():
    if len(sys.argv) != 3 or sys.platform != "darwin" or not os.getuid():
        raise SystemExit("non-root macOS CI and two paths required")
    launcher, output = Path(sys.argv[1]).resolve(strict=True), Path(sys.argv[2])
    helper = Path(sys.base_prefix).resolve(strict=True) / "lib/d01-regression.dylib"
    digest = sha(helper)
    root = Path(tempfile.mkdtemp(prefix="d01-bound-regression-")).resolve()
    deadline = time.monotonic() + 240  # Separate experiment; never renew a row/old experiment deadline.
    cases = [(case, "none") for case in ("S1", "S2")]
    cases += [("S1", operation) for operation in ORIGINAL_OPERATIONS[1:] + NATIVE_OPERATIONS]
    rows, watched = [], []
    for case, operation in cases:
        for policy in ("baseline", "combined"):
            row, witness = collect(launcher, root, case, operation, policy, deadline,
                native_sha256=digest, native_classifier=classify)
            rows.append(row)
            watched.append((row, witness))
    for row, witness in watched:
        if row["policy"] == "combined" and witness.exists():
            row.update(observation="UNKNOWN", error="late launch witness")
    require_controls(rows)
    report = dict(schema="d01-bound-worker-regression/1", rows=rows, qualified=False,
        diagnostic_only=True, closed_creation_established=False, native_proof=False,
        production_workload_proof=False, owner_death="UNKNOWN", guardian_death="UNKNOWN",
        launcher_sha256=sha(launcher), native_sha256=digest,
        worker_sha256=sha(ROOT / "src/lightyear_execution/mac_owner_process.py"),
        limits=["Separate 240-second CI experiment, fixed 15-second rows plus original 5-second cleanup",
                "Native concurrent threads created after worker entry: post-policy samples, not installation races",
                "Raise baseline requests existing hard limit; confined row requests [1,1] from [0,0]",
                "A successful sandbox_init call plus failed fork does not prove policy relaxation was refused",
                "Exact-interpreter or SETEXEC image replacement is UNKNOWN/red under confinement",
                "All negative LaunchServices statuses remain UNKNOWN; no denial point isolated",
                "Parent/worker helper SHA checks do not close mutable-filesystem, loader or birth-identity races",
                "Owner/guardian death, inherited services, actual workload and all-process cleanup remain unproved"])
    output.write_text(json.dumps(report, indent=2) + "\n")
    for row in rows:
        print(json.dumps(row, sort_keys=True), flush=True)
    if len(rows) != 32 or any(row["observation"] == "UNKNOWN" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
