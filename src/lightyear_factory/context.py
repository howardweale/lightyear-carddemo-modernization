from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lightyear_knowledge_graph.evidence_pack import load_evidence_pack
from lightyear_knowledge_graph.explorer import GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph

from .contracts import ContractError, WorkOrder, canonical_hash


class GraphContextAssembler:
    """Build a bounded, provenance-rich implementer context from approved roots."""

    def __init__(
        self,
        graph_path: Path | None,
        evidence_path: Path | None,
        max_nodes: int = 160,
    ) -> None:
        self.graph_path = graph_path
        self.evidence_path = evidence_path
        self.max_nodes = max_nodes

    def assemble(self, order: WorkOrder, workspace_root: Path) -> dict[str, Any]:
        base: dict[str, Any] = {
            "schema_version": "1.0",
            "context_type": "lightyear-graph-grounded-implementer-context",
            "audience": "implementer",
            "graph_content_sha256": None,
            "evidence_pack_sha256": None,
            "approved_roots": list(order.graph_node_ids),
            "nodes": [],
            "edges": [],
            "source_excerpts": [],
            "allowed_files": [],
            "statistics": {},
            "truncated": False,
            "limitations": [],
        }
        for relative in order.allowed_paths:
            path = (workspace_root / relative).resolve()
            if workspace_root.resolve() not in path.parents or not path.is_file():
                continue
            raw = path.read_bytes()
            file_payload = {
                "path": relative,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "content": raw[: order.max_file_bytes].decode("utf-8", errors="replace"),
                "truncated": len(raw) > order.max_file_bytes,
            }
            if not self._append_within(base, "allowed_files", file_payload, order):
                base["truncated"] = True
                base["limitations"].append("Allowed-file context exceeded the byte budget.")
                break

        if not self.graph_path or not self.graph_path.is_file():
            base["limitations"].append("No knowledge graph was supplied to this run.")
            return self._finish(base, order)

        graph = load_graph(self.graph_path)
        index = GraphExplorerIndex(graph, max_nodes=self.max_nodes)
        base["graph_content_sha256"] = graph["content_sha256"]
        selected_nodes: dict[str, dict[str, Any]] = {}
        selected_edges: dict[str, dict[str, Any]] = {}
        for node_id in order.graph_node_ids:
            if node_id not in index.node_by_id:
                raise ContractError(f"Approved graph root does not exist: {node_id}")
            selection = index.neighborhood(node_id, 2, "implementer", 80)
            for node in selection.nodes:
                selected_nodes[node["id"]] = node
            for edge in selection.edges:
                selected_edges[edge["id"]] = edge
            if selection.truncated:
                base["truncated"] = True

        for node_id in sorted(selected_nodes):
            node = selected_nodes[node_id]
            item = {
                "id": node["id"],
                "kind": node["kind"],
                "name": node["name"],
                "properties": node.get("properties", {}),
                "evidence": node.get("evidence", []),
            }
            if not self._append_within(base, "nodes", item, order):
                base["truncated"] = True
                break
        included_nodes = {item["id"] for item in base["nodes"]}
        for edge_id in sorted(selected_edges):
            edge = selected_edges[edge_id]
            if edge["source"] not in included_nodes or edge["target"] not in included_nodes:
                continue
            item = {
                "id": edge["id"],
                "source": edge["source"],
                "relation": edge["relation"],
                "target": edge["target"],
                "properties": edge.get("properties", {}),
                "evidence": edge.get("evidence", []),
            }
            if not self._append_within(base, "edges", item, order):
                base["truncated"] = True
                break

        if self.evidence_path and self.evidence_path.is_file():
            pack = load_evidence_pack(self.evidence_path)
            if pack.get("graph_content_sha256") != graph["content_sha256"]:
                raise ContractError("Source evidence pack does not match the knowledge graph")
            base["evidence_pack_sha256"] = pack.get("content_sha256")
            wanted = {
                (owner_type, item["id"], evidence_index)
                for owner_type, records in (("node", base["nodes"]), ("edge", base["edges"]))
                for item in records
                for evidence_index, _ in enumerate(item.get("evidence", []))
            }
            seen: set[str] = set()
            for capsule in pack.get("capsules", []):
                supports = [
                    support
                    for support in capsule.get("supports", [])
                    if (
                        support.get("owner_type"),
                        support.get("owner_id"),
                        support.get("evidence_index"),
                    )
                    in wanted
                    and support.get("visibility") == "shared"
                ]
                if not supports or capsule["capsule_id"] in seen:
                    continue
                seen.add(capsule["capsule_id"])
                excerpt = {
                    key: value
                    for key, value in capsule.items()
                    if key != "supports"
                }
                excerpt["supports"] = supports
                if not self._append_within(base, "source_excerpts", excerpt, order):
                    base["truncated"] = True
                    break
        else:
            base["limitations"].append("No source evidence pack was supplied to this run.")

        if "inspector_private" in json.dumps(base, sort_keys=True):
            raise ContractError("Implementer context contains verifier-private content")
        base["limitations"].append(
            "Context is bounded to approved roots, two graph hops, shared evidence, and explicit byte limits."
        )
        return self._finish(base, order)

    @staticmethod
    def planner_context(context: dict[str, Any]) -> dict[str, Any]:
        """Project the full evidence bundle into a compact planner catalog.

        The controller retains the complete implementer context as an artifact.  The
        planner receives identifiers and short previews so it can select evidence for
        a task without paying to reread every source excerpt.
        """
        nodes = [
            {
                "id": item["id"],
                "kind": item["kind"],
                "name": item["name"],
                "properties": _compact_properties(item.get("properties", {})),
            }
            for item in context.get("nodes", [])
        ]
        edges = [
            {
                "id": item["id"],
                "source": item["source"],
                "relation": item["relation"],
                "target": item["target"],
            }
            for item in context.get("edges", [])
        ]
        evidence_catalog = []
        for excerpt in context.get("source_excerpts", []):
            highlighted = [
                str(line.get("text", ""))
                for line in excerpt.get("lines", [])
                if line.get("highlighted")
            ]
            preview_lines = highlighted or [
                str(line.get("text", "")) for line in excerpt.get("lines", [])[:3]
            ]
            preview = "\n".join(preview_lines)[:480]
            evidence_catalog.append(
                {
                    "capsule_id": excerpt["capsule_id"],
                    "path": excerpt.get("path"),
                    "language": excerpt.get("language"),
                    "line_start": excerpt.get("line_start"),
                    "line_end": excerpt.get("line_end"),
                    "confidence": excerpt.get("confidence"),
                    "preview": preview,
                    "supports": [
                        {
                            "owner_type": support.get("owner_type"),
                            "owner_id": support.get("owner_id"),
                        }
                        for support in excerpt.get("supports", [])
                    ],
                }
            )
        allowed_files = [
            {
                key: item.get(key)
                for key in ("path", "bytes", "sha256", "truncated")
            }
            for item in context.get("allowed_files", [])
        ]
        payload = {
            "schema_version": "1.0",
            "context_type": "lightyear-planner-evidence-catalog",
            "audience": "implementer",
            "source_context_sha256": context.get("content_sha256"),
            "graph_content_sha256": context.get("graph_content_sha256"),
            "evidence_pack_sha256": context.get("evidence_pack_sha256"),
            "approved_roots": context.get("approved_roots", []),
            "nodes": nodes,
            "edges": edges,
            "evidence_catalog": evidence_catalog,
            "allowed_files": allowed_files,
            "limitations": [
                *context.get("limitations", []),
                "Source bodies are omitted; tasks select evidence_capsule_ids for builder retrieval.",
            ],
        }
        payload["statistics"] = {
            "nodes": len(nodes),
            "edges": len(edges),
            "evidence_catalog_entries": len(evidence_catalog),
            "allowed_files": len(allowed_files),
            "source_context_bytes": context.get("statistics", {}).get("context_bytes", 0),
        }
        return _finish_projection(payload)

    @staticmethod
    def builder_context(
        context: dict[str, Any],
        evidence_capsule_ids: list[str],
        graph_node_ids: list[str],
    ) -> dict[str, Any]:
        """Retrieve only plan-selected graph and source evidence for the builder."""
        node_by_id = {item["id"]: item for item in context.get("nodes", [])}
        edge_by_id = {item["id"]: item for item in context.get("edges", [])}
        excerpt_by_id = {
            item["capsule_id"]: item for item in context.get("source_excerpts", [])
        }
        unknown_capsules = sorted(set(evidence_capsule_ids) - set(excerpt_by_id))
        if unknown_capsules:
            raise ContractError(
                "Planner selected unknown evidence capsule(s): "
                + ", ".join(unknown_capsules[:10])
            )
        unknown_nodes = sorted(set(graph_node_ids) - set(node_by_id))
        if unknown_nodes:
            raise ContractError(
                "Planner selected unknown graph node(s): " + ", ".join(unknown_nodes[:10])
            )

        selected_excerpts = [excerpt_by_id[item] for item in dict.fromkeys(evidence_capsule_ids)]
        selected_node_ids = set(graph_node_ids)
        selected_edge_ids: set[str] = set()
        for excerpt in selected_excerpts:
            for support in excerpt.get("supports", []):
                if support.get("owner_type") == "node":
                    selected_node_ids.add(str(support.get("owner_id")))
                elif support.get("owner_type") == "edge":
                    selected_edge_ids.add(str(support.get("owner_id")))
        for edge_id in list(selected_edge_ids):
            edge = edge_by_id.get(edge_id)
            if edge:
                selected_node_ids.update((edge["source"], edge["target"]))
        selected_edges = [
            item
            for item in context.get("edges", [])
            if item["id"] in selected_edge_ids
            or (item["source"] in selected_node_ids and item["target"] in selected_node_ids)
        ]
        for edge in selected_edges:
            selected_node_ids.update((edge["source"], edge["target"]))
        selected_nodes = [
            item for item in context.get("nodes", []) if item["id"] in selected_node_ids
        ]
        payload = {
            "schema_version": "1.0",
            "context_type": "lightyear-builder-selected-evidence",
            "audience": "implementer",
            "source_context_sha256": context.get("content_sha256"),
            "graph_content_sha256": context.get("graph_content_sha256"),
            "evidence_pack_sha256": context.get("evidence_pack_sha256"),
            "selected_evidence_capsule_ids": list(dict.fromkeys(evidence_capsule_ids)),
            "selected_graph_node_ids": list(dict.fromkeys(graph_node_ids)),
            "nodes": selected_nodes,
            "edges": selected_edges,
            "source_excerpts": selected_excerpts,
            "limitations": [
                "Evidence is restricted to identifiers selected in the approved planner artifact."
            ],
        }
        payload["statistics"] = {
            "nodes": len(selected_nodes),
            "edges": len(selected_edges),
            "source_excerpts": len(selected_excerpts),
            "source_context_bytes": context.get("statistics", {}).get("context_bytes", 0),
        }
        return _finish_projection(payload)

    @staticmethod
    def _append_within(
        payload: dict[str, Any], key: str, item: dict[str, Any], order: WorkOrder
    ) -> bool:
        payload[key].append(item)
        size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if size > order.max_context_bytes:
            payload[key].pop()
            return False
        return True

    @staticmethod
    def _finish(payload: dict[str, Any], order: WorkOrder) -> dict[str, Any]:
        payload["statistics"] = {
            "nodes": len(payload["nodes"]),
            "edges": len(payload["edges"]),
            "source_excerpts": len(payload["source_excerpts"]),
            "allowed_files": len(payload["allowed_files"]),
            "context_bytes": len(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ),
            "max_context_bytes": order.max_context_bytes,
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload


def _compact_properties(properties: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(properties):
        value = properties[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value[:240] if isinstance(value, str) else value
    return result


def _finish_projection(payload: dict[str, Any]) -> dict[str, Any]:
    payload["statistics"]["context_bytes"] = len(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    source_bytes = int(payload["statistics"].get("source_context_bytes", 0) or 0)
    projected_bytes = payload["statistics"]["context_bytes"]
    payload["statistics"]["reduction_ratio"] = (
        round(1 - projected_bytes / source_bytes, 4) if source_bytes else 0.0
    )
    payload["content_sha256"] = canonical_hash(payload)
    return payload
