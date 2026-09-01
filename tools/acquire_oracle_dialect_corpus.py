#!/usr/bin/env python3
"""Acquire or verify the pinned, allowlisted Oracle sample-schema corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ESTATE_ROOT = ROOT / "reference-estates/oracle"
PIN_PATH = ESTATE_ROOT / "source-pin.json"
CORPUS_ROOT = ESTATE_ROOT / "corpus"
MANIFEST_PATH = ESTATE_ROOT / "corpus-manifest.json"
SURFACE_PATTERNS = {
    "blob": r"\bBLOB\b",
    "clob": r"\bCLOB\b",
    "date": r"\bDATE\b",
    "number": r"\bNUMBER\b",
    "plsql_trigger": r"\bCREATE\s+OR\s+REPLACE\s+TRIGGER\b",
    "varchar2": r"\bVARCHAR2\b",
}


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(source_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"oracle-corpus-git-failed:{' '.join(args)}")
    return result.stdout.strip()


def load_pin() -> dict[str, Any]:
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def validate_source(source_root: Path, pin: dict[str, Any]) -> None:
    if not source_root.is_dir():
        raise ValueError("oracle-corpus-source-missing")
    if git(source_root, "status", "--porcelain"):
        raise ValueError("oracle-corpus-source-dirty")
    if git(source_root, "rev-parse", "HEAD^{commit}") != pin["commit"]:
        raise ValueError("oracle-corpus-source-commit-mismatch")
    if git(source_root, "rev-parse", "HEAD^{tree}") != pin["tree"]:
        raise ValueError("oracle-corpus-source-tree-mismatch")
    for item in pin["files"]:
        path = source_root / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise ValueError(f"oracle-corpus-source-file-mismatch:{item['path']}")


def selected_paths(pin: dict[str, Any]) -> set[str]:
    return {item["path"] for item in pin["files"]}


def unexpected_corpus_files(pin: dict[str, Any]) -> list[str]:
    if not CORPUS_ROOT.exists():
        return []
    return sorted(
        path.relative_to(CORPUS_ROOT).as_posix()
        for path in CORPUS_ROOT.rglob("*")
        if path.is_file() and path.relative_to(CORPUS_ROOT).as_posix() not in selected_paths(pin)
    )


def build_manifest(pin: dict[str, Any]) -> dict[str, Any]:
    files = []
    sql_lines = 0
    surface = {name: 0 for name in SURFACE_PATTERNS}
    for item in pin["files"]:
        path = CORPUS_ROOT / item["path"]
        if not path.is_file():
            raise ValueError(f"oracle-corpus-target-file-missing:{item['path']}")
        digest = sha256_path(path)
        if digest != item["sha256"]:
            raise ValueError(f"oracle-corpus-target-file-mismatch:{item['path']}")
        raw = path.read_bytes()
        files.append({"path": item["path"], "bytes": len(raw), "sha256": digest})
        if path.suffix.lower() == ".sql":
            text = raw.decode("utf-8")
            sql_lines += len(text.splitlines())
            for name, pattern in SURFACE_PATTERNS.items():
                surface[name] += len(re.findall(pattern, text, flags=re.IGNORECASE))
    return {
        "schema_version": "1.0",
        "corpus_id": "oracle-db-sample-schemas-v23.3-active-schema-surface",
        "source": {
            "repository": pin["repository"],
            "release": pin["release"],
            "commit": pin["commit"],
            "tree": pin["tree"],
            "license_expression": pin["license"]["expression"],
        },
        "selection": pin["selection"],
        "file_count": len(files),
        "sql_file_count": sum(item["path"].endswith(".sql") for item in files),
        "sql_line_count": sql_lines,
        "total_bytes": sum(item["bytes"] for item in files),
        "oracle_surface_counts": surface,
        "files": files,
        "source_pin_sha256": sha256_path(PIN_PATH),
        "native_oracle_executed": False,
        "production_ready": False,
    }


def acquire(source_root: Path) -> dict[str, Any]:
    pin = load_pin()
    validate_source(source_root, pin)
    extras = unexpected_corpus_files(pin)
    if extras:
        raise ValueError(f"oracle-corpus-target-unexpected:{extras[0]}")
    for item in pin["files"]:
        source = source_root / item["path"]
        target = CORPUS_ROOT / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    manifest = build_manifest(pin)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify(source_root: Path | None = None) -> dict[str, Any]:
    pin = load_pin()
    if source_root is not None:
        validate_source(source_root, pin)
    extras = unexpected_corpus_files(pin)
    if extras:
        raise ValueError(f"oracle-corpus-target-unexpected:{extras[0]}")
    expected = build_manifest(pin)
    if not MANIFEST_PATH.is_file():
        raise ValueError("oracle-corpus-manifest-missing")
    actual = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if actual != expected:
        raise ValueError("oracle-corpus-manifest-drift")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify and args.source_root is None:
        parser.error("--source-root is required for acquisition")
    manifest = verify(args.source_root.resolve() if args.source_root else None) if args.verify else acquire(args.source_root.resolve())
    print(json.dumps({
        "commit": manifest["source"]["commit"],
        "files": manifest["file_count"],
        "schemas": len(manifest["selection"]["schemas"]),
        "status": "verified" if args.verify else "acquired",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
