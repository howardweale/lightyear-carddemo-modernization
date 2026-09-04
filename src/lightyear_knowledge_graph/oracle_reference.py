from __future__ import annotations

import json
import hashlib
import gzip
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json

from .composite import validate_fragment_binding
from .inputs import canonical_hash


OPERATOR_ESTATE_ID = "oracle-customer-large"
OPERATOR_ESTATE_NAME = "iDempiere Reference Estate (Large)"
LEGACY_OPERATOR_ESTATE_NAME = "Oracle Customer (Large)"
FRAGMENT_ID = "lightyear:oracle-customer-large-reference-v1"
SOURCE_ID = "source:lightyear-carddemo"
SOURCE_PATH = "reference-estates/idempiere/business-slices.json"
INVENTORY_PATH = "reference-estates/idempiere/inventory.json"
STRUCTURAL_INVENTORY_PATH = "work/reference-estates/idempiere/inventory.json"
_INVENTORY_LINE_CACHE: tuple[dict[str, Any], dict[str, int]] | None = None

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
    common_static = {
        "customer_id": OPERATOR_ESTATE_ID,
        "evidence_class": "upstream-static-reference",
        "runtime_observed": False,
        "source_commit": pin["commit"],
        "source_product": "iDempiere",
        "source_repository": pin["repository"],
    }

    structural = inventory.get("structural_graph") or {}
    structural_enabled = bool(structural.get("source_units"))
    estate_name = (
        OPERATOR_ESTATE_NAME if structural_enabled else LEGACY_OPERATOR_ESTATE_NAME
    )
    license_metadata = deepcopy(source_pin["license"])
    if structural_enabled:
        license_metadata["bundled_license_file"] = "LICENSES/GPL-2.0-only.md"
        license_metadata["distribution_policy"] = (
            "Keep the source pin and GPL-2.0 license with any separately "
            "distributed complete structural projection."
        )
    type_ids: dict[str, str] = {}
    for record in structural.get("source_units", []):
        fqcn = record["node"]
        path = record["path"]
        type_id = f"oracle-reference:java-type:{fqcn}"
        type_ids[fqcn] = type_id
        evidence = _inventory_evidence(
            _inventory_line(inventory, f'"node": "{fqcn}"')
        )
        slice_roles = sorted(
            {
                f"{slice_id}:{item['role']}"
                for slice_id, value in inventory["slices"].items()
                for item in value.get("source_units", [])
                if item["node"] == fqcn
            }
        )
        nodes.append(
            {
                "id": type_id,
                "kind": "java_type",
                "name": _operator_type_name(fqcn),
                "properties": {
                    **common_static,
                    "operator_platform": "Java",
                    "package": record["package"],
                    "slice_roles": slice_roles,
                    "source_path": path,
                    "statement": "Package-qualified Java source unit derived from the pinned Oracle reference estate.",
                },
                "evidence": [evidence],
            }
        )

    slice_edges: dict[tuple[str, str], set[str]] = {}
    for slice_id, value in inventory["slices"].items():
        for record in value.get("dependency_edges", []):
            slice_edges.setdefault((record["source"], record["target"]), set()).add(
                slice_id
            )
    for record in structural.get("dependency_edges", []):
        source = record["source"]
        target = record["target"]
        evidence = _inventory_evidence(
            _inventory_line(inventory, f'"node": "{source}"')
        )
        slice_ids = sorted(slice_edges.get((source, target), set()))
        edges.append(
            _structural_edge(
                type_ids[source], "DEPENDS_ON", type_ids[target], evidence,
                {
                    "extraction": "internal-java-source-reference",
                    "curated_slices": slice_ids,
                },
            )
        )

    sorted_slices = sorted(slices["slices"], key=lambda item: item["id"])
    for slice_occurrence, slice_item in enumerate(sorted_slices):
        slice_id = slice_item["id"]
        display_name = SLICE_NAMES[slice_id]
        workload_id = f"oracle-reference:workload:{slice_id}"
        common_properties = {
            **common_static,
            "operator_platform": "Oracle",
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
                        f"{estate_name}; no customer system is attached."
                    ),
                    "status": "reference-projected",
                    "tables": deepcopy(slice_item["tables"]),
                },
                "evidence": [_evidence(1, source_lines, "curated-oracle-reference-slice-v1")],
            }
        )
        if structural_enabled:
            for seed in inventory["slices"][slice_id]["seeds"]:
                edges.append(
                    _structural_edge(
                        workload_id,
                        "MODERN_ENTRYPOINT",
                        type_ids[seed["node"]],
                        _inventory_evidence(
                            _inventory_line(
                                inventory, f'"node": "{seed["node"]}"'
                            )
                        ),
                        {"scope": "curated-slice-seed", "slice_id": slice_id},
                    )
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
            "license": license_metadata,
            "operator_estate_id": OPERATOR_ESTATE_ID,
            "operator_estate_name": estate_name,
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
        "limitations": _limitations(structural_enabled),
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
    if fragment.get("source", {}).get("operator_estate_name") != expected["source"]["operator_estate_name"]:
        errors.append("operator-facing estate name is invalid")
    if any(
        "idempiere" in node.get("name", "").casefold()
        for node in fragment.get("nodes", [])
    ):
        errors.append("operator-facing node name exposes the upstream product name")
    for node in fragment.get("nodes", []):
        properties = node.get("properties", {})
        if properties.get("customer_id") != OPERATOR_ESTATE_ID:
            errors.append(f"node omits the Oracle reference estate identity: {node.get('id')}")
        if properties.get("runtime_observed") is not False:
            errors.append(f"node overstates runtime observation: {node.get('id')}")
        if (
            node.get("kind") in {"modernization_workload", "verification_scenario"}
            and properties.get("operator_platform") != "Oracle"
        ):
            errors.append(f"node omits the Oracle operator platform: {node.get('id')}")
    return sorted(set(errors))


def write_oracle_reference_fragment(payload: dict[str, Any], path: Path) -> None:
    if path.suffix == ".gz":
        serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(serialized, compresslevel=9, mtime=0))
    else:
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


