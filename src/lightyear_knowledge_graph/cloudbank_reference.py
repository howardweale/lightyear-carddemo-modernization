from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .composite import validate_fragment_binding
from .inputs import canonical_hash


OPERATOR_ESTATE_ID = "cloudbank-reference"
OPERATOR_ESTATE_NAME = "CloudBank Reference Estate"
FRAGMENT_ID = "lightyear:cloudbank-modern-oracle-reference-v1"
SOURCE_ID = "source:lightyear-carddemo"
SOURCE_PATH = "reference-estates/cloudbank/workloads.json"


def build_cloudbank_reference_fragment(
    base_graph: dict[str, Any],
    workloads: dict[str, Any],
    inventory: dict[str, Any],
    source_pin: dict[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    pin = source_pin["source"]
    estate = inventory["estate"]

    for workload in sorted(workloads["workloads"], key=lambda item: item["id"]):
        workload_id = f"cloudbank-reference:workload:{workload['id']}"
        workload_line = _source_line(f'"id": "{workload["id"]}"')
        common_properties = {
            "application_architecture": "cloud-native-microservices",
            "customer_id": OPERATOR_ESTATE_ID,
            "evidence_class": workloads["evidence_class"],
            "migration_complete": False,
            "operator_platform": "Oracle",
            "postgresql_mapping_complete": False,
            "production_ready": False,
            "runtime_observed": False,
            "source_commit": pin["commit"],
            "source_product": "CloudBank v5",
            "source_repository": pin["repository"],
            "target_equivalent": False,
        }
        nodes.append(
            {
                "id": workload_id,
                "kind": "modernization_workload",
                "name": workload["name"],
                "properties": {
                    **common_properties,
                    "business_problem": workload["business_problem"],
                    "business_question": workload["business_question"],
                    "estate_inventory": {
                        "deployable_units": estate["deployable_unit_count"],
                        "java_source_units": estate["java_source_units"],
                        "runtime_service_modules": estate["runtime_service_module_count"],
                        "sql_files": estate["sql_files"],
                        "tracked_files": estate["tracked_files"],
                    },
                    "migration_risk_count": len(workload["migration_risks"]),
                    "services": deepcopy(workload["services"]),
                    "source_paths": deepcopy(workload["source_paths"]),
                    "statement": (
                        f"Pinned static modern-Oracle workload for {OPERATOR_ESTATE_NAME}; "
                        "no runtime or target equivalence is attached."
                    ),
                    "status": "reference-projected",
                    "target_posture": deepcopy(workloads["target_posture"]),
                },
                "evidence": [_evidence(workload_line, "curated-cloudbank-workload-v1")],
            }
        )
        for sequence, risk in enumerate(workload["migration_risks"], start=1):
            scenario_id = f"cloudbank-reference:scenario:{workload['id']}:{sequence:02d}"
            risk_line = _source_line(f'"id": "{risk["id"]}"')
            nodes.append(
                {
                    "id": scenario_id,
                    "kind": "verification_scenario",
                    "name": f"{workload['name']} risk {sequence:02d}: {risk['name']}",
                    "properties": {
                        **common_properties,
                        "migration_risk_id": risk["id"],
                        "scenario_kind": "static-modern-oracle-migration-risk",
                        "sequence": sequence,
                        "statement": risk["statement"],
                        "workload_id": workload_id,
                    },
                    "evidence": [_evidence(risk_line, "curated-cloudbank-migration-risk-v1")],
                }
            )
            edges.append(
                {
                    "id": f"cloudbank-reference:edge:{workload['id']}:{sequence:02d}",
                    "source": workload_id,
                    "target": scenario_id,
                    "relation": "HAS_SCENARIO",
                    "properties": {
                        "claim_boundary": "static-modern-oracle-migration-risk",
                        "sequence": sequence,
                    },
                    "evidence": [_evidence(risk_line, "curated-cloudbank-migration-risk-v1")],
                }
            )

    payload = {
        "schema_version": "1.0",
        "fragment_type": "lightyear-graph-extension",
        "fragment_id": FRAGMENT_ID,
        "base_graph": {
            "graph_id": base_graph["graph_id"],
            "schema_version": base_graph["schema_version"],
            "content_sha256": base_graph["content_sha256"],
        },
        "language_pack": {
            "extensions": [".java", ".sql", ".yaml", ".xml", ".sh"],
            "id": "lightyear.cloudbank-reference",
            "language": "Modern Oracle reference estate",
            "version": "1.0",
        },
        "source": {
            "acquisition_mode": source_pin["acquisition"]["mode"],
            "inventory": "reference-estates/cloudbank/inventory.json",
            "license": deepcopy(source_pin["license"]),
            "operator_estate_id": OPERATOR_ESTATE_ID,
            "operator_estate_name": OPERATOR_ESTATE_NAME,
            "source_pin": "reference-estates/cloudbank/source-pin.json",
            "subtree": pin["subtree"],
            "upstream_commit": pin["commit"],
            "upstream_product": "CloudBank v5",
            "upstream_repository": pin["repository"],
            "upstream_root_tree": pin["root_tree"],
            "upstream_subtree_tree": pin["subtree_tree"],
            "workloads": SOURCE_PATH,
        },
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: item["id"]),
        "external_references": [],
        "statistics": _statistics(nodes, edges),
        "limitations": [
            "CloudBank Reference Estate is an official upstream reference application, not an attached customer system.",
            "The projection is derived from a pinned static inventory and curated migration risks; CloudBank was not built or executed.",
            "Oracle coupling is identified but no PostgreSQL or other target mapping is complete or selected.",
            "Static source evidence does not prove application equivalence, migration completion, runtime behavior, or production readiness.",
            "The fragment is bound to one exact canonical graph identity and fails closed after graph drift.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_cloudbank_reference_fragment(
    fragment: dict[str, Any],
    base_graph: dict[str, Any],
    workloads: dict[str, Any],
    inventory: dict[str, Any],
    source_pin: dict[str, Any],
) -> list[str]:
    errors = validate_fragment_binding(fragment, base_graph)
    expected = build_cloudbank_reference_fragment(
        base_graph, workloads, inventory, source_pin
    )
    if fragment != expected:
        errors.append("CloudBank reference fragment is not the deterministic projection of its inputs")
    if fragment.get("source", {}).get("operator_estate_name") != OPERATOR_ESTATE_NAME:
        errors.append("CloudBank operator-facing estate name is invalid")
    for node in fragment.get("nodes", []):
        properties = node.get("properties", {})
        for key in (
            "migration_complete",
            "postgresql_mapping_complete",
            "production_ready",
            "runtime_observed",
            "target_equivalent",
        ):
            if properties.get(key) is not False:
                errors.append(f"node overstates {key}: {node.get('id')}")
        if properties.get("operator_platform") != "Oracle":
            errors.append(f"node omits the Oracle operator platform: {node.get('id')}")
    return sorted(set(errors))


def write_cloudbank_reference_fragment(payload: dict[str, Any], path: Path) -> None:
    write_json(path, payload)


def write_cloudbank_reference_receipt(payload: dict[str, Any], path: Path) -> None:
    write_json(
        path,
        {
            "receipt_type": "lightyear-cloudbank-reference-projection-build",
            "schema_version": "1.0",
            "fragment_id": payload["fragment_id"],
            "content_sha256": payload["content_sha256"],
            "base_graph": payload["base_graph"],
            "operator_estate": {
                "id": payload["source"]["operator_estate_id"],
                "name": payload["source"]["operator_estate_name"],
            },
            "upstream": {
                "product": payload["source"]["upstream_product"],
                "repository": payload["source"]["upstream_repository"],
                "commit": payload["source"]["upstream_commit"],
                "root_tree": payload["source"]["upstream_root_tree"],
                "subtree": payload["source"]["subtree"],
                "subtree_tree": payload["source"]["upstream_subtree_tree"],
            },
            "statistics": payload["statistics"],
            "runtime_observed": False,
            "postgresql_mapping_complete": False,
            "target_equivalent": False,
            "migration_complete": False,
            "production_ready": False,
        },
    )


def _evidence(line: int, method: str) -> dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "path": SOURCE_PATH,
        "line_start": line,
        "line_end": line,
        "method": method,
        "confidence": "asserted",
    }


def _source_line(needle: str) -> int:
    path = Path(__file__).resolve().parents[2] / SOURCE_PATH
    matches = [
        number
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if needle in line
    ]
    if len(matches) != 1:
        raise ValueError(f"CloudBank workload source token is not unique: {needle}")
    return matches[0]


def _statistics(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "external_reference_count": 0,
        "nodes_by_kind": dict(sorted(Counter(node["kind"] for node in nodes).items())),
        "edges_by_relation": dict(
            sorted(Counter(edge["relation"] for edge in edges).items())
        ),
    }
