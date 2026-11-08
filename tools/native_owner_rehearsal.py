"""Human-attended NO-KEY public spawn rehearsal; CI exercises disposable fixtures.

Use the reviewed absolute interpreter with -I and this absolute script path.
No hardware, signer, helper, factory or Tower import. This is not an admission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
# Ordinary importable module, including in multiprocessing's spawned interpreter.
sys.path.insert(0, str(SOURCE_ROOT / "src"))
from lightyear_execution.mac_owner_process import CASES, RehearsalProcessOwner


class PublicJournal:
    """Exclusive directory and append-only, fsynced public event stream.

    Truncated/missing final result is failure. No restart/resume/overwrite path.
    Filesystem retention/power-loss durability still needs native verification.
    """
    def __init__(self, directory):
        directory = Path(directory)
        if not directory.is_absolute() or ".." in directory.parts:
            raise ValueError("absolute-reviewed-output-required")
        # Inspect named path components only, never scan directories or home files.
        parent = directory.parent
        if parent.resolve(strict=True) != parent or any(p.is_symlink() for p in (parent, *parent.parents)):
            raise ValueError("output-parent-alias-refused")
        if os.name == "posix":
            meta = parent.stat()
            if meta.st_uid != os.getuid() or stat.S_IMODE(meta.st_mode) & 0o022:
                raise ValueError("output-parent-owner-or-mode-refused")
        directory.mkdir(mode=0o700)  # Existing name, including symlink => STOP.
        self.path = directory / "events.jsonl"
        self._file = self.path.open("xb", buffering=0)
        if os.name == "posix":
            os.fchmod(self._file.fileno(), 0o600)
        self._sequence = 0
        self._previous = "0" * 64

    def append(self, event):
        self._sequence += 1
        record = dict(sequence=self._sequence, previous_sha256=self._previous, event=event)
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"
        if self._file.write(raw) != len(raw):
            raise OSError("public-journal-short-write")
        os.fsync(self._file.fileno())
        self._previous = hashlib.sha256(raw).hexdigest()

    def close(self):
        self._file.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--output", type=Path, required=True, help="exclusive new directory beneath reviewed scratch parent")
    parser.add_argument("--seconds", type=int, choices=range(1, 61), required=True)
    parser.add_argument("--keys-unplugged", action="store_true", help="human acknowledgment, not hardware verification")
    args = parser.parse_args(argv)
    if not args.keys_unplugged:
        parser.error("human NO-KEY acknowledgment required")
    journal = None
    try:
        journal = PublicJournal(args.output)
        shipped = ("tools/native_owner_rehearsal.py", "src/lightyear_execution/mac_owner_process.py",
                   "src/lightyear_execution/__init__.py")
        public_argv = ["--case", args.case, "--output", str(args.output), "--seconds", str(args.seconds), "--keys-unplugged"]
        journal.append(dict(kind="metadata", schema="native-owner-rehearsal/1",
                            python=sys.version, executable=sys.executable, machine=platform.machine(),
                            argv_sha256=hashlib.sha256(json.dumps(public_argv).encode()).hexdigest(),
                            source_sha256={p: hashlib.sha256((SOURCE_ROOT / p).read_bytes()).hexdigest() for p in shipped},
                            keys_unplugged_human_ack=True, hardware_checked=False,
                            native_proof=False, admission_authorized=False))
        def emit(event):
            journal.append(event)
            if (args.case == "S6" and event["kind"] == "worker-observation"
                    and event["observation"]["kind"] == "ready"):
                print('{"status":"READY","action":"press-Ctrl-C-once"}', flush=True)
        result = RehearsalProcessOwner(case=args.case, duration=args.seconds, emit=emit).run_once()
        print(json.dumps({k: result[k] for k in ("status", "reason", "cleanup_status", "native_proof")}))
        return 0 if result["status"] == "PASS" else 2
    except BaseException:
        # No raw stderr, paths from exceptions, environment or private data.
        print('{"status":"FAIL","reason":"public-rehearsal-unavailable","native_proof":false}')
        return 2
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
