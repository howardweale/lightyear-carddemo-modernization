"""NO-KEY controlled spawn-tree diagnostics; NOT a production NativeProcessOwner.

Only these importable public workers can launch. Their creation identities are
spawn-instance observations, not OS birth-time attestations. Grandchild reap is
reported by its parent. No arbitrary executable, process discovery or PID kill.
An unobserved descendant/parent loss is UNKNOWN, never complete containment.
"""
import hashlib
import json
import math
import multiprocessing
import os
import signal
import time
from datetime import datetime, timezone
from threading import Lock


CASES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7")
MAX_MESSAGE = 4096


class WorkerFault(Exception):
    """Fixed public reason only; never arbitrary worker exception text."""


def _send(channel, kind, **fields):
    channel.send_bytes(json.dumps(dict(kind=kind, **fields), sort_keys=True).encode("ascii"))


def _receive(channel):
    raw = channel.recv_bytes(MAX_MESSAGE)
    message = json.loads(raw)
    if type(message) is not dict or type(message.get("kind")) is not str:
        raise ValueError("worker-protocol-invalid")
    return message


def _identity(role):
    pid, parent = os.getpid(), os.getppid()
    created = time.monotonic_ns()
    return dict(role=role, pid=pid, parent_pid=parent,
                creation_identity=hashlib.sha256(f"{role}:{pid}:{parent}:{created}".encode()).hexdigest())


def _grandchild(channel, stop, cleanup_deadline):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        _send(channel, "identity", **_identity("grandchild"))
        while not stop.wait(0.02) and time.monotonic() < cleanup_deadline - 1:
            pass
    finally:
        channel.close()


