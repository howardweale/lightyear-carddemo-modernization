"""Bounded public-only NO-KEY metadata/hash/copy operations for attended review.

No signing SDK imports, hardware discovery, network, commands or recursive walk.
These diagnostics do not grant authority, authenticate manifests or prove custody.
Every output is a new exclusive file; partial failures are retained, never deleted.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import stat
import sys


MAX_BYTES = 8 * 1024 * 1024
VERSIONS = {"cryptography": "46.0.3", "yubikey-manager": "5.9.2"}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite-json")))


def _path(value, *, directory=False):
    p = Path(value)
    require(p.is_absolute() and ".." not in p.parts, "absolute-path-required")
    for parent in (p, *p.parents):
        meta = parent.lstat()
        require(not stat.S_ISLNK(meta.st_mode) and not getattr(meta, "st_file_attributes", 0) & 0x400,
                "path-alias-refused")
    require(p.resolve(strict=True) == p, "path-resolution-drift")
    meta = p.stat()
    require(stat.S_ISDIR(meta.st_mode) if directory else stat.S_ISREG(meta.st_mode), "plain-path-required")
    if not directory:
        require(meta.st_nlink == 1, "hardlink-refused")
    return p


def _new_file(value):
    p = Path(value)
    require(p.is_absolute() and ".." not in p.parts, "absolute-output-required")
    parent = _path(p.parent, directory=True)
    if os.name == "posix":
        meta = parent.stat()
        require(meta.st_uid == os.getuid() and not stat.S_IMODE(meta.st_mode) & 0o022,
                "output-owner-or-mode")
    return os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)


def _write_new(path, raw):
    fd = _new_file(path)
    try:
        require(os.write(fd, raw) == len(raw), "short-output-write")
        os.fsync(fd)
    finally:
        os.close(fd)


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read_public(path):
    p = _path(path)
    before = p.stat()
    require(before.st_size <= MAX_BYTES, "public-file-size")
    with p.open("rb") as stream:
        require(_identity(os.fstat(stream.fileno())) == _identity(before), "source-open-drift")
        raw = stream.read(MAX_BYTES + 1)
        require(_identity(os.fstat(stream.fileno())) == _identity(before), "source-read-drift")
    require(_identity(p.stat()) == _identity(before) and len(raw) == before.st_size, "source-path-drift")
    _path(p)
    return raw


def _digest(value):
    require(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value), "digest-shape")
    return value


def compare_public(source, expected_sha256, expected_bytes):
    _digest(expected_sha256)
    require(type(expected_bytes) is int and 0 <= expected_bytes <= MAX_BYTES, "public-size-bound")
    raw = read_public(source)
    digest = hashlib.sha256(raw).hexdigest()
    require(len(raw) == expected_bytes and digest == expected_sha256, "public-source-mismatch")
    return raw, dict(sha256=digest, bytes=len(raw), matched=True, native_proof=False)


def copy_public(source, destination, expected_sha256, expected_bytes):
    raw, result = compare_public(source, expected_sha256, expected_bytes)
    # Validation happens before creation; a wrong digest cannot leave a good-looking copy.
    _write_new(destination, raw)
    observed = read_public(destination)
    require(observed == raw, "copy-readback-mismatch")
    return dict(result, copy_readback=True, overwrite=False)


def runtime_metadata(bundle, site):
    bundle, site = _path(bundle, directory=True), _path(site, directory=True)
    executable = Path(sys.executable).resolve(strict=True)
    require(executable.is_relative_to(bundle / "runtime") and site == bundle / "site", "bundle-runtime-site-binding")
    observed = {}
    for distribution in importlib.metadata.distributions(path=[str(site)]):
        name = distribution.metadata.get("Name", "").lower().replace("_", "-")
        if name in VERSIONS:
            require(name not in observed, "duplicate-distribution")
            observed[name] = distribution.version
    require(platform.python_version() == "3.12.16" and observed == VERSIONS, "runtime-baseline-mismatch")
    return dict(python=platform.python_version(), executable=str(executable), machine=platform.machine(),
                sqlite=sqlite3.sqlite_version, distributions=observed, sdk_imported=False,
                hardware_checked=False, native_proof=False)


def check_manifest(root, manifest, manifest_sha256):
    root = _path(root, directory=True)
    raw = read_public(manifest)
    require(hashlib.sha256(raw).hexdigest() == _digest(manifest_sha256), "manifest-digest-mismatch")
    data = _json(raw)
    require(type(data) is dict and set(data) == {"schema", "files"}
            and data["schema"] == "native-rehearsal-public-files/1"
            and type(data["files"]) is list and 0 < len(data["files"]) <= 10000, "manifest-shape")
    seen, rows = set(), []
    for row in data["files"]:
        require(type(row) is dict and set(row) == {"path", "sha256", "bytes"}, "manifest-file-fields")
        name = row["path"]
        require(type(name) is str and name and "\\" not in name and ":" not in name
                and not name.startswith("/") and all(p not in ("", ".", "..") for p in name.split("/"))
                and name not in seen, "manifest-relative-path")
        seen.add(name)
        _, checked = compare_public(root / name, row["sha256"], row["bytes"])
        rows.append(dict(path=name, **checked))
    return dict(manifest_sha256=manifest_sha256, files=rows, native_proof=False,
                scope="listed-public-source-fixtures-only; runtime archive needs its independent manifest")


def journal_status(source):
    raw = read_public(source)
    require(raw.endswith(b"\n"), "journal-truncated")
    rows = raw.splitlines(keepends=True)
    require(2 <= len(rows) <= 8192, "journal-line-count")
    previous, deadline, cleanup_bound, case = "0" * 64, None, None, None
    for sequence, line in enumerate(rows, 1):
        row = _json(line)
        require(type(row) is dict and set(row) == {"sequence", "previous_sha256", "event"}
                and type(row["sequence"]) is int and row["sequence"] == sequence
                and row["previous_sha256"] == previous, "journal-chain")
        event = row["event"]
        require(type(event) is dict, "journal-event")
        if sequence == 1:
            require(event.get("kind") == "metadata" and event.get("schema") == "native-owner-rehearsal/1"
                    and event.get("native_proof") is False, "journal-metadata")
        else:
            binding = event.get("original_deadline"), event.get("cleanup_deadline"), event.get("case")
            if deadline is None:
                deadline, cleanup_bound, case = binding
                require(type(deadline) in (int, float) and type(cleanup_bound) in (int, float)
                        and math.isfinite(deadline) and math.isfinite(cleanup_bound)
                        and cleanup_bound - deadline == 5 and case in ("S1","S2","S3","S4","S5","S6","S7"), "journal-binding")
            require(binding == (deadline, cleanup_bound, case), "journal-binding-drift")
        require(event.get("kind") != "result" or sequence == len(rows), "journal-after-result")
        previous = hashlib.sha256(line).hexdigest()
    final = row["event"]
    require(final.get("kind") == "result" and final.get("status") in ("PASS", "FAIL")
            and final.get("cleanup_status") in ("REAPED", "UNKNOWN")
            and final.get("native_proof") is False, "journal-final-result-required")
    require(final["status"] != "PASS" or final["cleanup_status"] == "REAPED", "inconsistent-reported-success")
    return dict(case=case, reported_status=final["status"], reported_cleanup=final["cleanup_status"],
                journal_sha256=hashlib.sha256(raw).hexdigest(), chain_consistent=True,
                live_processes_checked=False, authenticated=False, native_proof=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="operation", required=True)
    for name in ("compare", "copy"):
        cmd = subs.add_parser(name)
        cmd.add_argument("--source", type=Path, required=True)
        cmd.add_argument("--sha256", required=True)
        cmd.add_argument("--bytes", type=int, required=True)
        if name == "copy": cmd.add_argument("--destination", type=Path, required=True)
    cmd = subs.add_parser("metadata")
    cmd.add_argument("--bundle", type=Path, required=True)
    cmd.add_argument("--site", type=Path, required=True)
    cmd = subs.add_parser("manifest")
    cmd.add_argument("--root", type=Path, required=True)
    cmd.add_argument("--manifest", type=Path, required=True)
    cmd.add_argument("--sha256", required=True)
    cmd = subs.add_parser("journal-status")
    cmd.add_argument("--source", type=Path, required=True)
    for cmd in subs.choices.values(): cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "copy": result = copy_public(args.source, args.destination, args.sha256, args.bytes)
        elif args.operation == "compare": _, result = compare_public(args.source, args.sha256, args.bytes)
        elif args.operation == "metadata": result = runtime_metadata(args.bundle, args.site)
        elif args.operation == "manifest": result = check_manifest(args.root, args.manifest, args.sha256)
        else: result = journal_status(args.source)
        raw = (json.dumps(result, sort_keys=True, allow_nan=False) + "\n").encode("ascii")
        _write_new(args.output, raw)
        print('{"status":"RECORDED","native_proof":false}')
        return 0
    except BaseException:
        print('{"status":"REFUSED","reason":"public-io-invalid-or-unavailable","native_proof":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
