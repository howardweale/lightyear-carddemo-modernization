from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import write_json
from lightyear_data.contracts import content_hash, seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES


SCHEMA_VERSION = "1.0"
QUALIFICATION_TYPE = "lightyear-cobol-qualification"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def build_cobol_ledger(graph_receipt: Mapping[str, Any]) -> dict[str, Any]:
    specs = (
        ("source-format", "normalized-equivalent", "governed-normalization", ["fixed-and-free-source-fixtures"]),
        ("copybook-resolution", "policy-decision-required", "unresolved", ["compiler-search-order", "complete-copybook-closure"]),
        ("pic-elementary-layout", "normalized-equivalent", "governed-normalization", ["offset-length-sign-and-scale-tests"]),
        ("redefines-occurs-depending-on", "policy-decision-required", "unresolved", ["layout-variants", "runtime-boundary-tests"]),
        ("packed-and-zoned-decimal", "normalized-equivalent", "governed-normalization", ["positive-negative-zero-and-boundary-vectors"]),
        ("arithmetic-rounding-truncation", "policy-decision-required", "unresolved", ["compiler-options", "native-arithmetic-baseline"]),
        ("paragraph-control-flow", "normalized-equivalent", "governed-normalization", ["perform-range-and-fallthrough-tests"]),
        ("static-call-linkage", "normalized-equivalent", "governed-normalization", ["linkage-section-and-parameter-layout"]),
        ("dynamic-call-linkage", "policy-decision-required", "unresolved", ["runtime-target-inventory", "load-resolution-policy"]),
        ("file-organization-and-status", "policy-decision-required", "unresolved", ["organization-access-mode-status-and-rdw-tests"]),
        ("embedded-db2-sql", "unsupported", "excluded-from-claim-scope", ["DB2-precompile-package-and-runtime-qualification"]),
        ("exec-cics", "unsupported", "excluded-from-claim-scope", ["MS-39-CICS-qualification"]),
        ("ims-dli", "unsupported", "excluded-from-claim-scope", ["MS-40-IMS-qualification"]),
        ("compiler-directives-and-options", "policy-decision-required", "unresolved", ["IBM-Enterprise-COBOL-listing-and-options"]),
        ("language-environment-runtime", "policy-decision-required", "unresolved", ["LE-options-abend-and-condition-capture"]),
    )
    entries = [
        {
            "item_id": f"cobol:{scope}",
            "scope": scope,
            "source_semantics": {"language": "IBM Enterprise COBOL", "claim": "bounded-static-inventory"},
            "target_semantics": {"contract": "lightyear-cobol-qualification"},
            "classification": classification,
            "rationale": "COBOL behavior is classified independently; static extraction cannot promote native runtime equivalence.",
            "evidence_required": evidence,
            "decision": decision,
        }
        for scope, classification, decision, evidence in specs
    ]
    statistics = dict(Counter(item["classification"] for item in entries))
    for name in COMPATIBILITY_CLASSES:
        statistics.setdefault(name, 0)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "ledger_type": "lightyear-cobol-compatibility-ledger",
        "graph_content_sha256": graph_receipt["content_sha256"],
        "classifications": list(COMPATIBILITY_CLASSES),
        "entries": entries,
        "statistics": statistics,
        "qualification_blocked": any(item["classification"] in {"policy-decision-required", "lossy", "unsupported"} for item in entries),
        "mainframe_equivalent": False,
        "production_ready": False,
    })


