from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from lightyear_common.io import normalize_logical_source, write_json

from .model import semantic_content


EVIDENCE_PACK_SCHEMA_VERSION = "1.0"
ALLOWED_VISIBILITY = {"shared", "inspector_private"}


class EvidenceStore:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.by_support: dict[tuple[str, str, int], dict[str, Any]] = {}
        for capsule in payload.get("capsules", []):
            for support in capsule.get("supports", []):
                self.by_support[
                    (
                        support["owner_type"],
                        support["owner_id"],
                        support["evidence_index"],
                    )
                ] = capsule

    def excerpt(
        self, owner_type: str, owner_id: str, evidence_index: int
    ) -> dict[str, Any]:
        capsule = self.by_support[(owner_type, owner_id, evidence_index)]
        return {key: value for key, value in capsule.items() if key != "supports"}


def evidence_key(item: dict[str, Any]) -> str:
    identity = {
        "confidence": item.get("confidence"),
        "line_end": item.get("line_end"),
        "line_start": item.get("line_start"),
        "method": item.get("method"),
        "path": item.get("path"),
        "source_id": item.get("source_id"),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_evidence_pack(
    graph: dict[str, Any],
    source_roots: dict[str, Path],
    context_lines: int = 5,
    max_evidence_lines: int = 240,
) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph["nodes"]}
    sources = {source["id"]: source for source in graph["sources"]}
    file_cache: dict[tuple[str, str], tuple[list[str], str, str]] = {}
    capsules: dict[str, dict[str, Any]] = {}

    for owner_type, owners in (("node", graph["nodes"]), ("edge", graph["edges"])):
        for owner in owners:
            visibility = _owner_visibility(owner_type, owner, nodes)
            for evidence_index, item in enumerate(owner.get("evidence", [])):
                key = evidence_key(item)
                if key not in capsules:
                    source_id = item["source_id"]
                    if source_id not in source_roots or source_id not in sources:
                        raise ValueError(f"No configured source root for {source_id}")
                    relative_path, source_path = _safe_source_path(
                        source_roots[source_id], item["path"]
                    )
                    cache_key = (source_id, relative_path)
                    if cache_key not in file_cache:
                        raw = source_path.read_bytes()
                        logical = normalize_logical_source(raw)
                        lines = logical.decode("utf-8", errors="replace").splitlines() or [""]
                        file_cache[cache_key] = (
                            lines,
                            hashlib.sha256(logical).hexdigest(),
                            hashlib.sha256(raw).hexdigest(),
                        )
                    lines, file_sha256, transport_file_sha256 = file_cache[cache_key]
                    line_start = item["line_start"]
                    line_end = item["line_end"]
                    if line_start < 1 or line_start > len(lines):
                        raise ValueError(
                            f"Evidence line {line_start} is outside {relative_path} ({len(lines)} lines)"
                        )
                    if line_end < line_start:
                        raise ValueError(f"Evidence range is reversed in {relative_path}")
                    display_line_end = min(line_end, line_start + max_evidence_lines - 1, len(lines))
                    context_start = max(1, line_start - context_lines)
                    context_end = min(len(lines), display_line_end + context_lines)
                    excerpt_lines = [
                        {
                            "highlighted": line_start <= number <= display_line_end,
                            "number": number,
                            "text": lines[number - 1],
                        }
                        for number in range(context_start, context_end + 1)
                    ]
                    excerpt_hash = hashlib.sha256(
                        json.dumps(
                            excerpt_lines, sort_keys=True, separators=(",", ":")
                        ).encode("utf-8")
                    ).hexdigest()
                    capsules[key] = {
                        "capsule_id": f"capsule:{key[:24]}",
                        "confidence": item["confidence"],
                        "context_end": context_end,
                        "context_start": context_start,
                        "display_line_end": display_line_end,
                        "excerpt_sha256": excerpt_hash,
                        "file_sha256": file_sha256,
                        "hash_basis": "normalized-lf",
                        "language": _language(relative_path),
                        "line_end": line_end,
                        "line_start": line_start,
                        "lines": excerpt_lines,
                        "method": item["method"],
                        "path": relative_path,
                        "source_id": source_id,
                        "supports": [],
                        "truncated": line_end > display_line_end,
                        "transport_file_sha256": transport_file_sha256,
                    }
                support = {
                    "evidence_index": evidence_index,
                    "owner_id": owner["id"],
                    "owner_type": owner_type,
                    "visibility": visibility,
                }
                if support not in capsules[key]["supports"]:
                    capsules[key]["supports"].append(support)

    ordered_capsules = []
    for _, capsule in sorted(capsules.items()):
        capsule["supports"] = sorted(
            capsule["supports"],
            key=lambda item: (
                item["owner_type"], item["owner_id"], item["evidence_index"]
            ),
        )
        ordered_capsules.append(capsule)
    payload = {
        "capsules": ordered_capsules,
        "graph_content_sha256": graph["content_sha256"],
        "relationship_ontology": graph["relationship_ontology"],
        "schema_version": EVIDENCE_PACK_SCHEMA_VERSION,
        "sources": graph["sources"],
        "statistics": {
            "capsule_count": len(ordered_capsules),
            "capsules_by_source": dict(
                sorted(Counter(item["source_id"] for item in ordered_capsules).items())
            ),
            "support_count": sum(len(item["supports"]) for item in ordered_capsules),
        },
    }
    payload["content_sha256"] = evidence_pack_hash(payload)
    return payload


