from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def normalize_logical_source(raw: bytes) -> bytes:
    """Return a platform-neutral logical source representation.

    Source-control transports may materialize the same text with LF, CRLF, or
    legacy CR line endings. Semantic identity is based on LF while the raw hash
    remains available for forensic chain-of-custody evidence.
    """

    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def source_hashes(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    logical = normalize_logical_source(raw)
    return hashlib.sha256(logical).hexdigest(), hashlib.sha256(raw).hexdigest()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
