"""Capture CI tool output without forwarding source or diagnostics to logs."""
import os
from pathlib import Path
import subprocess
import tempfile


class CaptureRefused(ValueError):
    """Fixed codes only; never interpolate a command, path, output or exception."""


def capture(command, cwd, timeout=600, limit=64 * 1024 * 1024):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise CaptureRefused("ci-only")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise CaptureRefused("command-schema")
    if not 1 <= timeout <= 3600 or not 1 <= limit <= 128 * 1024 * 1024:
        raise CaptureRefused("capture-bounds")
    # Temporary raw streams are never artifacts. File-backed capture avoids
    # unbounded memory; fixed diagnostic codes prevent accidental traceback leaks.
    with tempfile.TemporaryDirectory(prefix="p1-capture-") as temp:
        stdout, stderr = Path(temp) / "stdout", Path(temp) / "stderr"
        try:
            with stdout.open("wb") as out, stderr.open("wb") as err:
                result = subprocess.run(command, cwd=cwd, stdout=out, stderr=err,
                                        timeout=timeout, check=False, shell=False)
            if stdout.stat().st_size > limit or stderr.stat().st_size > limit:
                raise CaptureRefused("capture-output-limit")
            return result.returncode, stdout.read_bytes(), stderr.read_bytes()
        except CaptureRefused:
            raise
        except (OSError, subprocess.SubprocessError):
            raise CaptureRefused("capture-failed") from None