def write_evidence_pack(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(serialized, compresslevel=9, mtime=0))
    else:
        path.write_bytes(serialized)


def load_evidence_pack(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_pack_hash(payload: dict[str, Any]) -> str:
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    canonical = json.dumps(
        semantic_content(content), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_evidence_pack(
    graph: dict[str, Any], pack: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if pack.get("schema_version") != EVIDENCE_PACK_SCHEMA_VERSION:
        errors.append(f"unsupported evidence pack version: {pack.get('schema_version')}")
    if pack.get("graph_content_sha256") != graph.get("content_sha256"):
        errors.append("evidence pack graph identity does not match")
    if pack.get("relationship_ontology") != graph.get("relationship_ontology"):
        errors.append("evidence pack relationship ontology identity does not match")
    if pack.get("content_sha256") != evidence_pack_hash(pack):
        errors.append("evidence pack content_sha256 does not match canonical content")

    owners = {
        (owner_type, owner["id"]): owner
        for owner_type, records in (("node", graph["nodes"]), ("edge", graph["edges"]))
        for owner in records
    }
    seen_supports: set[tuple[str, str, int]] = set()
    capsule_ids: set[str] = set()
    for capsule in pack.get("capsules", []):
        capsule_id = capsule.get("capsule_id")
        if capsule_id in capsule_ids:
            errors.append(f"duplicate evidence capsule id: {capsule_id}")
        capsule_ids.add(capsule_id)
        path = Path(str(capsule.get("path", "")))
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"capsule {capsule_id} has unsafe path")
        lines = capsule.get("lines", [])
        excerpt_hash = hashlib.sha256(
            json.dumps(lines, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if excerpt_hash != capsule.get("excerpt_sha256"):
            errors.append(f"capsule {capsule_id} excerpt hash does not match")
        for support in capsule.get("supports", []):
            key = (
                support.get("owner_type"),
                support.get("owner_id"),
                support.get("evidence_index"),
            )
            owner = owners.get((key[0], key[1]))
            if owner is None:
                errors.append(f"capsule {capsule_id} references unknown owner {key[0]}:{key[1]}")
                continue
            if support.get("visibility") not in ALLOWED_VISIBILITY:
                errors.append(f"capsule {capsule_id} has invalid visibility")
            evidence_index = key[2]
            if not isinstance(evidence_index, int) or not 0 <= evidence_index < len(
                owner.get("evidence", [])
            ):
                errors.append(f"capsule {capsule_id} has invalid evidence index for {key[1]}")
                continue
            expected_id = f"capsule:{evidence_key(owner['evidence'][evidence_index])[:24]}"
            if capsule_id != expected_id:
                errors.append(f"capsule {capsule_id} does not match owner evidence {key[1]}")
            seen_supports.add(key)
    expected_supports = {
        (owner_type, owner["id"], index)
        for owner_type, records in (("node", graph["nodes"]), ("edge", graph["edges"]))
        for owner in records
        for index, _ in enumerate(owner.get("evidence", []))
    }
    missing = expected_supports - seen_supports
    if missing:
        errors.append(f"evidence pack is missing {len(missing)} graph evidence supports")
    return errors


def write_evidence_receipt(payload: dict[str, Any], path: Path) -> None:
    receipt = {
        "content_sha256": payload["content_sha256"],
        "graph_content_sha256": payload["graph_content_sha256"],
        "receipt_type": "lightyear-source-evidence-pack",
        "relationship_ontology": payload["relationship_ontology"],
        "schema_version": payload["schema_version"],
        "statistics": payload["statistics"],
    }
    write_json(path, receipt)


def _owner_visibility(
    owner_type: str, owner: dict[str, Any], nodes: dict[str, dict[str, Any]]
) -> str:
    if owner.get("properties", {}).get("visibility") == "inspector_private":
        return "inspector_private"
    if owner_type == "edge" and any(
        nodes[node_id].get("properties", {}).get("visibility") == "inspector_private"
        for node_id in (owner["source"], owner["target"])
    ):
        return "inspector_private"
    return "shared"


def _safe_source_path(root: Path, path: str) -> tuple[str, Path]:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe evidence path: {path}")
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if resolved_root not in candidate.parents:
        raise ValueError(f"Evidence path escapes source root: {path}")
    if not candidate.is_file():
        raise ValueError(f"Evidence source file does not exist: {path}")
    return relative.as_posix(), candidate


def _language(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return {
        ".cbl": "cobol",
        ".cob": "cobol",
        ".cpy": "cobol",
        ".java": "java",
        ".json": "json",
        ".md": "markdown",
        ".pom": "xml",
        ".properties": "properties",
        ".py": "python",
        ".xml": "xml",
        ".yml": "yaml",
        ".yaml": "yaml",
    }.get(suffix, "text")
