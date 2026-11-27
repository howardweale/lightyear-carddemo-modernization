"""Exercise the production key owner on a controlling PTY with a public marker only."""
import argparse
from contextlib import nullcontext
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import termios
import time
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
PROMPT = b"API key (hidden): "
MARKER = b"PUBLIC-SYNTHETIC-PTY-MARKER"
OLD_PROVIDER = "586e9d2b6639b472173443fac6280333e87a813a9668028f9a9cbf8a09974259"


def child(mode, baseline):
    # Popen starts a new session. Acquire its slave as the controlling terminal
    # before getpass opens /dev/tty independently of the supplied output stream.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    sys.path.insert(0, str(ROOT / "src"))
    if baseline:
        if hashlib.sha256(baseline.read_bytes()).hexdigest() != OLD_PROVIDER:
            raise ValueError("wrong frozen provider")
        spec = importlib.util.spec_from_file_location("frozen_provider", baseline)
        provider = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(provider)
    else:
        from lightyear_factory import public_repair_provider as provider

    pipe = Mock()
    request = dict(path=provider.COUNT, body="{}", timeout_ms=1000)
    pipe.recv_bytes.side_effect = [json.dumps(request).encode(), EOFError()]
    fallback = mode == "fallback"
    control = patch.object(termios, "tcsetattr", side_effect=termios.error("synthetic")) if fallback else nullcontext()
    with control as fault, patch.object(provider, "https_once", return_value=(200, b"ok")) as transport:
        provider.key_owner(pipe)
    replies = [call.args[0] for call in pipe.send_bytes.call_args_list]
    pipe.close.assert_called_once_with()
    if fallback:
        assert fault.called, "did not reach echo control"
    if baseline or fallback:
        transport.assert_not_called()
        assert replies == [b"FAULT"], "owner did not refuse before READY"
    else:
        transport.assert_called_once_with(provider.COUNT, b"{}", MARKER.decode(), 1.0)
        # EOF after the synthetic request exercises normal owner teardown.
        assert replies == [b"READY", b"\x00\xc8ok", b"FAULT"]


def exercise(mode, baseline=None):
    master, slave = pty.openpty()
    args = [sys.executable, "-I", "-B", __file__, "--child", mode]
    if baseline:
        args.extend(["--baseline", str(baseline)])
    try:
        proc = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    except BaseException:
        os.close(master)
        raise
    finally:
        os.close(slave)
    transcript = bytearray()
    sent = False
    end = time.monotonic() + 20
    try:
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0 or not select.select([master], [], [], remaining)[0]:
                raise AssertionError("timed out waiting for PTY")
            try:
                part = os.read(master, 4096)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                break
            if not part:
                break
            transcript.extend(part)
            if len(transcript) > 16384:
                raise AssertionError("unexpected PTY output")
            if PROMPT in transcript and not sent:
                assert mode == "success" and baseline is None, "unexpected prompt on refusal"
                assert not termios.tcgetattr(master)[3] & termios.ECHO, "input echo is enabled"
                os.write(master, MARKER + b"\n")
                sent = True
        assert proc.wait(timeout=5) == 0, "key-owner protocol assertion failed"
        assert MARKER not in transcript, "synthetic input was echoed"
        if mode == "success" and baseline is None:
            assert sent and transcript.count(PROMPT) == 1, "expected one hidden prompt"
        else:
            assert not sent and PROMPT not in transcript, "refusal prompted for input"
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        os.close(master)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=("success", "fallback"))
    parser.add_argument("--baseline", type=Path)
    options = parser.parse_args()
    if options.child:
        child(options.child, options.baseline)
    elif options.baseline:
        exercise("success", options.baseline)
        print("Frozen provider refused before prompt and READY")
    else:
        exercise("success")
        print("One hidden prompt; public marker read exactly; no network")
        exercise("fallback")
        print("Echo fallback refused before prompt and READY")
