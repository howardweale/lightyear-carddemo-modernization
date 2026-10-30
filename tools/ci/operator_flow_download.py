"""Bounded stdout collection for the fixed public artifact GET subprocess.

No artifact, proof or admission authority is returned. The caller owns the
fixed command and subsequent original byte/digest/service checks. This bounds
our retained output, not the helper's own memory, network traffic or children.
"""
import math
import subprocess
import threading
import time


def _capture_bounded_stdout(command, *, max_bytes, timeout):
    if (type(max_bytes) is not int or not 0 < max_bytes <= 4 * 1024 * 1024
            or type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 45):
        raise ValueError('handoff-download-limits')
    # No shell, stdin or stderr capture. In particular, a diagnostic flood
    # cannot allocate an unbounded second capture buffer or expose credentials.
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False,
        close_fds=True)
    # Process creation itself may block in the OS; do not claim a total duration.
    deadline = time.monotonic() + timeout
    finished = threading.Event()
    data = bytearray()
    errors = []

    def read_stdout():
        try:
            while True:
                # One extra byte detects overflow; never collect beyond it.
                chunk = process.stdout.read1(min(65536, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    errors.append('handoff-download-overflow')
                    break
        except Exception:
            errors.append('handoff-download-read-failed')
        finally:
            try:
                process.stdout.close()
            except Exception:
                errors.append('handoff-download-close-failed')
            finally:
                finished.set()

    reader = threading.Thread(target=read_stdout, daemon=True)
    started = False
    try:
        reader.start()
        started = True
        if not finished.wait(max(0, deadline - time.monotonic())):
            raise ValueError('handoff-download-timeout')
        if errors:
            raise ValueError(errors[0])
        try:
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise ValueError('handoff-download-timeout') from None
        if code != 0:
            raise ValueError('handoff-download-exit')
        return bytes(data)
    finally:
        # Only the original download helper is stopped. Never retry a GET or
        # kill an unrelated process. No process-tree/death assurance is made.
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise ValueError('handoff-download-reap-unavailable') from None
        if started:
            reader.join(timeout=5)
            if reader.is_alive():
                # A descendant retaining the pipe cannot make us wait forever.
                # Its reader remains daemonized and bounded; refuse all output.
                raise ValueError('handoff-download-reader-unavailable')
        else:
            process.stdout.close()
