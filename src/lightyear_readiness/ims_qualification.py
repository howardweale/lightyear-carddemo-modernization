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
CONFORMANCE_TYPE = "lightyear-ims-conformance-receipt"
LEDGER_TYPE = "lightyear-ims-compatibility-ledger"
QUALIFICATION_TYPE = "lightyear-ims-qualification"
CORPUS_ID = "lightyear-ims-synthetic-conformance-v1"

GRAPH_MINIMUMS = {
    "nodes": {
        "ims_database": 4,
        "ims_dataset_group": 4,
        "ims_field": 3,
        "ims_pcb": 6,
        "ims_psb": 4,
        "ims_segment": 3,
    },
    "edges": {
        "HAS_DATASET_GROUP": 4,
        "HAS_FIELD": 3,
        "PARENT_OF": 1,
        "USES_DBD": 6,
        "USES_PSB": 4,
    },
}

IMS_STATUS = {
    "SUCCESS": "  ",
    "SEGMENT_NOT_FOUND": "GE",
    "END_DATABASE": "GB",
    "DUPLICATE_SEGMENT": "II",
    "INVALID_SSA": "AJ",
    "SEQUENCE_ERROR": "DJ",
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
    held: bool = False,
    trace: list[str] | None = None,
    diagnostics: list[str] | None = None,
    status: str = "passed",
) -> dict[str, Any]:
    return {
        "status": status,
        "response": response,
        "ims_status": IMS_STATUS[response],
        "result_count": result_count,
        "mutation_count": mutation_count,
        "held": held,
        "trace": trace or [],
        "diagnostics": diagnostics or [],
    }


