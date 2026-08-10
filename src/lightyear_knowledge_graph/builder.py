from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .extractors import LEGACY_SOURCE_ID, MODERN_SOURCE_ID, extract_legacy, extract_modern
from .model import KnowledgeGraph, evidence


def build_graph(
    legacy_root: Path,
    modern_root: Path,
    manifest_path: Path,
    legacy_commit: str,
    modern_commit: str = "working-tree",
) -> KnowledgeGraph:
    graph = KnowledgeGraph(
        "lightyear:carddemo-modernization",
        [
            {
                "id": LEGACY_SOURCE_ID,
                "kind": "git_repository",
                "repository": "https://github.com/aws-samples/aws-mainframe-modernization-carddemo",
                "commit": legacy_commit,
            },
            {
                "id": MODERN_SOURCE_ID,
                "kind": "git_repository",
                "repository": "https://github.com/howardweale/lightyear-carddemo-modernization",
                "commit": modern_commit,
            },
        ],
    )
    extract_legacy(graph, legacy_root)
    extract_modern(graph, modern_root)
    _apply_manifest(graph, manifest_path)
    return graph


def _apply_manifest(graph: KnowledgeGraph, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_id = MODERN_SOURCE_ID
    manifest_relative = manifest_path.name
    mapping_evidence = [
        evidence(
            source_id,
            f"knowledge/mappings/{manifest_relative}",
            1,
            method="curated-mapping",
            confidence="asserted",
        )
    ]
    for workload in manifest["workloads"]:
        workload_id = workload["id"]
        graph.add_node(
            workload_id,
            "modernization_workload",
            workload["name"],
            properties={
                "status": workload["status"],
                "visibility": workload.get("visibility", "shared"),
            },
            evidence_items=mapping_evidence,
        )
        for node_id in workload.get("legacy_entrypoints", []):
            _require_node(graph, node_id, workload_id)
            graph.add_edge(workload_id, "LEGACY_ENTRYPOINT", node_id, evidence_items=mapping_evidence)
        for node_id in workload.get("modern_entrypoints", []):
            _require_node(graph, node_id, workload_id)
            graph.add_edge(workload_id, "MODERN_ENTRYPOINT", node_id, evidence_items=mapping_evidence)
        for node_id in workload.get("scheduled_by", []):
            _require_node(graph, node_id, workload_id)
            graph.add_edge(workload_id, "SCHEDULED_BY", node_id, evidence_items=mapping_evidence)

        for scenario in workload.get("scenarios", []):
            graph.add_node(
                scenario["id"],
                "verification_scenario",
                scenario["name"],
                properties={
                    "visibility": scenario.get("visibility", "shared"),
                    "kind": scenario["kind"],
                    "status": scenario.get("status", "defined"),
                },
            )
            graph.add_edge(workload_id, "HAS_SCENARIO", scenario["id"], evidence_items=mapping_evidence)

        for rule in workload["rules"]:
            rule_id = rule["id"]
            graph.add_node(
                rule_id,
                "business_rule",
                rule["name"],
                properties={
                    "statement": rule["statement"],
                    "status": rule.get("status", "mapped"),
                    "visibility": rule.get("visibility", "shared"),
                    "confidence": rule.get("confidence", "asserted"),
                },
            )
            graph.add_edge(workload_id, "HAS_RULE", rule_id, evidence_items=mapping_evidence)
            for source in rule.get("derived_from", []):
                node_id = source["node"]
                _require_node(graph, node_id, rule_id)
                graph.add_edge(
                    rule_id,
                    "DERIVED_FROM",
                    node_id,
                    evidence_items=[
                        evidence(
                            LEGACY_SOURCE_ID,
                            source["path"],
                            source["line_start"],
                            source.get("line_end"),
                            method=source.get("method", "source-analysis"),
                            confidence=source.get("confidence", "observed"),
                        )
                    ],
                )
            for node_id in rule.get("implemented_by", []):
                _require_node(graph, node_id, rule_id)
                graph.add_edge(rule_id, "IMPLEMENTED_BY", node_id, evidence_items=mapping_evidence)
            for node_id in rule.get("verified_by", []):
                _require_node(graph, node_id, rule_id)
                graph.add_edge(rule_id, "VERIFIED_BY", node_id, evidence_items=mapping_evidence)


def _require_node(graph: KnowledgeGraph, node_id: str, owner: str) -> None:
    if node_id not in graph.nodes:
        raise ValueError(f"Mapping {owner} references missing graph node {node_id}")


def write_receipt(graph_payload: dict[str, Any], path: Path) -> None:
    receipt = {
        "receipt_type": "lightyear-knowledge-graph-build",
        "graph_id": graph_payload["graph_id"],
        "schema_version": graph_payload["schema_version"],
        "content_sha256": graph_payload["content_sha256"],
        "sources": graph_payload["sources"],
        "statistics": graph_payload["statistics"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
