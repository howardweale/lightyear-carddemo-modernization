"""NO-KEY controlled spawn-tree diagnostics; NOT a production NativeProcessOwner.

Only these importable public workers can launch. Their creation identities are
spawn-instance observations, not OS birth-time attestations. Grandchild reap is
reported by its parent. No arbitrary executable, process discovery or PID kill.
An unobserved descendant/parent loss is UNKNOWN, never complete containment.
"""
import hashlib
import errno
import json
import math
import os
from pathlib import Path
from queue import Empty, Queue
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from threading import Event, Lock, Thread


CASES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7")
MAX_MESSAGE = 4096


class WorkerFault(Exception):
    """Fixed public reason only; never arbitrary worker exception text."""


class _Output:
    def send_bytes(self, raw):
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()

    def close(self):
        pass


class _StopPipe:
    def __init__(self):
        self.closed, self.invalid = Event(), False  # Thread event, never SemLock.
        Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        try:
            self.invalid = os.read(sys.stdin.fileno(), 1) != b""
        except OSError:
            self.invalid = True
        self.closed.set()

    def poll(self, timeout):
        return self.closed.wait(timeout)

    def recv_bytes(self, maximum):
        if self.invalid:
            raise ValueError("stop-channel-invalid")
        raise EOFError

    def close(self):
        pass


class _WorkerChannel:
    """Bounded public frames; a reader thread avoids platform-specific pipe poll."""
    def __init__(self, stream):
        self.stream, self.messages, self.pending = stream, Queue(16), None
        self.overflow = False
        self.thread = Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            while True:
                raw = self.stream.readline(MAX_MESSAGE + 2)
                item = raw[:-1] if raw.endswith(b"\n") and len(raw) <= MAX_MESSAGE + 1 else (
                    EOFError() if not raw else ValueError("worker-frame-invalid"))
                if self.messages.full():
                    self.overflow = True
                    return
                self.messages.put_nowait(item)
                if isinstance(item, Exception):
                    return
        except OSError as error:
            if not self.messages.full():
                self.messages.put_nowait(error)
            else:
                self.overflow = True

    def poll(self, timeout):
        if self.overflow:
            raise ValueError("worker-frame-overflow")
        if self.pending is None:
            try:
                self.pending = self.messages.get(timeout=timeout)
            except Empty:
                return False
        return True

    def recv_bytes(self, maximum):
        item, self.pending = self.pending, None
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, bytes) or len(item) > maximum:
            raise ValueError("worker-frame-invalid")
        return item

    def close(self):
        self.thread.join(timeout=0.1)
        self.stream.close()


class _OwnedWorker:
    def __init__(self, role, case, original_deadline, cleanup_deadline, *, preexec=None):
        self.argv = [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                     "--worker", role, case, str(original_deadline), str(cleanup_deadline)]
        self.process = self.channel = None
        self._preexec = preexec  # Explicit CI-only opt-in; default launcher is unchanged.

    @property
    def pid(self):
        return None if self.process is None else self.process.pid

    @property
    def exitcode(self):
        return None if self.process is None else self.process.poll()

    def start(self):
        if self._preexec is not None:
            from .mac_owner_preexec import PreExecBinding
            if type(self._preexec) is not PreExecBinding:
                raise ValueError("d01-preexec-binding-required")
            argv = self._preexec.command(self.argv)
            self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=(subprocess.DEVNULL if self._preexec.stderr_fd is None
                        else self._preexec.stderr_fd),
                close_fds=True, pass_fds=(self._preexec.witness_fd,),
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"})
        else:
            self.process = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, close_fds=True)
        self.channel = _WorkerChannel(self.process.stdout)

    def request_stop(self):
        if self.process is not None:
            self.process.stdin.close()

    def join(self, timeout):
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass

    def is_alive(self):
        return self.exitcode is None

    def terminate(self):
        self.process.terminate()  # Only this owned Popen handle, never a supplied PID.

    def close(self):
        self.request_stop()
        if self.channel is not None:
            self.channel.close()


