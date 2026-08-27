from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SUPPORTED_MODERN_SUFFIXES = {".java", ".py", ".xml"}


class SemanticInputError(ValueError):
    """Raised when the semantic graph input contract is incomplete or unsafe."""


def canonical_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_semantic_inputs(path: Path, project_root: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_semantic_inputs(payload, project_root)
    if errors:
        raise SemanticInputError("; ".join(errors))
    return payload


def validate_semantic_inputs(payload: dict[str, Any], project_root: Path) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported semantic input schema_version: {payload.get('schema_version')}")
    if payload.get("manifest_id") != "lightyear:carddemo-semantic-inputs":
        errors.append("semantic input manifest_id is invalid")
    if payload.get("content_sha256") != canonical_hash(payload):
        errors.append("semantic input content_sha256 is invalid")

    expected_keys = {
        "schema_version",
        "manifest_id",
        "modern_files",
        "workload_manifests",
        "limitations",
        "content_sha256",
    }
    if set(payload) != expected_keys:
        errors.append("semantic input manifest has an unexpected field set")

    modern_files = payload.get("modern_files")
    workload_manifests = payload.get("workload_manifests")
    limitations = payload.get("limitations")
    if not isinstance(modern_files, list) or not modern_files:
        errors.append("semantic input modern_files must be a non-empty list")
        modern_files = []
    if not isinstance(workload_manifests, list) or not workload_manifests:
        errors.append("semantic input workload_manifests must be a non-empty list")
        workload_manifests = []
    if not isinstance(limitations, list) or not limitations:
        errors.append("semantic input limitations must be a non-empty list")

    _validate_paths(modern_files, project_root, "modern file", errors, SUPPORTED_MODERN_SUFFIXES)
    _validate_paths(workload_manifests, project_root, "workload manifest", errors, {".json"})
    return errors


def resolve_declared_paths(
    payload: dict[str, Any], project_root: Path, field: str
) -> list[Path]:
    return [(project_root / item).resolve() for item in payload[field]]


def manifest_binding(payload: dict[str, Any], path: Path, project_root: Path) -> dict[str, str]:
    return {
        "manifest_id": payload["manifest_id"],
        "schema_version": payload["schema_version"],
        "path": path.resolve().relative_to(project_root.resolve()).as_posix(),
        "content_sha256": payload["content_sha256"],
    }


def _validate_paths(
    values: list[Any],
    project_root: Path,
    label: str,
    errors: list[str],
    suffixes: set[str],
) -> None:
    if values != sorted(values) or len(values) != len(set(values)):
        errors.append(f"semantic input {label} paths must be sorted and unique")
    root = project_root.resolve()
    for value in values:
        if not isinstance(value, str) or not value or "\\" in value:
            errors.append(f"semantic input {label} path is invalid: {value!r}")
            continue
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"semantic input {label} path escapes the project: {value}")
            continue
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"semantic input {label} path escapes the project: {value}")
            continue
        if candidate.suffix.casefold() not in suffixes:
            errors.append(f"semantic input {label} has unsupported suffix: {value}")
        if not candidate.is_file():
            errors.append(f"semantic input {label} is missing: {value}")