def _operator_type_name(fqcn: str) -> str:
    name = fqcn.rsplit(".", 1)[-1]
    if name.casefold().startswith("idempiere"):
        return name[len("Idempiere"):] or "ReferenceType"
    return name


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
            if '"node": ' in line
        }
        _INVENTORY_LINE_CACHE = (inventory, lines)
    token = needle.strip().rstrip(",")
    if token in _INVENTORY_LINE_CACHE[1]:
        return _INVENTORY_LINE_CACHE[1][token]
    raise ValueError(f"Oracle reference inventory token is missing: {needle}")


def _limitations(structural_enabled: bool) -> list[str]:
    if not structural_enabled:
        return [
            "Oracle Customer (Large) is an operator-facing reference-estate label; no customer system is attached.",
            "The projection is derived from pinned iDempiere static inventory and curated slices, not native Oracle execution evidence.",
            "Static document-flow scenarios do not prove application equivalence, migration completion, production readiness, or runtime behavior.",
            "The fragment is bound to one exact canonical graph identity and fails closed after graph drift.",
        ]
    return [
        "iDempiere Reference Estate (Large) is generated from public GPL-2.0 source; it is not a customer system.",
        "Oracle is used only to describe the compatibility analysis; Oracle Corporation does not sponsor or endorse this project.",
        "The projection is derived from pinned iDempiere static inventory and curated slices, not native Oracle execution evidence.",
        "Static document-flow scenarios do not prove application equivalence, migration completion, production readiness, or runtime behavior.",
        "Java dependency edges cover the complete measured static source graph and do not prove runtime calls.",
        "The fragment is generated into ignored work output and is not distributed in this repository.",
        "The fragment is bound to one exact canonical graph identity and fails closed after graph drift.",
    ]


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
        "id": f"oracle-reference:edge:structural:{digest}",
        "source": source,
        "target": target,
        "relation": relation,
        "properties": properties,
        "evidence": [evidence],
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