def _send(channel, kind, **fields):
    channel.send_bytes(json.dumps(dict(kind=kind, **fields), sort_keys=True).encode("ascii"))


def _receive(channel):
    try:
        raw = channel.recv_bytes(MAX_MESSAGE)
    except OSError as error:
        if _closed_channel(error):
            raise EOFError from error
        raise
    message = json.loads(raw)
    if type(message) is not dict or type(message.get("kind")) is not str:
        raise ValueError("worker-protocol-invalid")
    return message


def _closed_channel(error):
    return (isinstance(error, BrokenPipeError) or getattr(error, "winerror", None) == 109
            or error.errno == errno.EPIPE)


def _poll(channel, timeout):
    """Normalize only Windows' closed-writer poll result to stream EOF.

    CPython 3.12 PipeConnection.poll uses PeekNamedPipe, which can raise
    ERROR_BROKEN_PIPE before recv_bytes gets its chance to report EOFError.
    EOF is never itself evidence of process exit, scope or successful cleanup.
    """
    try:
        return channel.poll(timeout)
    except OSError as error:
        if _closed_channel(error):
            raise EOFError from error
        raise


def _identity(role):
    pid, parent = os.getpid(), os.getppid()
    created = time.monotonic_ns()
    return dict(role=role, pid=pid, parent_pid=parent,
                creation_identity=hashlib.sha256(f"{role}:{pid}:{parent}:{created}".encode()).hexdigest())


def _stop_requested(channel, timeout):
    """The owner closes its sole writer; no semaphore/resource-tracker process."""
    try:
        if _poll(channel, timeout):
            channel.recv_bytes(1)
            raise ValueError("stop-channel-data-refused")
        return False
    except EOFError:
        return True


def _grandchild(channel, stop, cleanup_deadline):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        _send(channel, "identity", **_identity("grandchild"))
        while not _stop_requested(stop, 0.02) and time.monotonic() < cleanup_deadline - 1:
            pass
    finally:
        stop.close()
        channel.close()


def _worker(channel, stop, case, original_deadline, cleanup_deadline, *, before_complete=None):
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
            grand = _OwnedWorker("grandchild", case, original_deadline, cleanup_deadline)
            grand.start()
            grand_channel = grand.channel
            if not _poll(grand_channel, max(0, original_deadline - time.monotonic())):
                raise ValueError("grandchild-ready-missing")
            observed = _receive(grand_channel)
            if (observed.get("kind") != "identity" or observed.get("role") != "grandchild"
                    or observed.get("pid") != grand.pid or observed.get("parent_pid") != os.getpid()):
                raise ValueError("grandchild-identity-mismatch")
            _send(channel, "identity", **{k: v for k, v in observed.items() if k != "kind"})
        _send(channel, "ready")
        if before_complete is not None:
            before_complete()
        if case not in ("S5", "S6"):
            _send(channel, "completed")
        while not _stop_requested(stop, 0.02) and time.monotonic() < cleanup_deadline - 1:
            pass
    except BaseException:
        # No traceback, path, environment or arbitrary exception content returned.
        try:
            _send(channel, "worker-failed")
        except (OSError, EOFError):
            pass
    finally:
        if grand is not None and grand.pid is not None:
            grand.request_stop()
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
        stop.close()
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
        child = _OwnedWorker("child", self.case, original_deadline, cleanup_deadline)
        reader = None
        identities, ready, completed, grand_reap = {}, False, False, None
        reason, storage_failed, forced, cleanup_requested = "unknown", False, False, False
        observation_failed = False
        cleanup_fault, channel_closed = None, False

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
            event("intent", owner_pid=self._pid, start_method="fixed-subprocess", native_proof=False)
            if time.monotonic() >= original_deadline:
                raise WorkerFault("original-deadline-before-launch")
            child.start()
            reader = child.channel
            while True:
                if time.monotonic() >= original_deadline:
                    reason = "original-deadline-reached"
                    break
                if self.cancel_requested():
                    reason = "operator-cancelled"
                    break
                if _poll(reader, min(0.02, max(0, original_deadline - time.monotonic()))):
                    if time.monotonic() >= original_deadline:
                        reason = "original-deadline-reached"
                        break
                    consume(_receive(reader))
                if completed:
                    reason = "completed"
                    break
        except KeyboardInterrupt:
            reason = "operator-cancelled"
        except WorkerFault as error:
            reason = str(error)
        except EOFError:
            channel_closed = True
            reason = ("original-deadline-reached" if time.monotonic() >= original_deadline
                      else "worker-exited-before-completion")
        except BaseException:
            observation_failed = True
            reason = "journal-failed" if storage_failed else "launch-or-worker-fault"
        finally:
            # One request, no new deadline. Reap remains mandatory on every path.
            cleanup_requested = True
            child.request_stop()
            try:
                event("cleanup-requested", reason=reason)
                while not channel_closed and child.pid is not None and time.monotonic() < cleanup_deadline - 0.5:
                    try:
                        if _poll(reader, 0.02):
                            consume(_receive(reader))
                    except EOFError:
                        break
            except BaseException:
                observation_failed = True
                cleanup_fault = "journal-failed" if storage_failed else "cleanup-observation-unknown"
                # Retain the first fault/cancellation; cleanup has its own evidence.
                if reason in ("unknown", "completed"):
                    reason = cleanup_fault
            finally:
                if child.pid is not None:
                    child.join(max(0, cleanup_deadline - 0.5 - time.monotonic()))
                    if child.is_alive():
                        forced = True
                        child.terminate()
                        child.join(max(0, cleanup_deadline - time.monotonic()))
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
                      cleanup_fault=cleanup_fault,
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


