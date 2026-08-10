from __future__ import annotations

from collections import Counter
from typing import Any

from .model import SCHEMA_VERSION, graph_hash


ALLOWED_CONFIDENCE = {"observed", "asserted", "inferred", "verified"}
REQUIRED_RULE_RELATIONS = {"DERIVED_FROM", "IMPLEMENTED_BY", "VERIFIED_BY"}


def validate_graph(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {payload.get('schema_version')}")
    if payload.get("content_sha256") != graph_hash(payload):
        errors.append("content_sha256 does not match canonical graph content")

    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    node_ids = [item.get("id") for item in nodes]
    edge_ids = [item.get("id") for item in edges]
    for duplicate in _duplicates(node_ids):
        errors.append(f"duplicate node id: {duplicate}")
    for duplicate in _duplicates(edge_ids):
        errors.append(f"duplicate edge id: {duplicate}")
    node_id_set = set(node_ids)
    source_ids = {item.get("id") for item in payload.get("sources", [])}
    for edge in edges:
        if edge.get("source") not in node_id_set:
            errors.append(f"edge {edge.get('id')} has missing source {edge.get('source')}")
        if edge.get("target") not in node_id_set:
            errors.append(f"edge {edge.get('id')} has missing target {edge.get('target')}")
    for item in [*nodes, *edges]:
        for ev in item.get("evidence", []):
            if ev.get("source_id") not in source_ids:
                errors.append(f"{item.get('id')} evidence has unknown source {ev.get('source_id')}")
            if ev.get("confidence") not in ALLOWED_CONFIDENCE:
                errors.append(f"{item.get('id')} evidence has invalid confidence {ev.get('confidence')}")
            if not isinstance(ev.get("line_start"), int) or ev.get("line_start", 0) < 1:
                errors.append(f"{item.get('id')} evidence has invalid line_start")

    outgoing: dict[str, set[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge["source"], set()).add(edge["relation"])
    for node in nodes:
        if node.get("kind") != "business_rule":
            continue
        missing = REQUIRED_RULE_RELATIONS - outgoing.get(node["id"], set())
        for relation in sorted(missing):
            errors.append(f"business rule {node['id']} is missing {relation}")

    stats = payload.get("statistics", {})
    if stats.get("node_count") != len(nodes):
        errors.append("statistics.node_count is stale")
    if stats.get("edge_count") != len(edges):
        errors.append("statistics.edge_count is stale")
    return errors


def rule_gaps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    outgoing: dict[str, set[str]] = {}
    for edge in payload["edges"]:
        outgoing.setdefault(edge["source"], set()).add(edge["relation"])
    gaps = []
    for node in payload["nodes"]:
        if node["kind"] != "business_rule":
            continue
        missing = sorted(REQUIRED_RULE_RELATIONS - outgoing.get(node["id"], set()))
        if missing:
            gaps.append({"rule": node["id"], "missing_relations": missing})
    return gaps


def _duplicates(items: list[Any]) -> list[Any]:
    return sorted(item for item, count in Counter(items).items() if count > 1)
