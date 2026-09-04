from __future__ import annotations

import json
import hashlib
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
INVENTORY_PATH = "reference-estates/cloudbank/inventory.json"
STRUCTURAL_INVENTORY_PATH = "work/reference-estates/cloudbank/inventory.json"
_INVENTORY_LINE_CACHE: tuple[dict[str, Any], dict[str, int]] | None = None


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
    structural = inventory.get("structural_graph") or {}
    structural_enabled = bool(structural.get("source_files"))
    license_metadata = deepcopy(source_pin["license"])
    if structural_enabled:
        license_metadata["bundled_license_file"] = "LICENSES/UPL-1.0.txt"
        license_metadata["copyright"] = (
            "Copyright (c) 2021, 2023 Oracle and/or its affiliates."
        )
    database_objects_by_path: dict[str, list[dict[str, str]]] = {}
    for declaration in inventory["database_surface"].get("ddl_declarations", []):
        database_objects_by_path.setdefault(declaration["path"], []).append(
            {"kind": declaration["kind"], "name": declaration["name"]}
        )

    common_static = {
        "customer_id": OPERATOR_ESTATE_ID,
        "evidence_class": inventory["claim_class"],
        "runtime_observed": False,
        "source_commit": pin["commit"],
        "source_product": "CloudBank v5",
        "source_repository": pin["repository"],
    }
    file_ids: dict[str, str] = {}
    for record in structural.get("source_files", []):
        path = record["path"]
        node_id = f"cloudbank-reference:source-file:{path}"
        file_ids[path] = node_id
        platform = (
            "Java" if record["category"] == "java"
            else "Oracle" if record["category"] == "sql"
            else "CloudBank"
        )
        nodes.append(
            {
                "id": node_id,
                "kind": "source_file",
                "name": path,
                "properties": {
                    **common_static,
                    "category": record["category"],
                    "declared_database_objects": database_objects_by_path.get(path, []),
                    "extension": record["extension"],
                    "module": record["module"],
                    "operator_platform": platform,
                    "path": f"cloudbank-v5/{path}",
                    "statement": "Pinned CloudBank source artifact recorded by static inventory.",
                },
                "evidence": [
                    _inventory_evidence(
                        _inventory_line(inventory, f'"path": "{path}"')
                    )
                ],
            }
        )

    type_ids: dict[str, str] = {}
    for record in structural.get("java_types", []):
        fqcn = record["node"]
        node_id = f"cloudbank-reference:java-type:{fqcn}"
        type_ids[fqcn] = node_id
        evidence = _inventory_evidence(
            _inventory_line(inventory, f'"node": "{fqcn}"')
        )
        nodes.append(
            {
                "id": node_id,
                "kind": "java_type",
                "name": fqcn,
                "properties": {
                    **common_static,
                    "coupling_categories": deepcopy(record["coupling_categories"]),
                    "endpoint_annotations": deepcopy(record["endpoint_annotations"]),
                    "module": record["module"],
                    "operator_platform": "Java",
                    "package": record["package"],
                    "source_path": f"cloudbank-v5/{record['path']}",
                    "source_set": record["source_set"],
                    "statement": "Package-qualified Java type derived from the pinned CloudBank source.",
                },
                "evidence": [evidence],
            }
        )
        edges.append(
            _structural_edge(
                file_ids[record["path"]], "DECLARES", node_id, evidence,
                {"extraction": "package-declaration"},
            )
        )

    for record in structural.get("dependency_edges", []):
        source = type_ids[record["source"]]
        target = type_ids[record["target"]]
        evidence = _inventory_evidence(
            _inventory_line(inventory, f'"node": "{record["source"]}"')
        )
        edges.append(
            _structural_edge(
                source, "DEPENDS_ON", target, evidence,
                {"extraction": "internal-java-source-reference"},
            )
        )

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
        if structural_enabled:
            for source_path in workload["source_paths"]:
                relative_path = source_path.removeprefix("cloudbank-v5/")
                target_id = file_ids.get(relative_path)
                if target_id is None:
                    raise ValueError(
                        "CloudBank workload source path is absent from inventory: "
                        f"{source_path}"
                    )
                edges.append(
                    _structural_edge(
                        workload_id,
                        "MODERN_ENTRYPOINT",
                        target_id,
                        _evidence(workload_line, "curated-cloudbank-workload-v1"),
                        {"scope": "curated-workload-source"},
                    )
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
            "license": license_metadata,
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
            *(
                [
                    "Java dependency edges are static import and source-reference evidence; they do not prove runtime calls.",
                    "The complete structural projection is generated into ignored work output and is not distributed in this repository.",
                ]
                if structural_enabled else []
            ),
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
        if properties.get("customer_id") != OPERATOR_ESTATE_ID:
            errors.append(f"node omits the CloudBank estate identity: {node.get('id')}")
        for key in (
            "migration_complete",
            "postgresql_mapping_complete",
            "production_ready",
            "runtime_observed",
            "target_equivalent",
        ):
            if node.get("kind") in {"modernization_workload", "verification_scenario"} and properties.get(key) is not False:
                errors.append(f"node overstates {key}: {node.get('id')}")
        if (
            node.get("kind") in {"modernization_workload", "verification_scenario"}
            and properties.get("operator_platform") != "Oracle"
        ):
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


def _inventory_evidence(line: int) -> dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "path": STRUCTURAL_INVENTORY_PATH,
        "line_start": line,
        "line_end": line,
        "method": "pinned-static-inventory-v2",
        "confidence": "asserted",
    }


def _inventory_line(inventory: dict[str, Any], needle: str) -> int:
    global _INVENTORY_LINE_CACHE
    if _INVENTORY_LINE_CACHE is None or _INVENTORY_LINE_CACHE[0] is not inventory:
        lines = {
            line.strip().rstrip(","): number
            for number, line in enumerate(
                json.dumps(inventory, indent=2, sort_keys=True).splitlines(), start=1
            )
            if '"node": ' in line or '"path": ' in line
        }
        _INVENTORY_LINE_CACHE = (inventory, lines)
    token = needle.strip().rstrip(",")
    if token in _INVENTORY_LINE_CACHE[1]:
        return _INVENTORY_LINE_CACHE[1][token]
    raise ValueError(f"CloudBank inventory token is missing: {needle}")


def _structural_edge(
    source: str,
    relation: str,
    target: str,
    evidence: dict[str, Any],
    properties: dict[str, Any],
) -> dict[str, Any]:
    identity = json.dumps([source, relation, target, properties], sort_keys=True)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return {
        "id": f"cloudbank-reference:edge:structural:{digest}",
        "source": source,
        "target": target,
        "relation": relation,
        "properties": properties,
        "evidence": [evidence],
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