def execute_conformance_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Execute a bounded hierarchical vector without emulating an IMS subsystem."""
    request = case.get("request", {})
    operation = str(request.get("operation", "")).upper()
    root = str(request.get("root", "R001"))
    child = str(request.get("child", "D001"))
    roots = {"R001": ["D001", "D002"], "R002": ["D003"]}
    index = {"000001": "R001", "000002": "R002"}

    if operation in {"GU", "GHU"}:
        found = root in roots
        return _result(
            "SUCCESS" if found else "SEGMENT_NOT_FOUND",
            result_count=int(found), held=found and operation == "GHU", trace=[f"{operation} PAUTSUM0 {root}"],
        )
    if operation in {"GN", "GHN"}:
        position = int(request.get("position", 0))
        found = 0 <= position < len(roots)
        return _result(
            "SUCCESS" if found else "END_DATABASE",
            result_count=int(found), held=found and operation == "GHN", trace=[f"{operation} PAUTSUM0 {position}"],
        )
    if operation in {"GNP", "GHNP"}:
        if not request.get("parent_established", True):
            return _result("SEQUENCE_ERROR", trace=[f"{operation} PAUTDTL1"], diagnostics=["parent-position-required"])
        found = root in roots and child in roots[root]
        return _result(
            "SUCCESS" if found else "SEGMENT_NOT_FOUND",
            result_count=int(found), held=found and operation == "GHNP", trace=[f"{operation} PAUTDTL1 {child}"],
        )
    if operation == "SSA":
        syntax = str(request.get("syntax", "QUALIFIED")).upper()
        if syntax == "INVALID":
            return _result("INVALID_SSA", trace=["SSA PARSE"], diagnostics=["invalid-ssa-syntax"])
        found = root in roots and (not request.get("child") or child in roots[root])
        qualifier = "UNQUALIFIED" if syntax == "UNQUALIFIED" else "QUALIFIED"
        return _result(
            "SUCCESS" if found else "SEGMENT_NOT_FOUND", result_count=int(found),
            trace=[f"SSA {qualifier} PAUTSUM0", *(["SSA QUALIFIED PAUTDTL1"] if request.get("child") else [])],
        )
    if operation == "INDEX_LOOKUP":
        key = str(request.get("key", ""))
        found = key in index
        return _result("SUCCESS" if found else "SEGMENT_NOT_FOUND", result_count=int(found), trace=[f"GU PAUTINDX {key}"])
    if operation == "GSAM_READ":
        position = int(request.get("position", 0))
        found = position in (0, 1)
        return _result("SUCCESS" if found else "END_DATABASE", result_count=int(found), trace=[f"GN GSAM {position}"])

    if operation in {"ISRT_ROOT", "ISRT_CHILD"}:
        if str(request.get("procopt", "AP")).upper() not in {"A", "AP"}:
            return _result("SEQUENCE_ERROR", trace=[operation], diagnostics=["procopt-denies-update"])
        if operation == "ISRT_ROOT":
            if root in roots:
                return _result("DUPLICATE_SEGMENT", trace=[f"ISRT PAUTSUM0 {root}"])
            return _result("SUCCESS", result_count=1, mutation_count=1, trace=[f"ISRT PAUTSUM0 {root}"])
        if root not in roots:
            return _result("SEGMENT_NOT_FOUND", trace=[f"ISRT PAUTDTL1 {child}"], diagnostics=["parent-not-found"])
        return _result("SUCCESS", result_count=1, mutation_count=1, trace=[f"ISRT PAUTDTL1 {child}"])

    if operation in {"REPL", "DLET"}:
        if not request.get("hold"):
            return _result("SEQUENCE_ERROR", trace=[operation], diagnostics=["successful-get-hold-required"])
        target = str(request.get("target", "ROOT")).upper()
        found = root in roots and (target == "ROOT" or child in roots[root])
        return _result(
            "SUCCESS" if found else "SEGMENT_NOT_FOUND",
            result_count=int(found), mutation_count=int(found), held=found, trace=[f"GH{'U' if target == 'ROOT' else 'NP'} {target}", operation],
        )

    if operation == "PROCOPT":
        option = str(request.get("procopt", "")).upper()
        allowed = option in {"A", "AP"}
        return _result(
            "SUCCESS" if allowed else "SEQUENCE_ERROR", result_count=int(allowed), trace=[f"PROCOPT {option}"],
            diagnostics=[] if allowed else ["procopt-denies-update"],
        )
    if operation == "SENSEG":
        segment = str(request.get("segment", ""))
        found = segment in {"PAUTSUM0", "PAUTDTL1"}
        return _result("SUCCESS" if found else "SEGMENT_NOT_FOUND", result_count=int(found), trace=[f"SENSEG {segment}"])
    if operation == "PCB_ACCESS":
        valid = request.get("pcb") == "PAUTBPCB" and int(request.get("pcb_number", 0)) == 2
        return _result(
            "SUCCESS" if valid else "INVALID_SSA", result_count=int(valid), trace=["PCB SELECT"],
            diagnostics=[] if valid else ["pcb-binding-mismatch"],
        )
    if operation == "CHKP":
        checkpoint = str(request.get("checkpoint", ""))
        valid = bool(checkpoint) and len(checkpoint) <= 8
        return _result(
            "SUCCESS" if valid else "SEQUENCE_ERROR", result_count=int(valid),
            mutation_count=int(request.get("pending_mutations", 0)) if valid else 0, trace=[f"CHKP {checkpoint}"],
        )
    if operation == "XRST":
        checkpoint = str(request.get("checkpoint", ""))
        found = checkpoint == "CP000001"
        return _result("SUCCESS" if found else "SEGMENT_NOT_FOUND", result_count=int(found), trace=[f"XRST {checkpoint}"])
    if operation == "ROLB":
        pending = int(request.get("pending_mutations", 0))
        return _result("SUCCESS", result_count=pending, mutation_count=0, trace=["ROLB"], diagnostics=["pending-mutations-discarded"])
    if operation == "ROUTE":
        mode = str(request.get("mode", "")).upper()
        valid = mode in {"BMP", "DLI_BATCH"}
        return _result("SUCCESS" if valid else "SEQUENCE_ERROR", result_count=int(valid), trace=[f"ROUTE {mode}"])

    unsupported = {
        "DEDB_ACCESS": "fast-path-dedb-unsupported",
        "MSDB_ACCESS": "msdb-unsupported",
        "SHARED_QUEUES_ACCESS": "ims-tm-shared-queues-unsupported",
        "DBRC_RECOVERY": "dbrc-log-and-recovery-unsupported",
    }
    if operation in unsupported:
        return _result("SEQUENCE_ERROR", status="blocked", diagnostics=[unsupported[operation]], trace=[operation])
    return _result("SEQUENCE_ERROR", status="blocked", diagnostics=["unsupported-operation"], trace=[operation or "MISSING"])


def validate_ims_graph(graph_receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    statistics = graph_receipt.get("statistics", {})
    for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
        observed = statistics.get(field, {})
        for name, minimum in GRAPH_MINIMUMS[group].items():
            if not isinstance(observed.get(name), int) or observed.get(name, 0) < minimum:
                errors.append(f"ims-graph-{group}-{name}-below-minimum")
    if not isinstance(graph_receipt.get("content_sha256"), str):
        errors.append("ims-graph-content-hash-missing")
    return sorted(errors)


def _corpus(project_root: Path) -> tuple[Path, dict[str, Any]]:
    path = project_root / "readiness/ims-expiry/conformance/cases.json"
    manifest = _load(path)
    if manifest.get("content_sha256") != content_hash(manifest):
        raise ValueError("IMS corpus manifest content_sha256 is invalid")
    if manifest.get("corpus_id") != CORPUS_ID:
        raise ValueError("IMS corpus identity is invalid")
    return path, manifest


def build_ims_conformance(project_root: Path) -> dict[str, Any]:
    _, manifest = _corpus(project_root)
    graph = _load(project_root / "knowledge/graph.receipt.json")
    graph_errors = validate_ims_graph(graph)
    if graph_errors:
        raise ValueError("IMS graph coverage failed: " + ", ".join(graph_errors))
    cases = manifest.get("cases", [])
    ids = [item.get("id") for item in cases if isinstance(item, dict)]
    if len(cases) != 40 or len(set(ids)) != 40 or any(not item for item in ids):
        raise ValueError("IMS corpus must bind the exact 40-case set")
    results: list[dict[str, Any]] = []
    features: Counter[str] = Counter()
    for case in cases:
        observed = execute_conformance_case(case)
        if (
            observed["status"] != case.get("expected_status")
            or observed["response"] != case.get("expected_response")
            or observed["ims_status"] != case.get("expected_ims_status")
            or observed["mutation_count"] != case.get("expected_mutation_count")
        ):
            raise ValueError(f"IMS conformance expectation failed: {case['id']}")
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
            "access_methods": ["GSAM", "HIDAM", "INDEX"],
            "call_families": ["GU", "GN", "GNP", "GHU", "GHN", "GHNP", "ISRT", "REPL", "DLET", "CHKP", "XRST", "ROLB"],
            "explicit_native_gaps": [
                "authorized IMS region, PSB scheduling, and native database execution",
                "Fast Path DEDB and MSDB behavior",
                "IMS TM message queues, shared queues, routing, and security",
                "DBRC, logging, image copy, recovery, locking, and data sharing",
                "native GSAM positioning, restart, and external dataset behavior",
            ],
        },
        "results": results,
        "status": "passed",
        "claim_boundary": {
            "native_ims_qualified": False,
            "ims_tm_qualified": False,
            "fast_path_qualified": False,
            "dbrc_recovery_equivalent": False,
            "restart_equivalent": False,
            "ims_runtime_equivalent": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        },
    })


def validate_ims_conformance(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_ims_conformance(project_root)
    payload = dict(payload or _load(project_root / "readiness/ims-expiry/conformance.receipt.json"))
    errors: list[str] = []
    if payload.get("receipt_type") != CONFORMANCE_TYPE:
        errors.append("ims-conformance-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("ims-conformance-content-hash-invalid")
    if payload != expected:
        errors.append("ims-conformance-drift")
    if any(payload.get("claim_boundary", {}).get(name) is not False for name in (
        "native_ims_qualified", "ims_tm_qualified", "fast_path_qualified", "dbrc_recovery_equivalent",
        "restart_equivalent", "ims_runtime_equivalent", "mainframe_equivalent", "production_ready",
    )):
        errors.append("ims-conformance-overclaims-readiness")
    return sorted(set(errors))


def build_ims_ledger(graph_receipt: Mapping[str, Any]) -> dict[str, Any]:
    specs = (
        ("dbd-database-identity", "exact", "bounded-contract", ["native-DBD-digest"]),
        ("hidam-root-and-hierarchy", "normalized-equivalent", "governed-normalization", ["root-addressing-and-sequence-vectors"]),
        ("secondary-index-read", "normalized-equivalent", "governed-normalization", ["index-to-target-vectors"]),
        ("secondary-index-maintenance", "policy-decision-required", "unresolved", ["native-index-update-and-rebuild-baseline"]),
        ("gsam-sequential-access", "lossy", "accepted-only-in-bounded-planning", ["native-GSAM-position-and-dataset-baseline"]),
        ("dataset-group-storage", "policy-decision-required", "unresolved", ["OSAM-VSAM-blocking-buffering-and-placement"]),
        ("segment-parentage", "exact", "bounded-contract", ["DBD-parent-child-binding"]),
        ("segment-field-layout", "exact", "bounded-contract", ["offset-length-type-and-key-binding"]),
        ("packed-decimal-key-collation", "policy-decision-required", "unresolved", ["native-key-order-and-invalid-data-vectors"]),
        ("psb-identity", "exact", "bounded-contract", ["native-PSB-digest"]),
        ("pcb-selection", "exact", "bounded-contract", ["PCB-name-number-and-DBD-binding"]),
        ("procopt-authorization", "policy-decision-required", "unresolved", ["site-PROCOPT-and-update-policy"]),
        ("sensitive-segment-view", "normalized-equivalent", "governed-normalization", ["SENSEG-visibility-vectors"]),
        ("gu-gn-gnp-navigation", "normalized-equivalent", "governed-normalization", ["hierarchical-position-and-end-vectors"]),
        ("ghu-ghn-ghnp-hold", "normalized-equivalent", "governed-normalization", ["native-lock-scope-and-hold-lifetime"]),
        ("ssa-qualification", "normalized-equivalent", "governed-normalization", ["qualified-unqualified-and-path-vectors"]),
        ("dli-status-codes", "exact", "bounded-contract", ["blank-GE-GB-II-AJ-DJ-crosswalk"]),
        ("segment-insert", "normalized-equivalent", "governed-normalization", ["ISRT-parent-sequence-and-duplicate-vectors"]),
        ("segment-replace", "normalized-equivalent", "governed-normalization", ["GET-HOLD-REPL-vectors"]),
        ("segment-delete", "normalized-equivalent", "governed-normalization", ["GET-HOLD-DLET-and-cascade-policy"]),
        ("checkpoint-and-restart", "policy-decision-required", "unresolved", ["native-CHKP-XRST-area-and-frequency-baseline"]),
        ("rollback-and-recovery", "unsupported", "excluded-from-claim-scope", ["IMS-log-DBRC-ROLB-and-recovery-qualification"]),
        ("bmp-scheduling", "normalized-equivalent", "governed-normalization", ["authorized-BMP-JCL-region-and-PSB-observation"]),
        ("dli-batch-scheduling", "lossy", "accepted-only-in-bounded-planning", ["native-DLI-region-and-dataset-allocation"]),
        ("ims-tm-message-processing", "unsupported", "excluded-from-claim-scope", ["MPP-transaction-queue-routing-and-security-qualification"]),
        ("fast-path-dedb", "unsupported", "excluded-from-claim-scope", ["DEDB-area-and-dependent-region-qualification"]),
        ("msdb", "unsupported", "excluded-from-claim-scope", ["MSDB-runtime-qualification"]),
        ("locking-data-sharing-and-irpm", "policy-decision-required", "unresolved", ["native-lock-contention-IRLM-and-data-sharing-baseline"]),
    )
    entries = [{
        "item_id": f"ims:{scope}",
        "scope": scope,
        "source_semantics": {"platform": "IBM IMS", "claim": "bounded-static-and-synthetic-evidence"},
        "target_semantics": {"contract": QUALIFICATION_TYPE},
        "classification": classification,
        "rationale": "Static inventory and deterministic hierarchical vectors are governed separately from native region, storage, locking, logging, restart, and recovery behavior.",
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


def validate_ims_ledger(ledger: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != LEDGER_TYPE:
        errors.append("ims-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("ims-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("ims-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    if len(entries) != 28 or len({item.get("item_id") for item in entries}) != len(entries):
        errors.append("ims-ledger-entry-set-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("ims-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("ims-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("ims-ledger-unsupported-not-excluded")
    counts = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != counts.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("ims-ledger-statistics-invalid")
    if ledger.get("qualification_blocked") is not True:
        errors.append("ims-ledger-qualification-gate-invalid")
    if ledger.get("mainframe_equivalent") is not False or ledger.get("production_ready") is not False:
        errors.append("ims-ledger-overclaims-readiness")
    return sorted(set(errors))


def build_ims_qualification(project_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    _, manifest = _corpus(project_root)
    conformance = build_ims_conformance(project_root)
    ledger = build_ims_ledger(graph)
    comparison = _load(project_root / "readiness/ims-expiry/comparison.json")
    readiness = _load(project_root / "readiness/ims-expiry/readiness-receipt.json")
    nodes = graph["statistics"]["nodes_by_kind"]
    edges = graph["statistics"]["edges_by_relation"]
    corpus = conformance["corpus"]
    inventory = {
        "ims_databases": nodes.get("ims_database", 0),
        "ims_dataset_groups": nodes.get("ims_dataset_group", 0),
        "ims_fields": nodes.get("ims_field", 0),
        "ims_pcbs": nodes.get("ims_pcb", 0),
        "ims_psbs": nodes.get("ims_psb", 0),
        "ims_segments": nodes.get("ims_segment", 0),
        "parent_edges": edges.get("PARENT_OF", 0),
        "uses_dbd_edges": edges.get("USES_DBD", 0),
        "uses_psb_edges": edges.get("USES_PSB", 0),
        "corpus_cases": corpus["case_count"],
        "targeted_boundary_cases": corpus["targeted_boundary_case_count"],
        "mutation_cases": corpus["mutation_case_count"],
        "blocked_cases": corpus["blocked_case_count"],
        "observed_feature_categories": conformance["coverage"]["observed_feature_count"],
        "customer_source": False,
    }
    gates = [
        {"gate": "estate-graph-inventory", "status": "passed-static", "evidence": {"graph_sha256": graph["content_sha256"], **{key: inventory[key] for key in ("ims_databases", "ims_dataset_groups", "ims_pcbs", "ims_psbs", "ims_segments")}}},
        {"gate": "corpus-and-provenance", "status": "passed-bounded-synthetic", "evidence": {"conformance_sha256": conformance["content_sha256"], **corpus}},
        {"gate": "dbd-access-methods-and-storage", "status": "passed-supported-subset", "evidence": {"access_methods": ["GSAM", "HIDAM", "INDEX"], "native_storage_observed": False}},
        {"gate": "hierarchy-fields-keys-and-ssa", "status": "passed-bounded-semantic", "evidence": {"segments": inventory["ims_segments"], "fields": inventory["ims_fields"], "parent_edges": inventory["parent_edges"]}},
        {"gate": "psb-pcb-procopt-and-senseg", "status": "passed-bounded-semantic", "evidence": {"psbs": inventory["ims_psbs"], "pcbs": inventory["ims_pcbs"], "native_schedule_observed": False}},
        {"gate": "navigation-hold-and-status", "status": "passed-bounded-semantic", "evidence": {"call_families": conformance["coverage"]["call_families"], "responses": conformance["coverage"]["responses"]}},
        {"gate": "insert-replace-delete", "status": "passed-bounded-semantic", "evidence": {"mutation_vectors": 9, "native_atomicity_observed": False}},
        {"gate": "checkpoint-restart-rollback-and-recovery", "status": "policy-decision-required", "evidence": {"synthetic_checkpoint_vectors": True, "native_log_or_DBRC_observed": False}},
        {"gate": "scheduling-tm-fast-path-and-data-sharing", "status": "excluded-unqualified", "evidence": {"bmp_route_modeled": True, "ims_tm": False, "fast_path": False, "data_sharing": False}},
        {"gate": "cbpaup0c-private-differential-proof", "status": "passed-local-development", "evidence": {"comparison_sha256": comparison["content_sha256"], "readiness_sha256": readiness["content_sha256"], "behavior_match": comparison.get("behavior_match") is True}},
        {"gate": "authorized-native-ims-execution", "status": "blocked-no-authorized-zos-evidence", "evidence": {"zos_observed_baseline": readiness.get("checks", {}).get("zos_observed_baseline") is True, "native_database_before_after": False, "region_trace": False, "signed_equivalence": False}},
    ]
    return seal({
        "schema_version": SCHEMA_VERSION,
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": "carddemo-ims-v0.40",
        "bindings": {
            "graph_content_sha256": graph["content_sha256"],
            "manifest_sha256": manifest["content_sha256"],
            "conformance_sha256": conformance["content_sha256"],
            "compatibility_ledger_sha256": ledger["content_sha256"],
            "expiry_comparison_sha256": comparison["content_sha256"],
            "expiry_readiness_sha256": readiness["content_sha256"],
        },
        "inventory": inventory,
        "qualification_gates": gates,
        "required_native_evidence": [
            "authorized LPAR, IMS subsystem, region, program, PSB, PCB, DBD, operator, and security identities",
            "native DBD, PSB, ACB or catalog, load module, JCL, database dataset, and image-copy digests",
            "native HIDAM, secondary-index, GSAM, hierarchy, SSA, positioning, and status-code vectors",
            "native ISRT, REPL, DLET, GET HOLD, locking, contention, and data-sharing evidence",
            "CHKP, XRST, ROLB, abend, IMS log, DBRC, restart, and recovery evidence",
            "BMP, DLI batch, MPP, IMS TM, Fast Path, routing, queue, and security scope decisions",
            "database before and after images with restoration proof",
            "independently signed differential equivalence receipt",
        ],
        "qualification_mechanism_ready": True,
        "development_ready": True,
        "native_ims_qualified": False,
        "ims_tm_qualified": False,
        "fast_path_qualified": False,
        "dbrc_recovery_equivalent": False,
        "restart_equivalent": False,
        "ims_runtime_equivalent": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can inventory and fail-closed qualify a bounded synthetic IMS hierarchical semantic subset without claiming native region, scheduling, Fast Path, DBRC, restart, recovery, or production equivalence.",
    })


def validate_ims_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_ims_qualification(project_root)
    payload = dict(payload or _load(project_root / "readiness/ims-expiry/qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("ims-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("ims-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("ims-qualification-drift")
    gates = [item.get("gate") for item in payload.get("qualification_gates", []) if isinstance(item, dict)]
    if len(gates) != 11 or len(set(gates)) != 11:
        errors.append("ims-qualification-gates-incomplete")
    if any(payload.get(name) is not False for name in (
        "native_ims_qualified", "ims_tm_qualified", "fast_path_qualified", "dbrc_recovery_equivalent",
        "restart_equivalent", "ims_runtime_equivalent", "mainframe_equivalent", "production_ready",
    )):
        errors.append("ims-qualification-overclaims-readiness")
    return sorted(set(errors))


def build_artifacts(project_root: Path, output_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    conformance = build_ims_conformance(project_root)
    ledger = build_ims_ledger(graph)
    qualification = build_ims_qualification(project_root)
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
    parser = argparse.ArgumentParser(description="LIGHTYEAR IMS qualification hardening")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    output = (args.output_root or root / "readiness/ims-expiry").resolve()
    if args.command == "build":
        result = build_artifacts(root, output)
    else:
        expected_conformance = build_ims_conformance(root)
        expected_ledger = build_ims_ledger(_load(root / "knowledge/graph.receipt.json"))
        conformance = _load(root / "readiness/ims-expiry/conformance.receipt.json")
        ledger = _load(root / "readiness/ims-expiry/compatibility-ledger.json")
        errors = (
            validate_ims_conformance(root, conformance)
            + validate_ims_ledger(ledger)
            + validate_ims_qualification(root)
        )
        if conformance != expected_conformance:
            errors.append("ims-conformance-drift")
        if ledger != expected_ledger:
            errors.append("ims-ledger-drift")
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
