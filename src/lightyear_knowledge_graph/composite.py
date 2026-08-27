from __future__ import annotations

import gzip
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .inputs import canonical_hash
from .model import graph_hash, load_graph
from .validation import validate_graph


PROJECTION_TYPE = "lightyear-composite-estate"


class CompositeEstateError(ValueError):
    """Raised when separately governed graph evidence cannot be composed safely."""


def build_composite_estate(
    base_graph: dict[str, Any],
    fragments: list[dict[str, Any]],
    capability_projection: dict[str, Any],
) -> dict[str, Any]:
    base_errors = validate_graph(base_graph)
    if base_errors:
        raise CompositeEstateError("canonical graph is invalid: " + "; ".join(base_errors))
    if not fragments:
        raise CompositeEstateError("composite estate requires at least one extension fragment")

    nodes = deepcopy(base_graph["nodes"])
    edges = deepcopy(base_graph["edges"])
    known_nodes = {node["id"] for node in nodes}
    known_edges = {edge["id"] for edge in edges}
    fragment_bindings = []
    for fragment in sorted(fragments, key=lambda item: item.get("fragment_id", "")):
        errors = validate_fragment_binding(fragment, base_graph)
        if errors:
            raise CompositeEstateError("extension fragment is invalid: " + "; ".join(errors))
        fragment_nodes = deepcopy(fragment["nodes"])
        fragment_edges = deepcopy(fragment["edges"])
        duplicates = sorted(known_nodes & {node["id"] for node in fragment_nodes})
        if duplicates:
            raise CompositeEstateError(f"extension fragment shadows graph node: {duplicates[0]}")
        duplicate_edges = sorted(known_edges & {edge["id"] for edge in fragment_edges})
        if duplicate_edges:
            raise CompositeEstateError(f"extension fragment shadows graph edge: {duplicate_edges[0]}")
        nodes.extend(fragment_nodes)
        edges.extend(fragment_edges)
        known_nodes.update(node["id"] for node in fragment_nodes)
        known_edges.update(edge["id"] for edge in fragment_edges)
        fragment_bindings.append(
            {
                "fragment_id": fragment["fragment_id"],
                "fragment_type": fragment["fragment_type"],
                "language": fragment["language_pack"]["language"],
                "content_sha256": fragment["content_sha256"],
                "limitations": fragment["limitations"],
            }
        )

    capability_errors = validate_capability_binding(capability_projection, base_graph, fragments)
    if capability_errors:
        raise CompositeEstateError(
            "capability projection is invalid: " + "; ".join(capability_errors)
        )

    payload = {
        "schema_version": base_graph["schema_version"],
        "graph_id": f"{base_graph['graph_id']}:composite",
        "projection_type": PROJECTION_TYPE,
        "relationship_ontology": deepcopy(base_graph["relationship_ontology"]),
        "base_graph": {
            "graph_id": base_graph["graph_id"],
            "schema_version": base_graph["schema_version"],
            "content_sha256": base_graph["content_sha256"],
        },
        "fragments": fragment_bindings,
        "capability_projection": _capability_summary(capability_projection),
        "claim_boundary": {
            "composite_is_read_only": True,
            "changes_canonical_graph": False,
            "proves_runtime_behavior": False,
            "mainframe_equivalent": False,
            "production_ready": False,
            "statement": (
                "The projection composes separately validated discovery and development evidence; "
                "it does not promote live-mainframe or production claims."
            ),
        },
        "sources": deepcopy(base_graph["sources"]),
        "statistics": _statistics(nodes, edges),
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: item["id"]),
    }
    payload["content_sha256"] = graph_hash(payload)
    errors = validate_composite_estate(payload, base_graph, fragments, capability_projection)
    if errors:
        raise CompositeEstateError("generated composite estate is invalid: " + "; ".join(errors))
    return payload


