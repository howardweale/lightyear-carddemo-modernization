"""D06 public feasibility fixture: separate safety ownership and S7 classification.

Not an operator command, production owner, receipt or authenticated proof. The
supervisor owns two fixed public children; neither can spawn descendants. The
diagnostic child deliberately lacks reap evidence. Only the separate supervisor
holds process handles. Integration into the reviewed S7 bundle remains required.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
import time


S7 = dict(case="S7", status="FAIL", cleanup_status="UNKNOWN", observation="withheld")
MAX_OUTPUT = 512


def _remaining(deadline):
    return max(0.0, deadline - time.monotonic())


def _start(role, cleanup_deadline):
    return subprocess.Popen(
        [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
         "--fixture-child", role, str(cleanup_deadline)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        close_fds=True)


def _finish(process, deadline):
    raw, _ = process.communicate(input=b"", timeout=_remaining(deadline))
    if len(raw) > MAX_OUTPUT:
        raise ValueError("bounded-output-required")
    return raw


def run_public_fixture(duration=5):
    """CI-only feasibility exercise; never grants operator execution authority."""
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 1 <= duration <= 60:
        raise ValueError("duration-refused")
    started = time.monotonic()
    original, cleanup = started + duration, started + duration + 5
    owned, outputs, forced = {}, {}, set()
    first_fault = None
    try:
        owned["worker"] = _start("worker", cleanup)
        owned["observer"] = _start("observer", cleanup)
        outputs["observer"] = _finish(owned["observer"], original)
        if json.loads(outputs["observer"]) != S7:
            raise ValueError("diagnostic-mismatch")
        if time.monotonic() >= original:
            first_fault = "original-deadline-reached"
    except KeyboardInterrupt:
        first_fault = "cancelled"
    except BaseException:
        first_fault = "diagnostic-or-launch-failed"
    finally:
        # Never recalculate a deadline; every started handle remains owned.
        for role, process in owned.items():
            try:
                if role not in outputs:
                    outputs[role] = _finish(process, cleanup)
            except BaseException:
                if first_fault is None:
                    first_fault = "closeout-observation-failed"
                if process.poll() is None:
                    forced.add(role)
                    try:
                        process.terminate()
                        _finish(process, cleanup)
                    except BaseException:
                        pass  # Retain unknown exit below, never fabricate reap.
    handles = [dict(role=role, pid=p.pid, exitcode=p.poll(), reaped=p.poll() is not None)
               for role, p in owned.items()]
    safety_known = (
        first_fault is None and set(owned) == {"worker", "observer"} and not forced
        and all(row["reaped"] and row["exitcode"] == 0 for row in handles)
        and outputs.get("worker") == b"PUBLIC-WORKER-EXIT\n"
        and time.monotonic() < cleanup)
    return dict(
        diagnostic=dict(S7), safety_status="OBSERVED_EXIT" if safety_known else "UNKNOWN",
        first_fault=first_fault, forced_roles=sorted(forced), processes=handles,
        original_deadline=original, cleanup_deadline=cleanup,
        supervisor_pid=os.getpid(), observation_scope="two-fixed-public-children-only",
        independence="separate supervisor handles, not authenticated or separate OS custody",
        native_proof=False, admission_authorized=False, restart_authorized=False,
        operator_packet_bound=False)


def _fixture_child(role, cleanup_deadline):
    if role == "observer":
        print(json.dumps(S7), flush=True)
        return
    if role != "worker":
        raise ValueError("fixed-role-required")
    closed = Event()  # Thread synchronization only; no multiprocessing tracker.
    def watch():
        try:
            os.read(sys.stdin.fileno(), 1)
        finally:
            closed.set()
    Thread(target=watch, daemon=True).start()
    while not closed.wait(0.01) and time.monotonic() < cleanup_deadline - 1:
        pass
    sys.stdout.buffer.write(b"PUBLIC-WORKER-EXIT\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--fixture-child":
        raise SystemExit(2)
    deadline = float(sys.argv[3])
    if not math.isfinite(deadline):
        raise SystemExit(2)
    _fixture_child(sys.argv[2], deadline)