def _worker(channel, stop, case, original_deadline, cleanup_deadline):
    """Fixed cooperative fixture, with autonomous bound if its owner disappears."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    grand = grand_channel = None
    try:
        _send(channel, "identity", **_identity("child"))
        if time.monotonic() >= original_deadline:
            _send(channel, "deadline-before-ready")
            return
        if case == "S4":
            _send(channel, "initialization-failed")
            return
        if case == "S3":
            context = multiprocessing.get_context("spawn")
            grand_channel, sender = context.Pipe(duplex=False)
            grand = context.Process(target=_grandchild, args=(sender, stop, cleanup_deadline))
            grand.start()
            sender.close()
            if not grand_channel.poll(max(0, original_deadline - time.monotonic())):
                raise ValueError("grandchild-ready-missing")
            observed = _receive(grand_channel)
            if (observed.get("kind") != "identity" or observed.get("role") != "grandchild"
                    or observed.get("pid") != grand.pid or observed.get("parent_pid") != os.getpid()):
                raise ValueError("grandchild-identity-mismatch")
            _send(channel, "identity", **{k: v for k, v in observed.items() if k != "kind"})
        _send(channel, "ready")
        if case not in ("S5", "S6"):
            _send(channel, "completed")
        while not stop.wait(0.02) and time.monotonic() < original_deadline:
            pass
    except BaseException:
        # No traceback, path, environment or arbitrary exception content returned.
        try:
            _send(channel, "worker-failed")
        except (OSError, EOFError):
            pass
    finally:
        stop.set()
        if grand is not None and grand.pid is not None:
            grand.join(max(0, cleanup_deadline - 1 - time.monotonic()))
            if grand.is_alive():
                grand.terminate()  # Only this positively owned Process handle.
                grand.join(max(0, cleanup_deadline - time.monotonic()))
            try:
                _send(channel, "grandchild-reap", pid=grand.pid,
                      reaped=grand.exitcode is not None, exitcode=grand.exitcode)
            except (OSError, EOFError):
                pass
            if grand.exitcode is not None:
                grand.close()
        if grand_channel is not None:
            grand_channel.close()
        channel.close()


class RehearsalProcessOwner:
    """Single attempt, original execution deadline plus predeclared cleanup bound.

    The cleanup bound never permits further work or an in-window success. Only
    fixed workers are supported. Missing observations, forced parent termination
    or arbitrary scope cannot produce a production typed scope observation.
    emit must durably retain public events; a write failure consumes the attempt.
    """
    def __init__(self, *, case, duration, emit, cancel_requested=lambda: False):
        if case not in CASES or type(duration) not in (int, float) or not math.isfinite(duration):
            raise ValueError("rehearsal-arguments-invalid")
        if not 1 <= duration <= 60 or not callable(emit) or not callable(cancel_requested):
            raise ValueError("rehearsal-arguments-invalid")
        self.case, self.duration, self.emit = case, duration, emit
        self.cancel_requested = cancel_requested
        self._consumed, self._lock, self._pid = False, Lock(), os.getpid()

    def run_once(self):
        with self._lock:
            if self._consumed or os.getpid() != self._pid:
                raise ValueError("rehearsal-consumed-no-resume")
            self._consumed = True
        started = time.monotonic()
        original_deadline, cleanup_deadline = started + self.duration, started + self.duration + 5
        context = multiprocessing.get_context("spawn")
        stop = context.Event()
        reader, sender = context.Pipe(duplex=False)
        child = context.Process(target=_worker, args=(sender, stop, self.case, original_deadline, cleanup_deadline))
        identities, ready, completed, grand_reap = {}, False, False, None
        reason, storage_failed, forced, cleanup_requested = "unknown", False, False, False
        observation_failed = False

        def event(kind, **fields):
            nonlocal storage_failed
            try:
                self.emit(dict(kind=kind, case=self.case, original_deadline=original_deadline,
                               cleanup_deadline=cleanup_deadline, monotonic=time.monotonic(),
                               wall_time=datetime.now(timezone.utc).isoformat(), **fields))
            except BaseException:
                storage_failed = True
                raise

        def consume(message):
            nonlocal ready, completed, grand_reap
            kind = message["kind"]
            if kind == "identity":
                role = message.get("role")
                expected_parent = self._pid if role == "child" else child.pid
                identity = message.get("creation_identity")
                if (set(message) != {"kind", "role", "pid", "parent_pid", "creation_identity"}
                        or role not in (("child", "grandchild") if self.case == "S3" else ("child",))
                        or role in identities or ready or type(message["pid"]) is not int
                        or message["pid"] <= 0 or message["parent_pid"] != expected_parent
                        or (role == "child" and message["pid"] != child.pid)
                        or (role == "grandchild" and "child" not in identities)
                        or any(v["pid"] == message["pid"] for v in identities.values())
                        or type(identity) is not str or len(identity) != 64
                        or any(c not in "0123456789abcdef" for c in identity)):
                    raise ValueError("worker-identity-unknown")
                identities[role] = message
            elif kind == "ready":
                if set(message) != {"kind"} or ready or len(identities) != (2 if self.case == "S3" else 1):
                    raise ValueError("worker-ready-invalid")
                ready = True
            elif kind == "completed":
                if set(message) != {"kind"} or not ready or completed or self.case in ("S4", "S5", "S6"):
                    raise ValueError("worker-completion-invalid")
                completed = True
            elif kind == "grandchild-reap":
                if (set(message) != {"kind", "pid", "reaped", "exitcode"} or grand_reap is not None
                        or "grandchild" not in identities or message["pid"] != identities["grandchild"]["pid"]
                        or message["reaped"] is not True or type(message["exitcode"]) is not int):
                    raise ValueError("grandchild-reap-unknown")
                grand_reap = message
            elif kind in ("initialization-failed", "worker-failed", "deadline-before-ready") and set(message) == {"kind"}:
                event("worker-observation", observation=message)
                raise WorkerFault(kind)
            else:
                raise ValueError("worker-fault-or-protocol-invalid")
            event("worker-observation", observation=message)

        try:
            event("intent", owner_pid=self._pid, start_method="spawn", native_proof=False)
            if time.monotonic() >= original_deadline:
                raise WorkerFault("original-deadline-before-launch")
            child.start()
            sender.close()
            while True:
                if time.monotonic() >= original_deadline:
                    reason = "original-deadline-reached"
                    break
                if self.cancel_requested():
                    reason = "operator-cancelled"
                    break
                if reader.poll(min(0.02, max(0, original_deadline - time.monotonic()))):
                    consume(_receive(reader))
                if completed:
                    reason = "completed"
                    break
                if child.exitcode is not None:
                    reason = "worker-exited-before-completion"
                    break
        except KeyboardInterrupt:
            reason = "operator-cancelled"
        except WorkerFault as error:
            reason = str(error)
        except BaseException:
            observation_failed = True
            reason = "journal-failed" if storage_failed else "launch-or-worker-fault"
        finally:
            # One request, no new deadline. Reap remains mandatory on every path.
            cleanup_requested = True
            stop.set()
            try:
                event("cleanup-requested", reason=reason)
                while child.pid is not None and time.monotonic() < cleanup_deadline - 0.5:
                    if reader.poll(0.02):
                        try:
                            consume(_receive(reader))
                        except EOFError:
                            break
                    elif child.exitcode is not None:
                        break
            except BaseException:
                observation_failed = True
                reason = "journal-failed" if storage_failed else "cleanup-observation-unknown"
            finally:
                if child.pid is not None:
                    child.join(max(0, cleanup_deadline - 0.5 - time.monotonic()))
                    if child.is_alive():
                        forced = True
                        child.terminate()
                        child.join(max(0, cleanup_deadline - time.monotonic()))
                sender.close()
                reader.close()
        reaped = child.pid is not None and child.exitcode is not None
        exitcode = child.exitcode if child.pid is not None else None
        # S7 removes the observation, not cleanup itself. It must remain UNKNOWN.
        observed_reap = reaped and self.case != "S7"
        scope_known = (len(identities) == (2 if self.case == "S3" else 1)
                       and (self.case != "S3" or (grand_reap is not None and grand_reap["exitcode"] == 0)))
        cleanup_known = observed_reap and exitcode == 0 and scope_known and not forced and not observation_failed
        passed = (reason == "completed" and ready and completed and cleanup_known
                  and time.monotonic() < original_deadline and not storage_failed)
        result = dict(status="PASS" if passed else "FAIL", reason=reason,
                      cleanup_status="REAPED" if cleanup_known else "UNKNOWN",
                      cleanup_requested=cleanup_requested, child_exitcode=exitcode,
                      child_reap_observed=observed_reap, forced_parent_termination=forced,
                      identities=list(identities.values()), grandchild_reap=grand_reap,
                      scope="fixed-cooperative-rehearsal-only", native_proof=False,
                      admission_authorized=False, restart_authorized=False)
        if reaped:
            child.close()
        event("result", **result)
        return result