def validate_fragment_binding(
    fragment: dict[str, Any], base_graph: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if fragment.get("fragment_type") != "lightyear-graph-extension":
        errors.append("fragment_type is invalid")
    if fragment.get("content_sha256") != canonical_hash(fragment):
        errors.append("fragment content_sha256 is invalid")
    binding = fragment.get("base_graph", {})
    if binding.get("graph_id") != base_graph.get("graph_id"):
        errors.append("fragment targets a different graph_id")
    if binding.get("content_sha256") != base_graph.get("content_sha256"):
        errors.append("fragment targets a different graph content identity")
    nodes = fragment.get("nodes", [])
    edges = fragment.get("edges", [])
    node_ids = [node.get("id") for node in nodes]
    edge_ids = [edge.get("id") for edge in edges]
    if len(node_ids) != len(set(node_ids)):
        errors.append("fragment contains duplicate node ids")
    if len(edge_ids) != len(set(edge_ids)):
        errors.append("fragment contains duplicate edge ids")
    available = set(node_ids) | {node["id"] for node in base_graph.get("nodes", [])}
    for edge in edges:
        if edge.get("source") not in available or edge.get("target") not in available:
            errors.append(f"fragment edge has an unresolved endpoint: {edge.get('id')}")
    declared_external = {item.get("entity_id") for item in fragment.get("external_references", [])}
    base_ids = {node["id"] for node in base_graph.get("nodes", [])}
    if not declared_external <= base_ids:
        errors.append("fragment has an unresolved external reference")
    if not fragment.get("limitations"):
        errors.append("fragment must retain explicit limitations")
    return errors


def validate_capability_binding(
    capability: dict[str, Any],
    base_graph: dict[str, Any],
    fragments: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if capability.get("content_sha256") != canonical_hash(capability):
        errors.append("capability content_sha256 is invalid")
    if capability.get("graph_content_sha256") != base_graph.get("content_sha256"):
        errors.append("capability targets a different canonical graph")
    expected_fragments = {fragment["content_sha256"] for fragment in fragments}
    bound_fragment = capability.get("evidence_bindings", {}).get("pli_fragment_sha256")
    if bound_fragment not in expected_fragments:
        errors.append("capability does not bind the composed PL/I fragment")
    if any(item.get("mainframe_equivalent") is not False for item in capability.get("capabilities", [])):
        errors.append("capability projection overstates mainframe equivalence")
    if any(
        item.get("production_ready") is not False
        for item in capability.get("collection_mechanisms", [])
    ):
        errors.append("capability collection mechanism overstates production readiness")
    return errors


def validate_composite_estate(
    payload: dict[str, Any],
    base_graph: dict[str, Any] | None = None,
    fragments: list[dict[str, Any]] | None = None,
    capability_projection: dict[str, Any] | None = None,
) -> list[str]:
    errors = validate_graph(payload)
    if payload.get("projection_type") != PROJECTION_TYPE:
        errors.append("composite projection_type is invalid")
    if payload.get("content_sha256") != graph_hash(payload):
        errors.append("composite content_sha256 is invalid")
    boundary = payload.get("claim_boundary", {})
    expected_boundary = {
        "composite_is_read_only": True,
        "changes_canonical_graph": False,
        "proves_runtime_behavior": False,
        "mainframe_equivalent": False,
        "production_ready": False,
    }
    for key, value in expected_boundary.items():
        if boundary.get(key) is not value:
            errors.append(f"composite claim boundary is invalid: {key}")
    if base_graph is not None:
        binding = payload.get("base_graph", {})
        if binding.get("content_sha256") != base_graph.get("content_sha256"):
            errors.append("composite targets a different base graph")
        expected_base_nodes = {node["id"] for node in base_graph.get("nodes", [])}
        actual_nodes = {node["id"] for node in payload.get("nodes", [])}
        if not expected_base_nodes <= actual_nodes:
            errors.append("composite omits canonical graph nodes")
    if fragments is not None:
        expected = {fragment["content_sha256"] for fragment in fragments}
        actual = {item.get("content_sha256") for item in payload.get("fragments", [])}
        if expected != actual:
            errors.append("composite fragment bindings are stale")
    if capability_projection is not None:
        if payload.get("capability_projection", {}).get("content_sha256") != capability_projection.get(
            "content_sha256"
        ):
            errors.append("composite capability binding is stale")
    return sorted(set(errors))


def write_composite_estate(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(serialized, compresslevel=9, mtime=0))
    else:
        path.write_bytes(serialized)


def write_composite_receipt(payload: dict[str, Any], path: Path) -> None:
    write_json(
        path,
        {
            "receipt_type": "lightyear-composite-estate-build",
            "schema_version": "1.0",
            "composite_graph_id": payload["graph_id"],
            "content_sha256": payload["content_sha256"],
            "base_graph": payload["base_graph"],
            "fragments": payload["fragments"],
            "capability_projection": payload["capability_projection"],
            "claim_boundary": payload["claim_boundary"],
            "statistics": payload["statistics"],
        },
    )


def load_json(path: Path) -> dict[str, Any]:
    return load_graph(path) if path.suffix == ".gz" else json.loads(path.read_text(encoding="utf-8"))


def _capability_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload["schema_version"],
        "content_sha256": payload["content_sha256"],
        "truth_boundary": payload["truth_boundary"],
        "capabilities": [
            {
                "technology": item["technology"],
                "capability_kind": item["capability_kind"],
                "discovery_ready": item["discovery_ready"],
                "development_ready": item["development_ready"],
                "mainframe_equivalent": item["mainframe_equivalent"],
            }
            for item in payload["capabilities"]
        ],
        "collection_mechanisms": deepcopy(payload["collection_mechanisms"]),
    }


def _statistics(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes_by_kind": dict(sorted(Counter(node["kind"] for node in nodes).items())),
        "edges_by_relation": dict(sorted(Counter(edge["relation"] for edge in edges).items())),
    }