if __name__ == "__main__":
    # Internal fixed worker entrypoint; no arbitrary command/module/path accepted.
    d01 = None
    d01_native = None
    if len(sys.argv) == 12 and sys.argv[10] == "--d01-native-sha256":
        d01_native = sys.argv[11]
        if len(d01_native) != 64 or any(c not in "0123456789abcdef" for c in d01_native):
            raise SystemExit(2)
        sys.argv = sys.argv[:10]
    if len(sys.argv) == 10 and sys.argv[6] == "--d01-probe":
        d01 = tuple(sys.argv[7:])
        sys.argv = sys.argv[:6]
    if len(sys.argv) != 6 or sys.argv[1] != "--worker" or sys.argv[2] not in ("child", "grandchild"):
        raise SystemExit(2)
    role, case = sys.argv[2:4]
    original, cleanup = map(float, sys.argv[4:6])
    if case not in CASES or not all(map(math.isfinite, (original, cleanup))) or cleanup != original + 5:
        raise SystemExit(2)
    hook = None
    if d01 is not None:
        # Combined mode starts ALREADY confined by the owner-launched C helper.
        # Only opt-in observations/attempts: regression raise/relax calls are
        # adversarial attempts under the inherited policy, never setup/approval.
        import runpy
        probe = runpy.run_path(str(Path(__file__).with_name("mac_owner_preexec_probe.py")))
        operation, descriptor, app = d01
        fd = int(descriptor)
        if role != "child" or case not in ("S1", "S2") or operation not in probe["OPERATIONS"]:
            raise SystemExit(2)
        _send(_Output(), "d01-entry", **probe["entry"](fd))
        if operation != "none":
            def hook():
                _send(_Output(), "d01-attempt", **probe["attempt"](operation, fd, app, native_sha256=d01_native, original=original, cleanup=cleanup))
    stop, output = _StopPipe(), _Output()
    if role == "grandchild":
        _grandchild(output, stop, cleanup)
    else:
        if hook is None:
            _worker(output, stop, case, original, cleanup)
        else:
            _worker(output, stop, case, original, cleanup, before_complete=hook)
