from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import write_json
from lightyear_data.contracts import content_hash, seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES


SCHEMA_VERSION = "1.0"
CONFORMANCE_TYPE = "lightyear-cics-vsam-conformance-receipt"
LEDGER_TYPE = "lightyear-cics-vsam-compatibility-ledger"
QUALIFICATION_TYPE = "lightyear-cics-vsam-qualification"
CORPUS_ID = "lightyear-cics-vsam-synthetic-conformance-v1"

GRAPH_MINIMUMS = {
    "nodes": {
        "cics_command": 200,
        "cics_file_resource": 10,
        "cics_program_resource": 20,
        "cics_transaction": 20,
        "vsam_alternate_index": 3,
        "vsam_cluster": 10,
        "vsam_component": 20,
        "vsam_path": 3,
    },
    "edges": {
        "ACCESSES": 40,
        "BACKED_BY": 5,
        "HAS_COMPONENT": 20,
        "INDEXES": 3,
        "ISSUES": 200,
        "RESOLVES_TO": 20,
        "STARTS_PROGRAM": 20,
        "TARGETS": 5,
        "USES_MAP": 30,
        "USES_MAPSET": 30,
    },
}

RESPONSE_CODES = {
    "NORMAL": {"resp": 0, "resp2": 0, "file_status": "00"},
    "ENDFILE": {"resp": 20, "resp2": 0, "file_status": "10"},
    "DUPREC": {"resp": 15, "resp2": 0, "file_status": "22"},
    "NOTFND": {"resp": 13, "resp2": 0, "file_status": "23"},
    "INVREQ": {"resp": 16, "resp2": 0, "file_status": "92"},
    "LOCKED": {"resp": 100, "resp2": 0, "file_status": "92"},
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _result(
    response: str,
    *,
    result_count: int = 0,
    mutation_count: int = 0,
    trace: list[str] | None = None,
    diagnostics: list[str] | None = None,
    status: str = "passed",
    resp2: int | None = None,
) -> dict[str, Any]:
    codes = RESPONSE_CODES[response]
    return {
        "status": status,
        "response": response,
        "resp": codes["resp"],
        "resp2": codes["resp2"] if resp2 is None else resp2,
        "file_status": codes["file_status"],
        "result_count": result_count,
        "mutation_count": mutation_count,
        "trace": trace or [],
        "diagnostics": diagnostics or [],
    }


def execute_conformance_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one bounded semantic vector without pretending to emulate CICS or VSAM."""
    request = case.get("request", {})
    operation = str(request.get("operation", "")).upper()
    organization = str(request.get("organization", "")).upper()
    key = str(request.get("key", ""))
    records = {"A001": "OPEN", "A002": "HOLD", "A003": "OPEN"}
    esds = ["ENTRY-1", "ENTRY-2"]
    rrds = {1: "SLOT-1", 3: "SLOT-3"}
    aix = {"OPEN": ["A001", "A003"], "HOLD": ["A002"]}

    if operation == "READ":
        if organization == "KSDS":
            found = key in records
            return _result("NORMAL" if found else "NOTFND", result_count=int(found), trace=[f"READ KSDS {key}"])
        if organization == "ESDS":
            position = int(request.get("position", 0))
            found = 0 <= position < len(esds)
            return _result("NORMAL" if found else "ENDFILE", result_count=int(found), trace=[f"READ ESDS {position}"])
        if organization == "RRDS":
            rrn = int(request.get("rrn", 0))
            found = rrn in rrds
            return _result("NORMAL" if found else "NOTFND", result_count=int(found), trace=[f"READ RRDS {rrn}"])

    if operation == "WRITE":
        if organization == "KSDS":
            if key in records:
                return _result("DUPREC", trace=[f"WRITE KSDS {key}"])
            records[key] = str(request.get("value", "NEW"))
            return _result("NORMAL", result_count=1, mutation_count=1, trace=[f"WRITE KSDS {key}"])
        if organization == "ESDS":
            esds.append(str(request.get("value", "APPEND")))
            return _result("NORMAL", result_count=1, mutation_count=1, trace=["WRITE ESDS APPEND"])
        if organization == "RRDS":
            rrn = int(request.get("rrn", 0))
            if rrn in rrds:
                return _result("DUPREC", trace=[f"WRITE RRDS {rrn}"])
            rrds[rrn] = str(request.get("value", "NEW"))
            return _result("NORMAL", result_count=1, mutation_count=1, trace=[f"WRITE RRDS {rrn}"])

    if operation in {"REWRITE", "DELETE"}:
        if organization != "KSDS" or not request.get("update_token"):
            return _result("INVREQ", trace=[f"{operation} {organization or 'UNKNOWN'}"], diagnostics=["update-token-required"])
        if key not in records:
            return _result("NOTFND", trace=[f"{operation} KSDS {key}"])
        if operation == "REWRITE":
            records[key] = str(request.get("value", records[key]))
        else:
            del records[key]
        return _result("NORMAL", result_count=1, mutation_count=1, trace=[f"{operation} KSDS {key}"])

    if operation == "AIX_READ":
        alternate_key = str(request.get("alternate_key", ""))
        matches = aix.get(alternate_key, [])
        if request.get("unique") and len(matches) > 1:
            return _result("DUPREC", result_count=len(matches), trace=[f"AIX UNIQUE {alternate_key}"])
        return _result("NORMAL" if matches else "NOTFND", result_count=len(matches), trace=[f"AIX READ {alternate_key}"])

    if operation == "PATH_RESOLVE":
        path = str(request.get("path", ""))
        found = path == "CXACAIX.PATH"
        return _result("NORMAL" if found else "NOTFND", result_count=int(found), trace=[f"PATH {path}"])

    if operation == "BROWSE":
        direction = str(request.get("direction", "NEXT")).upper()
        start = str(request.get("start", "A001"))
        ordered = sorted(records)
        selected = [item for item in ordered if item >= start]
        if direction == "PREV":
            selected = list(reversed([item for item in ordered if item <= start]))
        limit = int(request.get("limit", 1))
        selected = selected[:limit]
        response = "NORMAL" if selected else "ENDFILE"
        return _result(response, result_count=len(selected), trace=["STARTBR", f"READ{direction}", "ENDBR"])

    if operation == "ENQ":
        owner = str(request.get("owner", "TASK1"))
        held_by = str(request.get("held_by", ""))
        if held_by and held_by != owner:
            return _result("LOCKED", trace=[f"ENQ {owner}"], diagnostics=["record-lock-contention"])
        return _result("NORMAL", result_count=1, trace=[f"ENQ {owner}"])
    if operation == "DEQ":
        return _result("NORMAL", result_count=1, trace=["DEQ"])

    if operation == "SYNCPOINT":
        action = str(request.get("action", "COMMIT")).upper()
        pending = int(request.get("pending_mutations", 1))
        if action == "COMMIT":
            return _result("NORMAL", result_count=pending, mutation_count=pending, trace=["SYNCPOINT COMMIT"])
        if action == "ROLLBACK":
            return _result("NORMAL", result_count=pending, mutation_count=0, trace=["SYNCPOINT ROLLBACK"])
        return _result("INVREQ", diagnostics=["invalid-syncpoint-action"])

    if operation == "HANDLE_CONDITION":
        condition = str(request.get("condition", "NOTFND")).upper()
        return _result(condition if condition in RESPONSE_CODES else "INVREQ", result_count=1, trace=[f"HANDLE CONDITION {condition}"])
    if operation == "RESP2":
        return _result("INVREQ", resp2=int(request.get("resp2", 42)), trace=["RESP RESP2"], diagnostics=["secondary-response-preserved"])
    if operation in {"SEND_MAP", "RECEIVE_MAP"}:
        valid = bool(request.get("map")) and bool(request.get("mapset"))
        return _result("NORMAL" if valid else "INVREQ", result_count=int(valid), trace=[operation.replace("_", " ")])
    if operation in {"LINK", "XCTL", "RETURN"}:
        valid = operation == "RETURN" or bool(request.get("program"))
        return _result("NORMAL" if valid else "INVREQ", result_count=int(valid), trace=[operation])

    unsupported = {
        "LDS_ACCESS": "lds-record-access-unsupported",
        "RLS_ACCESS": "rls-semantics-unsupported",
        "TSQ_ACCESS": "temporary-storage-queue-unsupported",
        "TDQ_ACCESS": "transient-data-queue-unsupported",
    }
    if operation in unsupported:
        return _result("INVREQ", status="blocked", diagnostics=[unsupported[operation]], trace=[operation])
    return _result("INVREQ", status="blocked", diagnostics=["unsupported-operation"], trace=[operation or "MISSING"])


def validate_cics_vsam_graph(graph_receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    statistics = graph_receipt.get("statistics", {})
    for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
        observed = statistics.get(field, {})
        for name, minimum in GRAPH_MINIMUMS[group].items():
            if not isinstance(observed.get(name), int) or observed.get(name, 0) < minimum:
                errors.append(f"cics-vsam-graph-{group}-{name}-below-minimum")
    if not isinstance(graph_receipt.get("content_sha256"), str):
        errors.append("cics-vsam-graph-content-hash-missing")
    return sorted(errors)


def _corpus(project_root: Path) -> tuple[Path, dict[str, Any]]:
    path = project_root / "readiness/cics-vsam/conformance/cases.json"
    manifest = _load(path)
    if manifest.get("content_sha256") != content_hash(manifest):
        raise ValueError("CICS/VSAM corpus manifest content_sha256 is invalid")
    if manifest.get("corpus_id") != CORPUS_ID:
        raise ValueError("CICS/VSAM corpus identity is invalid")
    return path, manifest


def build_cics_vsam_conformance(project_root: Path) -> dict[str, Any]:
    _, manifest = _corpus(project_root)
    graph = _load(project_root / "knowledge/graph.receipt.json")
    graph_errors = validate_cics_vsam_graph(graph)
    if graph_errors:
        raise ValueError("CICS/VSAM graph coverage failed: " + ", ".join(graph_errors))
    cases = manifest.get("cases", [])
    ids = [item.get("id") for item in cases if isinstance(item, dict)]
    if len(cases) != 38 or len(set(ids)) != 38 or any(not item for item in ids):
        raise ValueError("CICS/VSAM corpus must bind the exact 38-case set")

    results: list[dict[str, Any]] = []
    features: Counter[str] = Counter()
    for case in cases:
        observed = execute_conformance_case(case)
        if (
            observed["status"] != case.get("expected_status")
            or observed["response"] != case.get("expected_response")
            or observed["file_status"] != case.get("expected_file_status")
            or observed["mutation_count"] != case.get("expected_mutation_count")
        ):
            raise ValueError(f"CICS/VSAM conformance expectation failed: {case['id']}")
        features.update(case.get("features", []))
        results.append({
            "id": case["id"],
            "classification": case["classification"],
            "features": sorted(case.get("features", [])),
            "request_sha256": content_hash({"request": case["request"]}),
            "observed": observed,
            "passed": True,
        })
    classifications = Counter(item["classification"] for item in cases)
    blocked = sum(item["observed"]["status"] == "blocked" for item in results)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "receipt_type": CONFORMANCE_TYPE,
        "corpus_id": CORPUS_ID,
        "graph_content_sha256": graph["content_sha256"],
        "manifest_sha256": manifest["content_sha256"],
        "corpus": {
            "case_count": len(cases),
            "positive_case_count": classifications["positive"],
            "targeted_boundary_case_count": classifications["boundary"],
            "mutation_case_count": classifications["mutation"],
            "passed_case_count": len(cases) - blocked,
            "blocked_case_count": blocked,
            "customer_source": False,
        },
        "coverage": {
            "observed_features": sorted(features),
            "observed_feature_count": len(features),
            "responses": sorted({item["observed"]["response"] for item in results}),
            "organizations": ["KSDS", "ESDS", "RRDS"],
            "explicit_native_gaps": [
                "authorized CICS region execution and task identity",
                "native VSAM catalog, CI/CA split, buffering, and EBCDIC collation",
                "RLS, coupling-facility locking, journals, exits, and recovery",
                "3270 terminal byte-stream and BMS runtime behavior",
                "TSQ, TDQ, security, routing, and installation policy",
            ],
        },
        "results": results,
        "status": "passed",
        "claim_boundary": {
            "native_vsam_qualified": False,
            "native_cics_qualified": False,
            "rls_qualified": False,
            "recovery_equivalent": False,
            "cics_runtime_equivalent": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        },
    })


def validate_cics_vsam_conformance(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_cics_vsam_conformance(project_root)
    payload = dict(payload or _load(project_root / "readiness/cics-vsam/conformance.receipt.json"))
    errors: list[str] = []
    if payload.get("receipt_type") != CONFORMANCE_TYPE:
        errors.append("cics-vsam-conformance-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("cics-vsam-conformance-content-hash-invalid")
    if payload != expected:
        errors.append("cics-vsam-conformance-drift")
    claims = payload.get("claim_boundary", {})
    if any(claims.get(name) is not False for name in (
        "native_vsam_qualified", "native_cics_qualified", "rls_qualified",
        "recovery_equivalent", "cics_runtime_equivalent", "mainframe_equivalent", "production_ready",
    )):
        errors.append("cics-vsam-conformance-overclaims-readiness")
    return sorted(set(errors))


def build_cics_vsam_ledger(graph_receipt: Mapping[str, Any]) -> dict[str, Any]:
    specs = (
        ("vsam-cluster-identity", "exact", "bounded-contract", ["catalog-definition-and-dataset-identity"]),
        ("ksds-primary-key", "normalized-equivalent", "governed-normalization", ["key-length-offset-and-collation-vectors"]),
        ("esds-relative-byte-address", "lossy", "accepted-only-in-bounded-planning", ["native-RBA-lifecycle-baseline"]),
        ("rrds-relative-record-number", "normalized-equivalent", "governed-normalization", ["occupied-empty-and-reuse-vectors"]),
        ("lds-record-access", "unsupported", "excluded-from-claim-scope", ["LDS-specific-replacement-design"]),
        ("fixed-and-variable-record-layout", "policy-decision-required", "unresolved", ["RECSZ-CI-buffer-and-open-time-resolution"]),
        ("ebcdic-key-collation", "policy-decision-required", "unresolved", ["CCSID-and-native-key-order-baseline"]),
        ("alternate-index-unique", "normalized-equivalent", "governed-normalization", ["BUILD-index-and-duplicate-vectors"]),
        ("alternate-index-nonunique", "normalized-equivalent", "governed-normalization", ["ordered-duplicate-key-vectors"]),
        ("vsam-path-resolution", "exact", "bounded-contract", ["PATHENTRY-to-AIX-to-base-binding"]),
        ("control-interval-area-splits", "lossy", "accepted-only-in-bounded-planning", ["native-split-and-freespace-observation"]),
        ("cics-file-definition", "policy-decision-required", "unresolved", ["authorized-CSD-or-bundle-export"]),
        ("cics-read-and-generic-key", "normalized-equivalent", "governed-normalization", ["READ-key-length-generic-vectors"]),
        ("cics-write", "normalized-equivalent", "governed-normalization", ["WRITE-DUPREC-and-atomicity-vectors"]),
        ("cics-rewrite-update-token", "normalized-equivalent", "governed-normalization", ["READ-UPDATE-REWRITE-vectors"]),
        ("cics-delete", "normalized-equivalent", "governed-normalization", ["DELETE-key-and-token-vectors"]),
        ("cics-browse", "normalized-equivalent", "governed-normalization", ["STARTBR-READNEXT-READPREV-ENDBR-vectors"]),
        ("file-status-resp-resp2", "exact", "bounded-contract", ["status-crosswalk-and-secondary-response-vectors"]),
        ("enq-deq-locking", "policy-decision-required", "unresolved", ["region-lock-scope-timeout-and-deadlock-baseline"]),
        ("syncpoint-and-rollback", "policy-decision-required", "unresolved", ["journal-UOW-and-recovery-baseline"]),
        ("record-level-sharing", "unsupported", "excluded-from-claim-scope", ["RLS-and-coupling-facility-qualification"]),
        ("bms-map-3270-boundary", "lossy", "accepted-only-in-bounded-planning", ["terminal-byte-stream-attention-and-attribute-baseline"]),
        ("link-xctl-return", "normalized-equivalent", "governed-normalization", ["COMMAREA-channels-and-task-lifetime-vectors"]),
        ("temporary-storage-queues", "unsupported", "excluded-from-claim-scope", ["TSQ-recovery-and-auxiliary-storage-qualification"]),
        ("transient-data-queues", "unsupported", "excluded-from-claim-scope", ["TDQ-trigger-intra-extra-partition-qualification"]),
        ("journals-exits-and-recovery", "unsupported", "excluded-from-claim-scope", ["journal-model-global-user-exit-and-restart-evidence"]),
        ("security-routing-and-affinity", "policy-decision-required", "unresolved", ["RACF-region-routing-and-affinity-baseline"]),
    )
    entries = [{
        "item_id": f"cics-vsam:{scope}",
        "scope": scope,
        "source_semantics": {"platform": "IBM CICS TS and VSAM", "claim": "bounded-static-and-synthetic-evidence"},
        "target_semantics": {"contract": QUALIFICATION_TYPE},
        "classification": classification,
        "rationale": "Static inventory and deterministic semantic vectors are governed separately from native region, catalog, locking, journal, and recovery behavior.",
        "evidence_required": evidence,
        "decision": decision,
    } for scope, classification, decision, evidence in specs]
    statistics = dict(Counter(item["classification"] for item in entries))
    for name in COMPATIBILITY_CLASSES:
        statistics.setdefault(name, 0)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "ledger_type": LEDGER_TYPE,
        "graph_content_sha256": graph_receipt["content_sha256"],
        "classifications": list(COMPATIBILITY_CLASSES),
        "entries": entries,
        "statistics": statistics,
        "qualification_blocked": True,
        "mainframe_equivalent": False,
        "production_ready": False,
    })


def validate_cics_vsam_ledger(ledger: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != LEDGER_TYPE:
        errors.append("cics-vsam-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("cics-vsam-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("cics-vsam-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    if len(entries) != 27 or len({item.get("item_id") for item in entries}) != len(entries):
        errors.append("cics-vsam-ledger-entry-set-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("cics-vsam-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("cics-vsam-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("cics-vsam-ledger-unsupported-not-excluded")
    counts = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != counts.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("cics-vsam-ledger-statistics-invalid")
    if ledger.get("qualification_blocked") is not True:
        errors.append("cics-vsam-ledger-qualification-gate-invalid")
    if ledger.get("mainframe_equivalent") is not False or ledger.get("production_ready") is not False:
        errors.append("cics-vsam-ledger-overclaims-readiness")
    return sorted(set(errors))


def build_cics_vsam_qualification(project_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    _, manifest = _corpus(project_root)
    conformance = build_cics_vsam_conformance(project_root)
    ledger = build_cics_vsam_ledger(graph)
    comparison = _load(project_root / "readiness/cics-vsam/comparison.json")
    readiness = _load(project_root / "readiness/cics-vsam/readiness-receipt.json")
    nodes = graph["statistics"]["nodes_by_kind"]
    edges = graph["statistics"]["edges_by_relation"]
    corpus = conformance["corpus"]
    inventory = {
        "cics_commands": nodes.get("cics_command", 0),
        "cics_file_resources": nodes.get("cics_file_resource", 0),
        "cics_program_resources": nodes.get("cics_program_resource", 0),
        "cics_transactions": nodes.get("cics_transaction", 0),
        "vsam_clusters": nodes.get("vsam_cluster", 0),
        "vsam_components": nodes.get("vsam_component", 0),
        "vsam_alternate_indexes": nodes.get("vsam_alternate_index", 0),
        "vsam_paths": nodes.get("vsam_path", 0),
        "cics_access_edges": edges.get("ACCESSES", 0),
        "cics_issue_edges": edges.get("ISSUES", 0),
        "corpus_cases": corpus["case_count"],
        "targeted_boundary_cases": corpus["targeted_boundary_case_count"],
        "mutation_cases": corpus["mutation_case_count"],
        "blocked_cases": corpus["blocked_case_count"],
        "observed_feature_categories": conformance["coverage"]["observed_feature_count"],
        "customer_source": False,
    }
    gates = [
        {"gate": "estate-graph-inventory", "status": "passed-static", "evidence": {"graph_sha256": graph["content_sha256"], **{key: inventory[key] for key in ("cics_commands", "cics_file_resources", "cics_transactions", "vsam_clusters", "vsam_alternate_indexes", "vsam_paths")}}},
        {"gate": "corpus-and-provenance", "status": "passed-bounded-synthetic", "evidence": {"conformance_sha256": conformance["content_sha256"], **corpus}},
        {"gate": "vsam-organizations-keys-and-records", "status": "passed-supported-subset", "evidence": {"organizations": ["KSDS", "ESDS", "RRDS"], "lds_supported": False}},
        {"gate": "alternate-index-and-path", "status": "passed-bounded-semantic", "evidence": {"alternate_indexes": inventory["vsam_alternate_indexes"], "paths": inventory["vsam_paths"], "native_build_index_observed": False}},
        {"gate": "file-access-status-and-browse", "status": "passed-bounded-semantic", "evidence": {"responses": conformance["coverage"]["responses"], "native_file_control_observed": False}},
        {"gate": "write-rewrite-delete-and-update-token", "status": "passed-bounded-semantic", "evidence": {"mutation_vectors": 7, "native_atomicity_observed": False}},
        {"gate": "enq-deq-syncpoint-and-recovery", "status": "policy-decision-required", "evidence": {"synthetic_lock_vectors": True, "native_journal_or_UOW_observed": False}},
        {"gate": "cics-response-map-and-program-control", "status": "passed-bounded-semantic", "evidence": {"resp_resp2_vectors": True, "bms_boundary_vectors": True, "link_xctl_return_vectors": True}},
        {"gate": "rls-queues-security-and-routing", "status": "excluded-unqualified", "evidence": {"rls": False, "tsq": False, "tdq": False, "security_and_routing": False}},
        {"gate": "account-view-private-differential-proof", "status": "passed-local-development", "evidence": {"comparison_sha256": comparison["content_sha256"], "readiness_sha256": readiness["content_sha256"], "behavior_match": comparison.get("behavior_match") is True}},
        {"gate": "authorized-native-cics-vsam-execution", "status": "blocked-no-authorized-zos-evidence", "evidence": {"zos_observed_baseline": readiness.get("checks", {}).get("zos_observed_baseline") is True, "native_catalog_before_after": False, "region_trace": False, "signed_equivalence": False}},
    ]
    return seal({
        "schema_version": SCHEMA_VERSION,
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": "carddemo-cics-vsam-v0.39",
        "bindings": {
            "graph_content_sha256": graph["content_sha256"],
            "manifest_sha256": manifest["content_sha256"],
            "conformance_sha256": conformance["content_sha256"],
            "compatibility_ledger_sha256": ledger["content_sha256"],
            "account_view_comparison_sha256": comparison["content_sha256"],
            "account_view_readiness_sha256": readiness["content_sha256"],
        },
        "inventory": inventory,
        "qualification_gates": gates,
        "required_native_evidence": [
            "authorized CICS region, transaction, program, task, operator, and security identities",
            "CSD or bundle file definitions and VSAM catalog LISTCAT before and after state",
            "native KSDS, ESDS, RRDS, alternate-index, PATH, browse, update, and delete vectors",
            "RESP, RESP2, file status, BMS terminal, COMMAREA, channel, and program-control traces",
            "concurrent ENQ, record-lock, deadlock, timeout, RLS, and coupling-facility evidence",
            "journal, unit-of-work, syncpoint, rollback, abend, restart, and data recovery evidence",
            "TSQ, TDQ, exits, routing, affinity, and installation-policy decisions",
            "independently signed differential equivalence receipt",
        ],
        "qualification_mechanism_ready": True,
        "development_ready": True,
        "native_vsam_qualified": False,
        "native_cics_qualified": False,
        "rls_qualified": False,
        "recovery_equivalent": False,
        "cics_runtime_equivalent": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can inventory and fail-closed qualify a bounded synthetic CICS/VSAM semantic subset without claiming native region, VSAM, RLS, recovery, or production equivalence.",
    })


def validate_cics_vsam_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_cics_vsam_qualification(project_root)
    payload = dict(payload or _load(project_root / "readiness/cics-vsam/qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("cics-vsam-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("cics-vsam-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("cics-vsam-qualification-drift")
    gates = [item.get("gate") for item in payload.get("qualification_gates", []) if isinstance(item, dict)]
    if len(gates) != 11 or len(set(gates)) != 11:
        errors.append("cics-vsam-qualification-gates-incomplete")
    if any(payload.get(name) is not False for name in (
        "native_vsam_qualified", "native_cics_qualified", "rls_qualified", "recovery_equivalent",
        "cics_runtime_equivalent", "mainframe_equivalent", "production_ready",
    )):
        errors.append("cics-vsam-qualification-overclaims-readiness")
    return sorted(set(errors))


def build_artifacts(project_root: Path, output_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    conformance = build_cics_vsam_conformance(project_root)
    ledger = build_cics_vsam_ledger(graph)
    qualification = build_cics_vsam_qualification(project_root)
    write_json(output_root / "conformance.receipt.json", conformance)
    write_json(output_root / "compatibility-ledger.json", ledger)
    write_json(output_root / "qualification.json", qualification)
    return {
        "status": "passed",
        "conformance_sha256": conformance["content_sha256"],
        "ledger_sha256": ledger["content_sha256"],
        "qualification_sha256": qualification["content_sha256"],
        "mainframe_equivalent": False,
        "production_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LIGHTYEAR CICS/VSAM qualification hardening")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    output = (args.output_root or root / "readiness/cics-vsam").resolve()
    if args.command == "build":
        result = build_artifacts(root, output)
    else:
        expected_conformance = build_cics_vsam_conformance(root)
        expected_ledger = build_cics_vsam_ledger(_load(root / "knowledge/graph.receipt.json"))
        conformance = _load(root / "readiness/cics-vsam/conformance.receipt.json")
        ledger = _load(root / "readiness/cics-vsam/compatibility-ledger.json")
        errors = (
            validate_cics_vsam_conformance(root, conformance)
            + validate_cics_vsam_ledger(ledger)
            + validate_cics_vsam_qualification(root)
        )
        if conformance != expected_conformance:
            errors.append("cics-vsam-conformance-drift")
        if ledger != expected_ledger:
            errors.append("cics-vsam-ledger-drift")
        result = {
            "status": "passed" if not errors else "failed",
            "errors": sorted(set(errors)),
            "mainframe_equivalent": False,
            "production_ready": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
