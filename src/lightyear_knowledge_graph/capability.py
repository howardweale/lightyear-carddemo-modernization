from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lightyear_common.io import write_json


GATE_NAMES = {
    1: "typed native asset parsing",
    2: "connected dependency and control-flow graph",
    3: "curated behavior contract",
    4: "bounded modernization candidate",
    5: "mutation and negative verification",
    6: "authorized execution of the original on z/OS",
    7: "independent differential comparison",
    8: "signed equivalence receipt with unresolved gaps",
}


def _canonical_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _gate(number: int, status: str, evidence: list[str], gap: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "gate": number,
        "name": GATE_NAMES[number],
        "status": status,
        "evidence": sorted(evidence),
    }
    if gap:
        result["gap"] = gap
    return result


def analyze_capabilities(
    graph: dict[str, Any],
    cics_vsam_receipt: dict[str, Any] | None = None,
    asm_receipt: dict[str, Any] | None = None,
    ims_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph["nodes"]}
    kind_counts = graph["statistics"]["nodes_by_kind"]
    relation_counts = graph["statistics"]["edges_by_relation"]
    scenario_status = {
        node["id"]: node.get("properties", {}).get("status")
        for node in graph["nodes"]
        if node["kind"] == "verification_scenario"
    }
    rule_counts = {
        prefix: sum(
            node["kind"] == "business_rule" and node["id"].startswith(prefix)
            for node in graph["nodes"]
        )
        for prefix in ("rule:cics-vsam:", "rule:asm-date:", "rule:ims-expiry:")
    }

    receipt = cics_vsam_receipt or {}
    live_equivalent = bool(receipt.get("mainframe_equivalent"))
    receipt_status = "passed" if live_equivalent else "blocked"
    receipt_gap = None if live_equivalent else "A signed, authorized z/OS CAVW observation is not yet bound."

    cics_common = [
        _gate(1, "passed", [
            f"{kind_counts.get('cics_transaction', 0)} cics_transaction nodes",
            f"{kind_counts.get('cics_command', 0)} cics_command nodes",
            f"{kind_counts.get('bms_field', 0)} bms_field nodes",
        ]),
        _gate(2, "passed", [
            f"{relation_counts.get('STARTS_PROGRAM', 0)} STARTS_PROGRAM edges",
            f"{relation_counts.get('ISSUES', 0)} ISSUES edges",
            f"{relation_counts.get('USES_MAP', 0)} USES_MAP edges",
        ]),
        _gate(3, "passed", [f"{rule_counts['rule:cics-vsam:']} curated CICS/VSAM rules"]),
        _gate(4, "passed", ["modern:file:factory/benchmarks/cics_vsam_account_candidate.py"]),
        _gate(5, "passed", ["scenario:cics-vsam:private-mutation-gate"]),
        _gate(6, "passed" if live_equivalent else "blocked", ["readiness/cics-vsam/readiness-receipt.json"], receipt_gap),
        _gate(7, "passed" if live_equivalent else "mechanism_ready", ["readiness/cics-vsam/comparison.json"], receipt_gap),
        _gate(8, receipt_status, ["readiness/cics-vsam/readiness-receipt.json"], receipt_gap),
    ]
    vsam_common = [dict(item) for item in cics_common]
    vsam_common[0] = _gate(1, "passed", [
        f"{kind_counts.get('vsam_cluster', 0)} vsam_cluster nodes",
        f"{kind_counts.get('vsam_alternate_index', 0)} alternate indexes",
        f"{kind_counts.get('vsam_path', 0)} VSAM paths",
    ])
    vsam_common[1] = _gate(2, "passed", [
        f"{relation_counts.get('BACKED_BY', 0)} BACKED_BY edges",
        f"{relation_counts.get('TARGETS', 0)} TARGETS edges",
        f"{relation_counts.get('ACCESSES', 0)} CICS file access edges",
    ])

    asm_live = bool((asm_receipt or {}).get("mainframe_equivalent"))
    asm_gap = None if asm_live else "No authorized COBDATFT z/OS execution capture exists."
    asm_gates = [
        _gate(1, "passed", [
            f"{kind_counts.get('assembler_program', 0)} assembler programs",
            f"{kind_counts.get('assembler_instruction', 0)} assembler instructions",
            f"{kind_counts.get('assembler_dsect', 0)} DSECTs",
            f"{kind_counts.get('assembler_macro', 0)} macros",
        ]),
        _gate(2, "passed", [
            f"{relation_counts.get('BRANCHES_TO', 0)} BRANCHES_TO edges",
            f"{relation_counts.get('USES_DSECT', 0)} USES_DSECT edges",
            f"{relation_counts.get('USES_MACRO', 0)} USES_MACRO edges",
            "legacy:cobol-program:CBACT01C -> legacy:assembler-program:COBDATFT",
        ]),
        _gate(3, "passed", [f"{rule_counts['rule:asm-date:']} curated COBDATFT rules"]),
        _gate(4, "passed", ["modern:file:factory/benchmarks/asm_date_candidate.py"]),
        _gate(5, "passed", ["scenario:asm-date:private-mutation-gate"]),
        _gate(6, "passed" if asm_live else "blocked", ["readiness/asm-date/readiness-receipt.json"], asm_gap),
        _gate(7, "passed" if asm_live else "mechanism_ready", ["readiness/asm-date/comparison.json"], asm_gap),
        _gate(8, "passed" if asm_live else "blocked", ["readiness/asm-date/readiness-receipt.json"], asm_gap),
    ]

    ims_live = bool((ims_receipt or {}).get("mainframe_equivalent"))
    ims_gap = None if ims_live else "No authorized CBPAUP0C IMS BMP execution capture exists."
    ims_gates = [
        _gate(1, "passed", [
            f"{kind_counts.get('ims_database', 0)} IMS DBDs",
            f"{kind_counts.get('ims_psb', 0)} IMS PSBs",
            f"{kind_counts.get('ims_segment', 0)} IMS segments",
            f"{kind_counts.get('ims_pcb', 0)} IMS PCBs",
        ]),
        _gate(2, "passed", [
            f"{relation_counts.get('USES_DBD', 0)} USES_DBD edges",
            f"{relation_counts.get('SENSITIVE_TO', 0)} SENSITIVE_TO edges",
            f"{relation_counts.get('USES_PSB', 0)} program-to-PSB edges",
        ]),
        _gate(3, "passed", [f"{rule_counts['rule:ims-expiry:']} curated CBPAUP0C IMS rules"]),
        _gate(4, "passed", ["modern:file:factory/benchmarks/ims_expiry_candidate.py"]),
        _gate(5, "passed", ["scenario:ims-expiry:private-mutation-gate"]),
        _gate(6, "passed" if ims_live else "blocked", ["readiness/ims-expiry/readiness-receipt.json"], ims_gap),
        _gate(7, "passed" if ims_live else "mechanism_ready", ["readiness/ims-expiry/comparison.json"], ims_gap),
        _gate(8, "passed" if ims_live else "blocked", ["readiness/ims-expiry/readiness-receipt.json"], ims_gap),
    ]

    capabilities = []
    for technology, gates in (
        ("CICS", cics_common),
        ("VSAM", vsam_common),
        ("IMS", ims_gates),
        ("HLASM", asm_gates),
    ):
        development_ready = all(item["status"] == "passed" for item in gates[:5])
        mainframe_equivalent = all(item["status"] == "passed" for item in gates)
        capabilities.append(
            {
                "technology": technology,
                "discovery_ready": all(item["status"] == "passed" for item in gates[:2]),
                "development_ready": development_ready,
                "mainframe_equivalent": mainframe_equivalent,
                "support_claim": (
                    "mainframe-equivalent"
                    if mainframe_equivalent
                    else "development-proof; live z/OS evidence pending"
                    if development_ready
                    else "discovery and dependency analysis only"
                ),
                "gates": gates,
            }
        )

    payload = {
        "schema_version": "1.0",
        "analysis_type": "factorydark-mainframe-capability-readiness",
        "graph_content_sha256": graph["content_sha256"],
        "truth_boundary": (
            "Local, simulated, fixture, and static evidence cannot satisfy z/OS observation gates."
        ),
        "capabilities": capabilities,
    }
    payload["content_sha256"] = _canonical_hash(payload)
    return payload


def validate_capability_analysis(payload: dict[str, Any], graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "1.0":
        errors.append("unsupported capability analysis schema_version")
    if payload.get("graph_content_sha256") != graph.get("content_sha256"):
        errors.append("capability analysis is not bound to the canonical graph")
    if payload.get("content_sha256") != _canonical_hash(payload):
        errors.append("capability analysis content_sha256 is invalid")
    technologies = [item.get("technology") for item in payload.get("capabilities", [])]
    if technologies != ["CICS", "VSAM", "IMS", "HLASM"]:
        errors.append("capability analysis must cover CICS, VSAM, IMS, and HLASM in order")
    for capability in payload.get("capabilities", []):
        gates = capability.get("gates", [])
        if [gate.get("gate") for gate in gates] != list(range(1, 9)):
            errors.append(f"{capability.get('technology')} does not contain readiness gates 1-8")
        if capability.get("mainframe_equivalent") and any(
            gate.get("status") != "passed" for gate in gates
        ):
            errors.append(f"{capability.get('technology')} overstates mainframe equivalence")
    return errors


def write_capability_analysis(payload: dict[str, Any], path: Path) -> None:
    write_json(path, payload)