def validate_cobol_ledger(ledger: Mapping[str, Any]) -> list[str]:
    ledger = dict(ledger)
    errors: list[str] = []
    if ledger.get("ledger_type") != "lightyear-cobol-compatibility-ledger":
        errors.append("cobol-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("cobol-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("cobol-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    if len({item.get("item_id") for item in entries}) != len(entries):
        errors.append("cobol-ledger-duplicate-item")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("cobol-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("cobol-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("cobol-ledger-unsupported-not-excluded")
    expected = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != expected.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("cobol-ledger-statistics-invalid")
    if ledger.get("qualification_blocked") is not True:
        errors.append("cobol-ledger-qualification-gate-invalid")
    if ledger.get("mainframe_equivalent") is not False or ledger.get("production_ready") is not False:
        errors.append("cobol-ledger-overclaims-readiness")
    return sorted(set(errors))


def build_cobol_qualification(project_root: Path) -> dict[str, Any]:
    receipt = _load(project_root / "knowledge/graph.receipt.json")
    ledger = build_cobol_ledger(receipt)
    nodes = receipt["statistics"]["nodes_by_kind"]
    edges = receipt["statistics"]["edges_by_relation"]
    inventory = {
        "programs": nodes.get("cobol_program", 0),
        "paragraphs": nodes.get("cobol_paragraph", 0),
        "copybooks": nodes.get("copybook", 0),
        "fields": nodes.get("cobol_field", 0),
        "file_handles": nodes.get("cobol_file_handle", 0),
        "copybook_edges": edges.get("USES_COPYBOOK", 0),
        "call_edges": edges.get("CALLS", 0),
        "file_read_edges": edges.get("READS", 0),
        "file_write_edges": edges.get("WRITES", 0),
        "embedded_sql_edges": edges.get("ISSUES_SQL", 0),
    }
    gates = [
        {"gate": "estate-inventory", "status": "passed-static", "evidence": {"graph_sha256": receipt["content_sha256"], **inventory}},
        {"gate": "syntax-and-source-format", "status": "passed-bounded-static", "evidence": {"source_formats": ["fixed"], "native_parser": False}},
        {"gate": "copybook-closure", "status": "policy-decision-required", "evidence": {"references": inventory["copybook_edges"], "compiler_search_order_observed": False}},
        {"gate": "data-layout-and-numeric-semantics", "status": "passed-bounded-development", "evidence": {"fields": inventory["fields"], "signed_zoned_decimal_proof": True, "complete_pic_coverage": False}},
        {"gate": "control-flow-and-call-linkage", "status": "passed-static", "evidence": {"paragraphs": inventory["paragraphs"], "call_edges": inventory["call_edges"], "dynamic_call_resolution_observed": False}},
        {"gate": "file-and-external-resource-behavior", "status": "policy-decision-required", "evidence": {"file_handles": inventory["file_handles"], "native_file_status_observed": False}},
        {"gate": "db2-cics-ims-boundaries", "status": "excluded-separate-qualification", "evidence": {"embedded_sql_edges": inventory["embedded_sql_edges"], "db2_milestone": "MS-35.1", "cics_milestone": "MS-39", "ims_milestone": "MS-40"}},
        {"gate": "runtime-differential", "status": "passed-local-development", "evidence": {"workload": "INTCALC", "candidate": "carddemo_oracle", "zos_baseline_observed": False}},
        {"gate": "native-compile-link-execute", "status": "blocked-no-authorized-zos-evidence", "evidence": {"compiler_listing": False, "binder_map": False, "load_module": False, "execution_capture": False}},
    ]
    return seal({
        "schema_version": SCHEMA_VERSION,
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": "carddemo-cobol-v0.36",
        "bindings": {"graph_content_sha256": receipt["content_sha256"], "compatibility_ledger_sha256": ledger["content_sha256"]},
        "inventory": inventory,
        "qualification_gates": gates,
        "required_native_evidence": [
            "IBM Enterprise COBOL compiler listing and exact options",
            "copybook resolution listing and preprocessor outputs",
            "binder map and load-module identity",
            "LE runtime options and condition/abend behavior",
            "authorized z/OS inputs, outputs, file statuses, SQL/CICS/IMS effects, and trace",
        ],
        "qualification_mechanism_ready": True,
        "development_ready": True,
        "native_compiler_qualified": False,
        "runtime_equivalent": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can inventory and independently gate bounded COBOL semantics without treating static planning cells as production qualification.",
    })


def validate_cobol_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_cobol_qualification(project_root)
    payload = dict(payload or _load(project_root / "readiness/cobol/qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("cobol-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("cobol-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("cobol-qualification-drift")
    gates = [item.get("gate") for item in payload.get("qualification_gates", []) if isinstance(item, dict)]
    if len(gates) != 9 or len(set(gates)) != 9:
        errors.append("cobol-qualification-gates-incomplete")
    if any(payload.get(name) is not False for name in ("native_compiler_qualified", "runtime_equivalent", "mainframe_equivalent", "production_ready")):
        errors.append("cobol-qualification-overclaims-readiness")
    return sorted(set(errors))


def build_artifacts(project_root: Path, output_root: Path) -> dict[str, Any]:
    receipt = _load(project_root / "knowledge/graph.receipt.json")
    ledger = build_cobol_ledger(receipt)
    qualification = build_cobol_qualification(project_root)
    write_json(output_root / "compatibility-ledger.json", ledger)
    write_json(output_root / "qualification.json", qualification)
    return {"status": "passed", "ledger_sha256": ledger["content_sha256"], "qualification_sha256": qualification["content_sha256"], "mainframe_equivalent": False, "production_ready": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LIGHTYEAR COBOL qualification hardening")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    output = (args.output_root or root / "readiness/cobol").resolve()
    if args.command == "build":
        result = build_artifacts(root, output)
    else:
        expected_ledger = build_cobol_ledger(_load(root / "knowledge/graph.receipt.json"))
        ledger_path = root / "readiness/cobol/compatibility-ledger.json"
        ledger = _load(ledger_path) if ledger_path.is_file() else {}
        errors = validate_cobol_ledger(ledger) + validate_cobol_qualification(root)
        if ledger != expected_ledger:
            errors.append("cobol-ledger-drift")
        result = {"status": "passed" if not errors else "failed", "errors": sorted(set(errors)), "mainframe_equivalent": False, "production_ready": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
