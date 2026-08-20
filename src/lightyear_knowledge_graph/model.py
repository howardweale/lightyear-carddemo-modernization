from __future__ import annotations

import hashlib
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.1"
TRANSPORT_ONLY_KEYS = {"transport_content_sha256", "transport_file_sha256"}


def semantic_content(value: Any) -> Any:
    """Remove transport-only observations from canonical semantic identity."""

    if isinstance(value, dict):
        return {
            key: semantic_content(item)
            for key, item in value.items()
            if key not in TRANSPORT_ONLY_KEYS
        }
    if isinstance(value, list):
        return [semantic_content(item) for item in value]
    return value


def evidence(
    source_id: str,
    path: str,
    line_start: int,
    line_end: int | None = None,
    method: str = "deterministic-extraction",
    confidence: str = "observed",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "path": path,
        "line_start": line_start,
        "line_end": line_end if line_end is not None else line_start,
        "method": method,
        "confidence": confidence,
    }


class KnowledgeGraph:
    """Small property-graph model with deterministic serialization and provenance."""

    def __init__(
        self,
        graph_id: str,
        sources: list[dict[str, Any]],
        relationship_ontology: dict[str, str],
    ) -> None:
        self.graph_id = graph_id
        self.sources = sorted(sources, key=lambda item: item["id"])
        self.relationship_ontology = relationship_ontology
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    def add_node(
        self,
        node_id: str,
        kind: str,
        name: str,
        *,
        properties: dict[str, Any] | None = None,
        evidence_items: list[dict[str, Any]] | None = None,
    ) -> str:
        candidate = {
            "id": node_id,
            "kind": kind,
            "name": name,
            "properties": properties or {},
            "evidence": evidence_items or [],
        }
        existing = self.nodes.get(node_id)
        if existing is None:
            self.nodes[node_id] = candidate
            return node_id
        if existing["kind"] != kind:
            raise ValueError(f"Node {node_id} has conflicting kinds: {existing['kind']} and {kind}")
        existing["properties"].update(candidate["properties"])
        for item in candidate["evidence"]:
            if item not in existing["evidence"]:
                existing["evidence"].append(item)
        return node_id

    def add_edge(
        self,
        source: str,
        relation: str,
        target: str,
        *,
        properties: dict[str, Any] | None = None,
        evidence_items: list[dict[str, Any]] | None = None,
    ) -> str:
        identity = json.dumps([source, relation, target, properties or {}], sort_keys=True)
        edge_id = "edge:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        candidate = {
            "id": edge_id,
            "source": source,
            "relation": relation,
            "target": target,
            "properties": properties or {},
            "evidence": evidence_items or [],
        }
        existing = self.edges.get(edge_id)
        if existing is None:
            self.edges[edge_id] = candidate
        else:
            for item in candidate["evidence"]:
                if item not in existing["evidence"]:
                    existing["evidence"].append(item)
        return edge_id

    def statistics(self) -> dict[str, Any]:
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes_by_kind": dict(sorted(Counter(n["kind"] for n in self.nodes.values()).items())),
            "edges_by_relation": dict(
                sorted(Counter(e["relation"] for e in self.edges.values()).items())
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        nodes = []
        for node in sorted(self.nodes.values(), key=lambda item: item["id"]):
            normalized = dict(node)
            normalized["properties"] = dict(sorted(node["properties"].items()))
            normalized["evidence"] = sorted(
                node["evidence"],
                key=lambda item: (
                    item["source_id"], item["path"], item["line_start"], item["line_end"], item["method"]
                ),
            )
            nodes.append(normalized)
        edges = []
        for edge in sorted(self.edges.values(), key=lambda item: item["id"]):
            normalized = dict(edge)
            normalized["properties"] = dict(sorted(edge["properties"].items()))
            normalized["evidence"] = sorted(
                edge["evidence"],
                key=lambda item: (
                    item["source_id"], item["path"], item["line_start"], item["line_end"], item["method"]
                ),
            )
            edges.append(normalized)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "graph_id": self.graph_id,
            "relationship_ontology": self.relationship_ontology,
            "sources": self.sources,
            "statistics": self.statistics(),
            "nodes": nodes,
            "edges": edges,
        }
        canonical = json.dumps(
            semantic_content(payload), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
        return payload

    def write(self, path: Path) -> dict[str, Any]:
        payload = self.to_dict()
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if path.suffix == ".gz":
            path.write_bytes(gzip.compress(serialized, compresslevel=9, mtime=0))
        else:
            path.write_bytes(serialized)
        return payload


def load_graph(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def graph_hash(payload: dict[str, Any]) -> str:
    without_hash = {key: value for key, value in payload.items() if key != "content_sha256"}
    canonical = json.dumps(
        semantic_content(without_hash), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
