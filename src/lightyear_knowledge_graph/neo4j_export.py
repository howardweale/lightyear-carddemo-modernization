from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


def _label(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    return "".join(word[:1].upper() + word[1:] for word in words) or "Entity"


def _relationship_type(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.upper()).strip("_")
    return normalized or "RELATED_TO"


def export_neo4j(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write lossless CSV projections for Neo4j Data Importer or neo4j-admin."""
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = output_dir / "nodes.csv"
    relationships_path = output_dir / "relationships.csv"
    constraints_path = output_dir / "constraints.cypher"
    receipt_path = output_dir / "export-receipt.json"

    with nodes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["nodeId:ID", "name", "kind", "propertiesJson", "evidenceJson", ":LABEL"]
        )
        for node in sorted(payload["nodes"], key=lambda item: item["id"]):
            writer.writerow(
                [
                    node["id"],
                    node["name"],
                    node["kind"],
                    json.dumps(node.get("properties", {}), sort_keys=True, separators=(",", ":")),
                    json.dumps(node.get("evidence", []), sort_keys=True, separators=(",", ":")),
                    f"Entity;{_label(node['kind'])}",
                ]
            )

    with relationships_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                ":START_ID",
                ":END_ID",
                "relation",
                "propertiesJson",
                "evidenceJson",
                ":TYPE",
            ]
        )
        for edge in sorted(payload["edges"], key=lambda item: item["id"]):
            writer.writerow(
                [
                    edge["source"],
                    edge["target"],
                    edge["relation"],
                    json.dumps(edge.get("properties", {}), sort_keys=True, separators=(",", ":")),
                    json.dumps(edge.get("evidence", []), sort_keys=True, separators=(",", ":")),
                    _relationship_type(edge["relation"]),
                ]
            )

    constraints_path.write_text(
        "CREATE CONSTRAINT lightyear_entity_id IF NOT EXISTS\n"
        "FOR (entity:Entity) REQUIRE entity.nodeId IS UNIQUE;\n",
        encoding="utf-8",
    )
    receipt = {
        "receipt_type": "lightyear-neo4j-projection",
        "graph_id": payload["graph_id"],
        "graph_content_sha256": payload["content_sha256"],
        "node_count": len(payload["nodes"]),
        "relationship_count": len(payload["edges"]),
        "files": {
            "nodes": nodes_path.name,
            "relationships": relationships_path.name,
            "constraints": constraints_path.name,
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt

