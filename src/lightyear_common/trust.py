from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping


CLAIM_FIELDS = (
    "qualification_eligible",
    "promotion_allowed",
    "production_ready",
    "mainframe_equivalent",
)
UPSTREAM_COMMIT = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
SCRIPT_ROLES = {
    "aggregator",
    "developer",
    "internal",
    "live-authorized",
    "operator",
    "release-gated",
}
SKIPPED_TREE_PARTS = {".git", ".mypy_cache", ".pytest_cache", "node_modules", "target", "work"}


class TrustBoundaryError(ValueError):
    """A receipt, prerequisite, or entry-point trust contract was violated."""


def require_unpromoted_claims(
    payload: Mapping[str, Any],
    *,
    required: Iterable[str] = CLAIM_FIELDS,
    label: str = "Receipt",
) -> None:
    """Require an explicitly false value for every non-promoted claim.

    A future live promotion must introduce and test an explicit authority path
    rather than changing a receipt literal in isolation.
    """

    for field in required:
        if payload.get(field) is not False:
            raise TrustBoundaryError(f"{label} must set {field} to false")


def audit_receipt_claims(project_root: Path) -> list[str]:
    """Reject committed receipt overclaims and literal source promotions."""

    root = project_root.resolve()
    errors: list[str] = []
    for source_root in (root / "src", root / "extensions/runtime"):
        if not source_root.is_dir():
            continue
        for path in sorted(source_root.rglob("*.py")):
            if any(part in SKIPPED_TREE_PARTS for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                errors.append(f"{path.relative_to(root)}: cannot audit Python source: {exc}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value in CLAIM_FIELDS
                        and isinstance(value, ast.Constant)
                        and value.value is True
                    ):
                        errors.append(
                            f"{path.relative_to(root)}:{value.lineno}: literal promotion of {key.value} requires an explicit authority path"
                        )

    for path in sorted(root.rglob("*.json")):
        relative = path.relative_to(root)
        if any(part in SKIPPED_TREE_PARTS or part in {"schema", "schemas"} for part in relative.parts):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        _audit_json_claims(payload, str(relative), "$", errors)
    return errors


def _audit_json_claims(value: Any, label: str, pointer: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{pointer}/{key}"
            if key in CLAIM_FIELDS and item is not False:
                errors.append(f"{label}:{child} must be false until an authority path is registered")
            _audit_json_claims(item, label, child, errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _audit_json_claims(item, label, f"{pointer}/{index}", errors)


def validate_upstream_fixture(project_root: Path) -> list[str]:
    root = project_root.resolve().parent / "carddemo-upstream"
    if not (root / ".git").exists():
        return [
            "Required CardDemo fixture is missing at ../carddemo-upstream. "
            f"Clone aws-samples/aws-mainframe-modernization-carddemo and check out {UPSTREAM_COMMIT}."
        ]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode or result.stdout.strip() != UPSTREAM_COMMIT:
        observed = result.stdout.strip() or "unreadable"
        return [f"CardDemo fixture must be at {UPSTREAM_COMMIT}; observed {observed}."]
    return []


def audit_script_catalog(project_root: Path) -> list[str]:
    root = project_root.resolve()
    path = root / "scripts.catalog.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"scripts.catalog.json is unavailable or invalid: {exc}"]
    errors: list[str] = []
    expected_hash = _canonical_hash(catalog, {"content_sha256"})
    if catalog.get("content_sha256") != expected_hash:
        errors.append("scripts.catalog.json content hash is invalid")
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        return errors + ["scripts.catalog.json entries must be a list"]
    names = [item.get("name") for item in entries if isinstance(item, dict)]
    if len(names) != len(entries) or len(set(names)) != len(names):
        errors.append("scripts.catalog.json contains invalid or duplicate names")
    actual = sorted(path.name[:-3] for path in root.glob("*.sh"))
    if sorted(names) != actual:
        errors.append(f"script catalog does not match POSIX entry points: expected {actual}, found {sorted(names)}")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if entry.get("role") not in SCRIPT_ROLES:
            errors.append(f"{name}: script role is invalid")
        if not isinstance(entry.get("verification"), str) or not entry["verification"]:
            errors.append(f"{name}: verification ownership is missing")
        if not isinstance(entry.get("purpose"), str) or not entry["purpose"]:
            errors.append(f"{name}: purpose is missing")
        if isinstance(name, str) and not (root / f"{name}.ps1").is_file():
            errors.append(f"{name}: PowerShell twin is missing")
    return errors


def _canonical_hash(payload: Mapping[str, Any], excluded: set[str]) -> str:
    material = {key: value for key, value in payload.items() if key not in excluded}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
