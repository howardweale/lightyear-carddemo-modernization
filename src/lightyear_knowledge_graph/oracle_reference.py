from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .composite import validate_fragment_binding
from .inputs import canonical_hash


OPERATOR_ESTATE_ID = "oracle-customer-large"
OPERATOR_ESTATE_NAME = "Oracle Customer (Large)"
FRAGMENT_ID = "lightyear:oracle-customer-large-reference-v1"
SOURCE_ID = "source:lightyear-carddemo"
SOURCE_PATH = "reference-estates/idempiere/business-slices.json"

SLICE_NAMES = {
    "order-to-cash": "Order to cash",
    "procure-to-pay": "Procure to pay",
}


def build_oracle_reference_fragment(
    base_graph: dict[str, Any],
    slices: dict[str, Any],
    inventory: dict[str, Any],
    source_pin: dict[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    source_lines = len(
        (Path(__file__).resolve().parents[2] / SOURCE_PATH).read_text(encoding="utf-8").splitlines()
    )
    estate_counts = inventory["estate"]
    pin = source_pin["source"]

    sorted_slices = sorted(slices["slices"], key=lambda item: item["id"])
    for slice_occurrence, slice_item in enumerate(sorted_slices):
        slice_id = slice_item["id"]
        display_name = SLICE_NAMES[slice_id]
        workload_id = f"oracle-reference:workload:{slice_id}"
        common_properties = {
            "customer_id": OPERATOR_ESTATE_ID,
            "evidence_class": "upstream-static-reference",
            "operator_platform": "Oracle",
            "runtime_observed": False,
            "source_commit": pin["commit"],
            "source_product": "iDempiere",
            "source_repository": pin["repository"],
        }
        nodes.append(
            {
                "id": workload_id,
                "kind": "modernization_workload",
                "name": display_name,
                "properties": {
                    **common_properties,
                    "business_question": slice_item["business_question"],
                    "documented_flow_edge_count": slice_item["edge_count"],
                    "entry_processes": deepcopy(slice_item["entry_processes"]),
                    "estate_inventory": {
                        "internal_java_dependency_edges": estate_counts[
                            "internal_java_dependency_edges"
                        ],
                        "java_source_units": estate_counts["java_source_units"],
                        "oracle_sql_files": estate_counts["oracle_sql_files"],
                        "tracked_files": estate_counts["tracked_files"],
                    },
                    "selectors": deepcopy(slice_item["selectors"]),
                    "statement": (
                        f"Static {display_name.lower()} reference slice for "
                        f"{OPERATOR_ESTATE_NAME}; no customer system is attached."
                    ),
                    "status": "reference-projected",
                    "tables": deepcopy(slice_item["tables"]),
                },
                "evidence": [_evidence(1, source_lines, "curated-oracle-reference-slice-v1")],
            }
        )
        for sequence, (source, relation, target) in enumerate(slice_item["edges"], start=1):
            scenario_id = f"oracle-reference:scenario:{slice_id}:{sequence:02d}"
            edge_line = _source_line([source, relation, target], slice_occurrence)
            nodes.append(
                {
                    "id": scenario_id,
                    "kind": "verification_scenario",
                    "name": (
                        f"{display_name} static trace {sequence:02d}: "
                        f"{source} {relation.lower().replace('_', ' ')} {target}"
                    ),
                    "properties": {
                        **common_properties,
                        "expected_relation": relation,
                        "sequence": sequence,
                        "scenario_kind": "static-reference-trace",
                        "source_table": source,
                        "statement": (
                            f"The pinned reference slice documents {source} {relation} {target}; "
                            "this is static provenance, not an observed Oracle transaction."
                        ),
                        "target_table": target,
                        "workload_id": workload_id,
                    },
                    "evidence": [
                        _evidence(edge_line, edge_line, "curated-oracle-reference-slice-v1")
                    ],
                }
            )
            edges.append(
                {
                    "id": f"oracle-reference:edge:{slice_id}:{sequence:02d}",
                    "source": workload_id,
                    "target": scenario_id,
                    "relation": "HAS_SCENARIO",
                    "properties": {
                        "claim_boundary": "static-reference-trace",
                        "sequence": sequence,
                    },
                    "evidence": [
                        _evidence(edge_line, edge_line, "curated-oracle-reference-slice-v1")
                    ],
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
            "extensions": [".java", ".sql"],
            "id": "lightyear.oracle-reference",
            "language": "Oracle reference estate",
            "version": "1.0",
        },
        "source": {
            "acquisition_mode": source_pin["acquisition"]["mode"],
            "business_slices": SOURCE_PATH,
            "inventory": "reference-estates/idempiere/inventory.json",
            "license": deepcopy(source_pin["license"]),
            "operator_estate_id": OPERATOR_ESTATE_ID,
            "operator_estate_name": OPERATOR_ESTATE_NAME,
            "source_pin": "reference-estates/idempiere/source-pin.json",
            "upstream_product": "iDempiere",
            "upstream_repository": pin["repository"],
            "upstream_commit": pin["commit"],
            "upstream_tree": pin["tree"],
        },
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: item["id"]),
        "external_references": [],
        "statistics": _statistics(nodes, edges),
        "limitations": [
            "Oracle Customer (Large) is an operator-facing reference-estate label; no customer system is attached.",
            "The projection is derived from pinned iDempiere static inventory and curated slices, not native Oracle execution evidence.",
            "Static document-flow scenarios do not prove application equivalence, migration completion, production readiness, or runtime behavior.",
            "The fragment is bound to one exact canonical graph identity and fails closed after graph drift.",
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_oracle_reference_fragment(
    fragment: dict[str, Any],
    base_graph: dict[str, Any],
    slices: dict[str, Any],
    inventory: dict[str, Any],
    source_pin: dict[str, Any],
) -> list[str]:
    errors = validate_fragment_binding(fragment, base_graph)
    expected = build_oracle_reference_fragment(base_graph, slices, inventory, source_pin)
    if fragment != expected:
        errors.append("Oracle reference fragment is not the deterministic projection of its inputs")
    if fragment.get("source", {}).get("operator_estate_name") != OPERATOR_ESTATE_NAME:
        errors.append("operator-facing estate name is invalid")
    if any(
        "idempiere" in node.get("name", "").casefold()
        for node in fragment.get("nodes", [])
    ):
        errors.append("operator-facing node name exposes the upstream product name")
    for node in fragment.get("nodes", []):
        properties = node.get("properties", {})
        if properties.get("runtime_observed") is not False:
            errors.append(f"node overstates runtime observation: {node.get('id')}")
        if properties.get("operator_platform") != "Oracle":
            errors.append(f"node omits the Oracle operator platform: {node.get('id')}")
    return sorted(set(errors))


def write_oracle_reference_fragment(payload: dict[str, Any], path: Path) -> None:
    write_json(path, payload)


def write_oracle_reference_receipt(payload: dict[str, Any], path: Path) -> None:
    write_json(
        path,
        {
            "receipt_type": "lightyear-oracle-reference-projection-build",
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
                "tree": payload["source"]["upstream_tree"],
            },
            "statistics": payload["statistics"],
            "runtime_observed": False,
            "production_ready": False,
        },
    )


def _evidence(line_start: int, line_end: int, method: str) -> dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "path": SOURCE_PATH,
        "line_start": line_start,
        "line_end": line_end,
        "method": method,
        "confidence": "asserted",
    }


def _source_line(edge: list[str], occurrence: int) -> int:
    path = Path(__file__).resolve().parents[2] / SOURCE_PATH
    needle = json.dumps(edge)
    matches = [
        number
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if needle in line
    ]
    if occurrence >= len(matches):
        raise ValueError(f"business-slice edge is missing from source text: {edge}")
    return matches[occurrence]


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
