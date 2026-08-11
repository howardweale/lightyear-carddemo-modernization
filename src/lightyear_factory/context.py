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

