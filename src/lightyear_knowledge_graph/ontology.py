from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_ONTOLOGY_PATH = (
    Path(__file__).resolve().parents[2] / "knowledge" / "ontology" / "relationships.json"
)


def load_ontology(path: Path = DEFAULT_ONTOLOGY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ontology_hash(ontology: dict[str, Any]) -> str:
    canonical = json.dumps(ontology, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def ontology_identity(ontology: dict[str, Any]) -> dict[str, str]:
    return {
        "ontology_id": ontology["ontology_id"],
        "schema_version": ontology["schema_version"],
        "content_sha256": ontology_hash(ontology),
    }


def validate_ontology(ontology: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if ontology.get("schema_version") != "1.0":
        errors.append(f"unsupported relationship ontology version: {ontology.get('schema_version')}")
    if not ontology.get("ontology_id"):
        errors.append("relationship ontology is missing ontology_id")
    relations = ontology.get("relations")
    if not isinstance(relations, dict) or not relations:
        return [*errors, "relationship ontology has no relations"]
    for relation, definition in sorted(relations.items()):
        if relation != relation.upper():
            errors.append(f"relationship name must be uppercase: {relation}")
        for field in ("label", "purpose", "category", "direction", "evidence_policy"):
            if not isinstance(definition.get(field), str) or not definition[field].strip():
                errors.append(f"relationship {relation} is missing {field}")
        pairs = definition.get("allowed_pairs")
        if not isinstance(pairs, list) or not pairs:
            errors.append(f"relationship {relation} has no allowed_pairs")
            continue
        for pair in pairs:
            if not isinstance(pair, list) or len(pair) != 2 or not all(
                isinstance(value, str) and value for value in pair
            ):
                errors.append(f"relationship {relation} has invalid allowed pair: {pair}")
    return errors


def validate_graph_relationships(
    payload: dict[str, Any], ontology: dict[str, Any]
) -> list[str]:
    errors = validate_ontology(ontology)
    identity = payload.get("relationship_ontology", {})
    expected_identity = ontology_identity(ontology)
    if identity != expected_identity:
        errors.append("relationship ontology identity does not match the canonical ontology")
    nodes = {node["id"]: node for node in payload.get("nodes", [])}
    relations = ontology.get("relations", {})
    for edge in payload.get("edges", []):
        relation = edge.get("relation")
        definition = relations.get(relation)
        if definition is None:
            errors.append(f"edge {edge.get('id')} uses undefined relationship {relation}")
            continue
        source = nodes.get(edge.get("source"))
        target = nodes.get(edge.get("target"))
        if source is None or target is None:
            continue
        pair = [source["kind"], target["kind"]]
        if pair not in definition["allowed_pairs"]:
            errors.append(
                f"edge {edge.get('id')} uses invalid {relation} pair "
                f"{source['kind']} -> {target['kind']}"
            )
    return errors
