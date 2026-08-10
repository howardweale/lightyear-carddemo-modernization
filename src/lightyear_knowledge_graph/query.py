from __future__ import annotations

from collections import deque
from typing import Any


def neighborhood(
    payload: dict[str, Any],
    node_id: str,
    depth: int = 1,
    audience: str = "shared",
) -> dict[str, Any]:
    node_by_id = {node["id"]: node for node in payload["nodes"]}
    if node_id not in node_by_id:
        raise KeyError(node_id)
    adjacency: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for edge in payload["edges"]:
        adjacency.setdefault(edge["source"], []).append((edge, edge["target"]))
        adjacency.setdefault(edge["target"], []).append((edge, edge["source"]))
    seen = {node_id}
    selected_edges: dict[str, dict[str, Any]] = {}
    queue = deque([(node_id, 0)])
    while queue:
        current, distance = queue.popleft()
        if distance >= depth:
            continue
        for edge, neighbor in adjacency.get(current, []):
            node = node_by_id[neighbor]
            if audience == "implementer" and node.get("properties", {}).get("visibility") == "inspector_private":
                continue
            selected_edges[edge["id"]] = edge
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
    return {
        "root": node_id,
        "depth": depth,
        "audience": audience,
        "nodes": [node_by_id[item] for item in sorted(seen)],
        "edges": [selected_edges[item] for item in sorted(selected_edges)],
    }


def shortest_trace(payload: dict[str, Any], source: str, target: str) -> dict[str, Any] | None:
    node_ids = {node["id"] for node in payload["nodes"]}
    if source not in node_ids or target not in node_ids:
        missing = source if source not in node_ids else target
        raise KeyError(missing)
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for edge in payload["edges"]:
        adjacency.setdefault(edge["source"], []).append((edge["target"], edge))
        adjacency.setdefault(edge["target"], []).append((edge["source"], edge))
    queue = deque([source])
    previous: dict[str, tuple[str, dict[str, Any]]] = {}
    seen = {source}
    while queue:
        current = queue.popleft()
        if current == target:
            break
        for neighbor, edge in sorted(adjacency.get(current, []), key=lambda item: item[0]):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            previous[neighbor] = (current, edge)
            queue.append(neighbor)
    if target not in seen:
        return None
    nodes = [target]
    edges = []
    while nodes[-1] != source:
        parent, edge = previous[nodes[-1]]
        edges.append(edge)
        nodes.append(parent)
    nodes.reverse()
    edges.reverse()
    return {"nodes": nodes, "edges": edges}
