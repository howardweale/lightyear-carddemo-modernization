"""Bounded, deterministic contracts shared by calibration adapters and reports."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_CASES = 20000
MAX_RECORDS = 500000
MAX_UNITS = 5000000
VERSION = "1.0"


class CalibrationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CalibrationError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(value):
    encoded = canonical(value)
    return {**json.loads(encoded), "content_sha256": hashlib.sha256(encoded).hexdigest()}


def verify(value):
    require(isinstance(value, dict) and value.get("content_sha256") == digest(
        {k: v for k, v in value.items() if k != "content_sha256"}), "Content hash mismatch")


def read_json(path: Path):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "Duplicate JSON key")
            value[key] = item
        return value
    def invalid(_):
        raise CalibrationError("Nonfinite JSON number")
    try:
        with path.open("rb") as f:
            data = f.read(MAX_JSON_BYTES + 1)
        require(len(data) <= MAX_JSON_BYTES, "JSON exceeds 64 MiB")
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise CalibrationError(f"Cannot admit JSON: {path.name}: {exc}") from exc


def exact(value, fields):
    require(isinstance(value, dict) and set(value) == set(fields), "Unknown or missing contract fields")


def label(value, maximum=500):
    require(isinstance(value, str) and 0 < len(value) <= maximum and
            not any(ord(c) < 32 for c in value), "Invalid bounded label")
    return value


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "Invalid SHA-256")
    return value


def count(value, maximum=MAX_UNITS):
    require(type(value) is int and 0 <= value <= maximum, "Invalid bounded count")
    return value


def implementation(paths):
    return {name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name, path in sorted(paths.items())}
