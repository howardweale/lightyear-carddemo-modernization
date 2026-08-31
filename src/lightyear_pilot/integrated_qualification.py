from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import write_json
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES
from lightyear_knowledge_graph.model import graph_hash

from .pilot import PilotError, canonical_hash, load_json


SCHEMA_VERSION = "1.0"
CORPUS_ID = "lightyear-integrated-pilot-synthetic-conformance-v1"
EXPECTED_CORPUS_SHA256 = "ab61a530f67e727f7f1996d88d988aeee29caba2b25e69889bf88ece5ed21011"
CONFORMANCE_TYPE = "lightyear-integrated-pilot-conformance-receipt"
MATRIX_TYPE = "lightyear-integrated-pilot-evidence-matrix"
LEDGER_TYPE = "lightyear-integrated-pilot-compatibility-ledger"
QUALIFICATION_TYPE = "lightyear-integrated-pilot-qualification"
QUALIFICATION_ID = "carddemo-account-mixed-language-pilot-v0.42"

REQUIRED_TECHNOLOGIES = ("COBOL", "Db2", "HLASM", "JCL", "PL/I")
REQUIRED_SOURCE_FILES = (
    "cobol/ACCOUNTV.cbl",
    "copybooks/ACCTREC.cpy",
    "db2/AUTHFRDS.ddl",
    "hlasm/DATEFMT.asm",
    "jcl/ACCTPIL.jcl",
    "pli/ACCTPL1.pli",
)
REQUIRED_DEPENDENCIES = {
    "COBOL": {"Db2", "PL/I"},
    "Db2": set(),
    "HLASM": set(),
    "JCL": {"HLASM", "PL/I"},
    "PL/I": {"Db2"},
}
GRAPH_MINIMUMS = {
    "nodes": {
        "assembler_program": 1,
        "cobol_program": 1,
        "copybook": 1,
        "db2_sql_statement": 2,
        "db2_table": 1,
        "jcl_job": 1,
        "jcl_step": 2,
        "pli_program": 1,
    },
    "edges": {
        "BRANCHES_TO": 2,
        "CALLS": 1,
        "EXECUTES": 2,
        "ISSUES_SQL": 2,
        "READS_TABLE": 2,
        "USES_COPYBOOK": 1,
    },
}
TECHNOLOGY_EVIDENCE = {
    "COBOL": ("readiness/cobol/qualification.json", "lightyear-cobol-qualification"),
    "Db2": (
        "data-modernization/db2-semantic-adapter/authfrds.conformance.receipt.json",
        "lightyear-db2-source-adapter-conformance",
    ),
    "HLASM": ("readiness/asm-date/qualification.json", "lightyear-hlasm-qualification"),
    "JCL": ("readiness/jcl/qualification.json", "lightyear-jcl-qualification"),
    "PL/I": ("readiness/pli/qualification.json", "lightyear-pli-qualification"),
}
FALSE_CLAIMS = (
    "factory_dispatch_allowed",
    "native_execution_observed",
    "native_runtime_qualified",
    "mainframe_equivalent",
    "production_release_allowed",
    "production_ready",
)


def _seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["content_sha256"] = canonical_hash(result, {"content_sha256"})
    return result


def _content_valid(payload: Mapping[str, Any]) -> bool:
    return payload.get("content_sha256") == canonical_hash(payload, {"content_sha256"})


def _load_graph(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise PilotError("integrated-pilot-graph-object-required")
    return payload


def validate_integrated_manifest(manifest: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not _content_valid(manifest):
        errors.append("integrated-pilot-corpus-content-hash-invalid")
    if manifest.get("corpus_id") != CORPUS_ID:
        errors.append("integrated-pilot-corpus-identity-invalid")
    if manifest.get("content_sha256") != EXPECTED_CORPUS_SHA256:
        errors.append("integrated-pilot-corpus-frozen-content-drift")
    cases = manifest.get("cases", [])
    ids = [item.get("id") for item in cases if isinstance(item, dict)] if isinstance(cases, list) else []
    if len(cases) != 40 or len(ids) != 40 or len(set(ids)) != 40 or any(not item for item in ids):
        errors.append("integrated-pilot-corpus-must-bind-exact-40-case-set")
    return sorted(errors)


def _result(
    response: str,
    *,
    status: str = "passed",
    result_count: int = 0,
    mutation_count: int = 0,
    selected_auth_id: int | None = None,
    external_call_count: int = 0,
    return_code: int | None = None,
    trace: list[str] | None = None,
    diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "response": response,
        "result_count": result_count,
        "mutation_count": mutation_count,
        "selected_auth_id": selected_auth_id,
        "external_call_count": external_call_count,
        "return_code": return_code,
        "trace": trace or [],
        "diagnostics": diagnostics or [],
    }


def _validate_rows(rows: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(rows, list):
        return [], ["authfrds-rows-must-be-a-list"]
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[int] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row-{index}-not-an-object")
            continue
        auth_id = row.get("auth_id")
        card_num = row.get("card_num")
        status = row.get("auth_status")
        if not isinstance(auth_id, int) or auth_id < 0 or auth_id > 99_999_999_999:
            errors.append(f"row-{index}-auth-id-outside-decimal-11")
        elif auth_id in seen:
            errors.append(f"row-{index}-duplicate-primary-key")
        else:
            seen.add(auth_id)
        if not isinstance(card_num, str) or len(card_num) != 16:
            errors.append(f"row-{index}-card-num-not-char-16")
        if not isinstance(status, str) or len(status) != 1:
            errors.append(f"row-{index}-auth-status-not-char-1")
        if not errors or all(not item.startswith(f"row-{index}-") for item in errors):
            normalized.append({"auth_id": auth_id, "card_num": card_num, "auth_status": status})
    return normalized, errors


def _single_row_select(rows: Any) -> tuple[str, int | None, list[str]]:
    normalized, errors = _validate_rows(rows)
    if errors:
        return "DATA_ERROR", None, errors
    if not normalized:
        return "SQL_NOT_FOUND", None, ["unqualified-select-returned-no-row"]
    if len(normalized) > 1:
        return "SQL_MULTIPLE_ROWS", None, ["unqualified-select-returned-more-than-one-row"]
    return "SUCCESS", int(normalized[0]["auth_id"]), []


def execute_integrated_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Execute only the bounded semantics visible in the six-file reference pilot."""
    request = case.get("request", {})
    operation = str(request.get("operation", "")).upper()

    if operation in {"BATCH_PIPELINE", "ONLINE_PIPELINE", "DB2_LOOKUP"}:
        response, selected, diagnostics = _single_row_select(request.get("rows", []))
        if response != "SUCCESS":
            return _result(response, diagnostics=diagnostics, trace=["SELECT AUTH_ID FROM CARDDEMO.AUTHFRDS"])
        if operation == "DB2_LOOKUP":
            return _result("SUCCESS", result_count=1, selected_auth_id=selected, trace=["UNQUALIFIED SELECT", "HOST VARIABLE ACCT_ID OVERWRITTEN"])
        if operation == "ONLINE_PIPELINE":
            return _result(
                "SUCCESS",
                result_count=1,
                selected_auth_id=selected,
                external_call_count=1,
                return_code=0,
                trace=[
                    "ACCOUNTV SELECT AUTH_ID",
                    "ACCOUNTV CALL ACCTPL1",
                    "ACCTPL1 SELECT AUTH_ID",
                    "ACCTPL1 CALL CBACT04C OPTIONS(COBOL)",
                ],
                diagnostics=["CBACT04C-external-behavior-not-modeled"],
            )
        pointer = int(request.get("date_pointer", 1))
        return_code = 8 if pointer == 0 else 0
        return _result(
            "SUCCESS",
            result_count=1,
            selected_auth_id=selected,
            external_call_count=1,
            return_code=return_code,
            trace=[
                "ACCTPIL RUN EXEC PGM=ACCTPL1",
                "ACCTPL1 SELECT AUTH_ID",
                "ACCTPL1 CALL CBACT04C OPTIONS(COBOL)",
                "ACCTPIL FORMAT EXEC PGM=DATEFMT",
                "DATEFMT BZ EMPTY" if pointer == 0 else "DATEFMT B RETURN",
            ],
            diagnostics=["CBACT04C-external-behavior-not-modeled"],
        )

    if operation == "AUTHFRDS_SCHEMA":
        rows, errors = _validate_rows(request.get("rows", []))
        return _result(
            "SUCCESS" if not errors else "DATA_ERROR",
            result_count=len(rows) if not errors else 0,
            diagnostics=errors,
            trace=["DECIMAL(11,0) NOT NULL", "CHAR(16) NOT NULL", "CHAR(1) NOT NULL", "PRIMARY KEY AUTH_ID"],
        )
    if operation == "COPYBOOK_LAYOUT":
        fields = request.get("fields", [{"name": "ACCT-ID", "length": 11}, {"name": "ACCT-STATUS", "length": 1}])
        expected = [("ACCT-ID", 11), ("ACCT-STATUS", 1)]
        actual = [(item.get("name"), item.get("length")) for item in fields if isinstance(item, dict)] if isinstance(fields, list) else []
        valid = actual == expected
        return _result("SUCCESS" if valid else "LAYOUT_MISMATCH", result_count=12 if valid else 0, trace=["01 ACCT-RECORD", "05 ACCT-ID PIC 9(11)", "05 ACCT-STATUS PIC X"])
    if operation == "INDEX_ORDER":
        columns = list(request.get("columns", []))
        unique = request.get("unique") is True
        valid = columns == ["CARD_NUM", "AUTH_ID"] and unique
        return _result("SUCCESS" if valid else "INDEX_MISMATCH", result_count=2 if valid else 0, trace=["AUTHFRDS_IX1 CARD_NUM,AUTH_ID"])
    if operation == "JCL_FLOW":
        steps = list(request.get("steps", []))
        valid = steps == ["RUN:ACCTPL1", "FORMAT:DATEFMT"]
        return _result("SUCCESS" if valid else "SEQUENCE_ERROR", result_count=2 if valid else 0, trace=steps, diagnostics=[] if valid else ["source-step-order-mismatch"])
    if operation == "DATASET_BINDING":
        name = str(request.get("name", ""))
        dsn = str(request.get("dsn", ""))
        disp = str(request.get("disp", ""))
        expected = {
            "STEPLIB": ("CARDDEMO.LOADLIB", "SHR"),
            "ACCTIN": ("CARDDEMO.PILOT.INPUT", "SHR"),
        }
        valid = expected.get(name) == (dsn, disp)
        return _result("SUCCESS" if valid else "ALLOCATION_MISMATCH", result_count=int(valid), trace=[f"DD {name} DSN={dsn} DISP={disp}"])
    if operation == "HLASM_DATEFMT":
        pointer = int(request.get("pointer", 0))
        return _result(
            "EMPTY_POINTER" if pointer == 0 else "SUCCESS",
            result_count=int(pointer != 0),
            return_code=8 if pointer == 0 else 0,
            trace=["L 2,0(1)", "LTR 2,2", "BZ EMPTY" if pointer == 0 else "LA 15,0", "BR 14"],
        )
    if operation == "COBOL_TO_PLI":
        program = str(request.get("program", ""))
        digits = int(request.get("parameter_digits", 0))
        valid = program == "ACCTPL1" and digits == 11
        return _result("SUCCESS" if valid else "CALL_CONTRACT_MISMATCH", result_count=int(valid), trace=[f"CALL {program} USING ACCT-ID"])
    if operation == "PLI_TO_COBOL":
        program = str(request.get("program", ""))
        convention = str(request.get("convention", ""))
        valid = program == "CBACT04C" and convention == "COBOL"
        return _result(
            "EXTERNAL_BOUNDARY_REACHED" if valid else "CALL_CONTRACT_MISMATCH",
            result_count=int(valid),
            external_call_count=int(valid),
            trace=[f"CALL {program} OPTIONS({convention})"],
            diagnostics=["external-program-outside-selected-source"] if valid else [],
        )
    if operation == "SOURCE_PATH":
        path = str(request.get("path", ""))
        valid = path in REQUIRED_SOURCE_FILES
        return _result("SUCCESS" if valid else "SOURCE_OUTSIDE_SELECTION", result_count=int(valid), trace=[path])
    if operation == "DEPENDENCY_EDGE":
        source = str(request.get("source", ""))
        target = str(request.get("target", ""))
        valid = target in REQUIRED_DEPENDENCIES.get(source, set())
        return _result("SUCCESS" if valid else "DEPENDENCY_MISMATCH", result_count=int(valid), trace=[f"{source}->{target}"])

    unsupported = {
        "CICS_TRANSACTION_RUNTIME": "CICS runtime is outside the selected five-cell proof",
        "NATIVE_DB2_PACKAGE": "native Db2 package and bind behavior were not observed",
        "NATIVE_JES_EXECUTION": "JES execution and dataset effects were not observed",
        "NATIVE_LE_LINKAGE": "native Language Environment linkage was not observed",
    }
    if operation in unsupported:
        return _result("UNSUPPORTED", status="blocked", diagnostics=[unsupported[operation]], trace=[operation])
    return _result("UNSUPPORTED", status="blocked", diagnostics=["operation-outside-integrated-pilot-contract"], trace=[operation or "MISSING"])


def validate_integrated_graph(graph: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    statistics = graph.get("statistics", {})
    for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
        observed = statistics.get(field, {})
        for name, minimum in GRAPH_MINIMUMS[group].items():
            if not isinstance(observed.get(name), int) or observed.get(name, 0) < minimum:
                errors.append(f"integrated-pilot-graph-{group}-{name}-below-minimum")
    if graph.get("content_sha256") != graph_hash(graph):
        errors.append("integrated-pilot-graph-content-hash-invalid")
    return sorted(errors)


def _inputs(project_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = project_root / "pilot/reference-output"
    selection = load_json(root / "pilot-selection.json")
    package = load_json(root / "pilot-work-package.json")
    graph = _load_graph(root / "source-estate.snapshot.json.gz")
    corpus = load_json(project_root / "pilot/integrated-qualification/conformance/cases.json")
    for label, payload in (("selection", selection), ("work-package", package)):
        if not _content_valid(payload):
            raise PilotError(f"integrated-pilot-{label}-content-hash-invalid")
    if graph.get("content_sha256") != graph_hash(graph):
        raise PilotError("integrated-pilot-graph-content-hash-invalid")
    manifest_errors = validate_integrated_manifest(corpus)
    if manifest_errors:
        raise PilotError(manifest_errors[0])
    return selection, package, graph, corpus


def validate_integrated_scope(
    selection: Mapping[str, Any], package: Mapping[str, Any], graph: Mapping[str, Any]
) -> list[str]:
    errors = validate_integrated_graph(graph)
    cluster = selection.get("selected_cluster", {})
    if selection.get("selection_ready") is not True:
        errors.append("integrated-pilot-selection-not-ready")
    if tuple(cluster.get("technologies", [])) != REQUIRED_TECHNOLOGIES:
        errors.append("integrated-pilot-technology-set-invalid")
    if tuple(cluster.get("source_files", [])) != REQUIRED_SOURCE_FILES:
        errors.append("integrated-pilot-source-set-invalid")
    if package.get("selection_sha256") != selection.get("content_sha256"):
        errors.append("integrated-pilot-work-package-selection-drift")
    if package.get("analysis_graph_sha256") != graph.get("content_sha256"):
        errors.append("integrated-pilot-work-package-graph-drift")
    cells = [item for item in package.get("cells", []) if isinstance(item, dict)]
    by_id = {item.get("cell_id"): item for item in cells}
    by_technology = {item.get("technology"): item for item in cells}
    if len(cells) != 5 or set(by_technology) != set(REQUIRED_TECHNOLOGIES) or len(by_id) != 5:
        errors.append("integrated-pilot-cell-set-invalid")
    else:
        for technology, expected_targets in REQUIRED_DEPENDENCIES.items():
            actual_ids = set(by_technology[technology].get("coordination_dependencies", []))
            actual_targets = {by_id.get(item, {}).get("technology") for item in actual_ids}
            if actual_targets != expected_targets:
                errors.append(f"integrated-pilot-{technology.lower().replace('/', 'i').replace(' ', '-')}-dependencies-invalid")
    if package.get("factory_dispatch_allowed") is not False or package.get("production_ready") is not False:
        errors.append("integrated-pilot-work-package-overclaim")
    return sorted(set(errors))


def build_integrated_conformance(project_root: Path) -> dict[str, Any]:
    selection, package, graph, manifest = _inputs(project_root)
    scope_errors = validate_integrated_scope(selection, package, graph)
    if scope_errors:
        raise PilotError(scope_errors[0])
    cases = manifest.get("cases", [])
    results: list[dict[str, Any]] = []
    features: Counter[str] = Counter()
    for case in cases:
        observed = execute_integrated_case(case)
        if (
            observed["status"] != case.get("expected_status")
            or observed["response"] != case.get("expected_response")
            or observed["mutation_count"] != case.get("expected_mutation_count")
        ):
            raise PilotError(f"integrated-pilot-case-expectation-failed:{case.get('id')}")
        features.update(case.get("features", []))
        results.append(
            {
                "id": case["id"],
                "classification": case["classification"],
                "features": sorted(case.get("features", [])),
                "request_sha256": canonical_hash({"request": case["request"]}),
                "observed": observed,
                "passed": True,
            }
        )
    classifications = Counter(item["classification"] for item in cases)
    blocked = sum(item["observed"]["status"] == "blocked" for item in results)
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "receipt_type": CONFORMANCE_TYPE,
            "corpus_id": CORPUS_ID,
            "bindings": {
                "selection_sha256": selection["content_sha256"],
                "work_package_sha256": package["content_sha256"],
                "source_graph_sha256": graph["content_sha256"],
                "manifest_sha256": manifest["content_sha256"],
            },
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
                "technologies": list(REQUIRED_TECHNOLOGIES),
                "source_files": list(REQUIRED_SOURCE_FILES),
                "observed_features": sorted(features),
                "observed_feature_count": len(features),
                "integrated_paths": [
                    "ACCTPIL.RUN -> ACCTPL1 -> AUTHFRDS -> CBACT04C external boundary",
                    "ACCTPIL.FORMAT -> DATEFMT",
                    "ACCOUNTV -> AUTHFRDS -> ACCTPL1 -> CBACT04C external boundary",
                ],
                "source_quirks": [
                    "both embedded SELECT statements have no predicate",
                    "ACCTPL1 overwrites its input parameter from AUTHFRDS",
                    "DATEFMT only distinguishes null and non-null pointers",
                ],
            },
            "results": results,
            "status": "passed",
            "claim_boundary": {
                "bounded_integrated_development_semantics": True,
                "external_cobol_behavior_modeled": False,
                "native_execution_observed": False,
                "native_runtime_qualified": False,
                "mainframe_equivalent": False,
                "production_ready": False,
            },
        }
    )


def validate_integrated_conformance(
    project_root: Path, payload: Mapping[str, Any] | None = None
) -> list[str]:
    expected = build_integrated_conformance(project_root)
    payload = dict(payload or load_json(project_root / "pilot/integrated-qualification/conformance.receipt.json"))
    errors: list[str] = []
    if payload.get("receipt_type") != CONFORMANCE_TYPE:
        errors.append("integrated-pilot-conformance-identity-invalid")
    if not _content_valid(payload):
        errors.append("integrated-pilot-conformance-content-hash-invalid")
    if payload != expected:
        errors.append("integrated-pilot-conformance-drift")
    boundary = payload.get("claim_boundary", {})
    if any(boundary.get(name) is not False for name in (
        "external_cobol_behavior_modeled", "native_execution_observed", "native_runtime_qualified",
        "mainframe_equivalent", "production_ready",
    )):
        errors.append("integrated-pilot-conformance-overclaim")
    return sorted(set(errors))


def _technology_receipt(project_root: Path, technology: str) -> tuple[str, dict[str, Any]]:
    relative, expected_type = TECHNOLOGY_EVIDENCE[technology]
    payload = load_json(project_root / relative)
    actual_type = payload.get("qualification_type") or payload.get("receipt_type")
    if actual_type != expected_type or not _content_valid(payload):
        raise PilotError(f"integrated-pilot-{technology}-qualification-invalid")
    return relative, payload


def build_evidence_matrix(project_root: Path) -> dict[str, Any]:
    selection, package, graph, _ = _inputs(project_root)
    if validate_integrated_scope(selection, package, graph):
        raise PilotError("integrated-pilot-scope-invalid")
    conformance = build_integrated_conformance(project_root)
    cells: list[dict[str, Any]] = []
    for cell in package["cells"]:
        technology = str(cell["technology"])
        receipt_path, receipt = _technology_receipt(project_root, technology)
        cells.append(
            {
                "cell_id": cell["cell_id"],
                "technology": technology,
                "source_paths": list(cell["read_only_source_paths"]),
                "coordination_dependencies": list(cell["coordination_dependencies"]),
                "qualification_mechanism": {
                    "path": receipt_path,
                    "content_sha256": receipt["content_sha256"],
                    "identity": receipt.get("qualification_type") or receipt.get("receipt_type"),
                    "exact_source_acceptance_implied": False,
                },
                "required_deliverables": [
                    {"name": name, "status": "passed-bounded-integrated"}
                    for name in cell["required_deliverables"]
                ],
                "required_acceptance_evidence": [
                    {"name": name, "status": "passed-bounded-synthetic", "receipt_sha256": conformance["content_sha256"]}
                    for name in cell["required_acceptance_evidence"]
                ],
                "required_live_evidence": [
                    {"name": name, "status": "blocked-not-observed"}
                    for name in cell["required_live_evidence"]
                ],
                "integrated_development_evidence_passed": True,
                "native_evidence_passed": False,
                "dispatch_ready": False,
            }
        )
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "matrix_type": MATRIX_TYPE,
            "selection_sha256": selection["content_sha256"],
            "work_package_sha256": package["content_sha256"],
            "source_graph_sha256": graph["content_sha256"],
            "conformance_sha256": conformance["content_sha256"],
            "cells": cells,
            "statistics": {
                "cell_count": len(cells),
                "technology_count": len({item["technology"] for item in cells}),
                "coordination_dependency_count": sum(len(item["coordination_dependencies"]) for item in cells),
                "deliverable_count": sum(len(item["required_deliverables"]) for item in cells),
                "acceptance_evidence_count": sum(len(item["required_acceptance_evidence"]) for item in cells),
                "blocked_live_evidence_count": sum(len(item["required_live_evidence"]) for item in cells),
            },
            "wave_2_integrated_development_ready": True,
            "factory_dispatch_allowed": False,
            "native_execution_observed": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        }
    )


def validate_evidence_matrix(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_evidence_matrix(project_root)
    payload = dict(payload or load_json(project_root / "pilot/integrated-qualification/evidence-matrix.json"))
    errors: list[str] = []
    if payload.get("matrix_type") != MATRIX_TYPE:
        errors.append("integrated-pilot-matrix-identity-invalid")
    if not _content_valid(payload):
        errors.append("integrated-pilot-matrix-content-hash-invalid")
    if payload != expected:
        errors.append("integrated-pilot-matrix-drift")
    cells = [item for item in payload.get("cells", []) if isinstance(item, dict)]
    if len(cells) != 5 or {item.get("technology") for item in cells} != set(REQUIRED_TECHNOLOGIES):
        errors.append("integrated-pilot-matrix-cell-set-invalid")
    if any(item.get("dispatch_ready") is not False or item.get("native_evidence_passed") is not False for item in cells):
        errors.append("integrated-pilot-matrix-overclaim")
    if any(payload.get(name) is not False for name in FALSE_CLAIMS if name in payload):
        errors.append("integrated-pilot-matrix-overclaim")
    return sorted(set(errors))


def build_integrated_ledger(project_root: Path) -> dict[str, Any]:
    selection, package, graph, _ = _inputs(project_root)
    specs = (
        ("selection-and-business-decision", "exact", "bounded-contract"),
        ("work-package-and-five-cell-identity", "exact", "bounded-contract"),
        ("source-file-and-graph-binding", "exact", "bounded-contract"),
        ("cell-coordination-dependency-dag", "exact", "bounded-contract"),
        ("copybook-acct-record-layout", "exact", "bounded-contract"),
        ("authfrds-three-column-projection", "exact", "bounded-contract"),
        ("authfrds-primary-key", "normalized-equivalent", "governed-normalization"),
        ("authfrds-unique-index-order", "normalized-equivalent", "governed-normalization"),
        ("unqualified-single-row-select", "normalized-equivalent", "governed-normalization"),
        ("sql-no-row-and-multiple-row-status", "normalized-equivalent", "governed-normalization"),
        ("cobol-to-pli-call", "normalized-equivalent", "governed-normalization"),
        ("pli-to-cobol-call-contract", "normalized-equivalent", "governed-normalization"),
        ("jcl-step-order", "normalized-equivalent", "governed-normalization"),
        ("jcl-dataset-bindings", "normalized-equivalent", "governed-normalization"),
        ("datefmt-null-pointer-return-code", "normalized-equivalent", "governed-normalization"),
        ("external-cbact04c-business-effects", "policy-decision-required", "unresolved"),
        ("cobol-pli-parameter-representation", "policy-decision-required", "unresolved"),
        ("db2-isolation-locking-and-package-options", "policy-decision-required", "unresolved"),
        ("jcl-condition-restart-and-step-failure", "policy-decision-required", "unresolved"),
        ("datefmt-linkage-amode-and-rmode", "policy-decision-required", "unresolved"),
        ("ebcdic-and-fixed-character-padding", "lossy", "accepted-only-in-bounded-planning"),
        ("decimal-host-variable-binary-representation", "lossy", "accepted-only-in-bounded-planning"),
        ("native-cobol-and-pli-compilation", "unsupported", "excluded-from-claim-scope"),
        ("native-db2-bind-and-execution", "unsupported", "excluded-from-claim-scope"),
        ("native-jes-scheduler-and-dataset-effects", "unsupported", "excluded-from-claim-scope"),
        ("native-hlasm-assembly-binder-and-le-linkage", "unsupported", "excluded-from-claim-scope"),
        ("cics-cbact04c-runtime", "unsupported", "excluded-from-claim-scope"),
        ("transaction-atomicity-across-program-boundaries", "unsupported", "excluded-from-claim-scope"),
        ("operational-recovery-and-rollback", "unsupported", "excluded-from-claim-scope"),
        ("production-cutover-and-release", "unsupported", "excluded-from-claim-scope"),
    )
    entries = [
        {
            "item_id": f"integrated-pilot:{scope}",
            "scope": scope,
            "source_semantics": {"selection": selection["selection_id"], "claim": "bounded-integrated-development"},
            "target_semantics": {"contract": QUALIFICATION_TYPE},
            "classification": classification,
            "rationale": "The six-file pilot is qualified as an integrated bounded development contract; native platform and operational behavior remain independent evidence gates.",
            "evidence_required": [f"{scope}-evidence"],
            "decision": decision,
        }
        for scope, classification, decision in specs
    ]
    statistics = dict(Counter(item["classification"] for item in entries))
    for name in COMPATIBILITY_CLASSES:
        statistics.setdefault(name, 0)
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "ledger_type": LEDGER_TYPE,
            "selection_sha256": selection["content_sha256"],
            "work_package_sha256": package["content_sha256"],
            "source_graph_sha256": graph["content_sha256"],
            "classifications": list(COMPATIBILITY_CLASSES),
            "entries": entries,
            "statistics": statistics,
            "qualification_blocked": True,
            "mainframe_equivalent": False,
            "production_ready": False,
        }
    )


def validate_integrated_ledger(ledger: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != LEDGER_TYPE:
        errors.append("integrated-pilot-ledger-identity-invalid")
    if not _content_valid(ledger):
        errors.append("integrated-pilot-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("integrated-pilot-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    if len(entries) != 30 or len({item.get("item_id") for item in entries}) != 30:
        errors.append("integrated-pilot-ledger-entry-set-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("integrated-pilot-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("integrated-pilot-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("integrated-pilot-ledger-unsupported-not-excluded")
    counts = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != counts.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("integrated-pilot-ledger-statistics-invalid")
    if ledger.get("qualification_blocked") is not True or ledger.get("mainframe_equivalent") is not False or ledger.get("production_ready") is not False:
        errors.append("integrated-pilot-ledger-overclaim")
    return sorted(set(errors))


def build_integrated_qualification(project_root: Path) -> dict[str, Any]:
    selection, package, graph, manifest = _inputs(project_root)
    conformance = build_integrated_conformance(project_root)
    matrix = build_evidence_matrix(project_root)
    ledger = build_integrated_ledger(project_root)
    gates = [
        {"gate": "governed-selection", "status": "passed", "evidence": {"selection_sha256": selection["content_sha256"], "selection_ready": True}},
        {"gate": "five-cell-work-package", "status": "passed", "evidence": {"work_package_sha256": package["content_sha256"], "cell_count": 5}},
        {"gate": "source-and-graph-identity", "status": "passed-static", "evidence": {"source_graph_sha256": graph["content_sha256"], "source_files": list(REQUIRED_SOURCE_FILES)}},
        {"gate": "technology-qualification-mechanisms", "status": "passed-mechanism-bound", "evidence": {"technologies": list(REQUIRED_TECHNOLOGIES), "exact_source_acceptance_implied": False}},
        {"gate": "cobol-copybook-sql-and-pli-call", "status": "passed-bounded-semantic", "evidence": {"program": "ACCOUNTV", "copybook": "ACCTREC", "target": "ACCTPL1"}},
        {"gate": "pli-db2-and-external-cobol-call", "status": "passed-bounded-semantic", "evidence": {"program": "ACCTPL1", "table": "CARDDEMO.AUTHFRDS", "external_program": "CBACT04C"}},
        {"gate": "db2-schema-query-and-index", "status": "passed-bounded-semantic", "evidence": {"columns": 3, "unqualified_selects": 2, "native_db2_observed": False}},
        {"gate": "jcl-step-and-dataset-flow", "status": "passed-bounded-semantic", "evidence": {"job": "ACCTPIL", "steps": ["RUN", "FORMAT"], "native_jes_observed": False}},
        {"gate": "hlasm-pointer-branch-and-return", "status": "passed-bounded-semantic", "evidence": {"program": "DATEFMT", "return_codes": [0, 8], "native_assembly_observed": False}},
        {"gate": "cross-cell-integrated-conformance", "status": "passed-bounded-synthetic", "evidence": {"conformance_sha256": conformance["content_sha256"], **conformance["corpus"]}},
        {"gate": "compatibility-policy-and-live-evidence", "status": "policy-and-native-evidence-required", "evidence": {"ledger_sha256": ledger["content_sha256"], "matrix_sha256": matrix["content_sha256"], "blocked_live_evidence": matrix["statistics"]["blocked_live_evidence_count"]}},
        {"gate": "authorized-native-integrated-execution", "status": "blocked-no-authorized-evidence", "evidence": {"native_execution_observed": False, "signed_equivalence": False, "production_release_allowed": False}},
    ]
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "qualification_type": QUALIFICATION_TYPE,
            "qualification_id": QUALIFICATION_ID,
            "bindings": {
                "selection_sha256": selection["content_sha256"],
                "work_package_sha256": package["content_sha256"],
                "source_graph_sha256": graph["content_sha256"],
                "manifest_sha256": manifest["content_sha256"],
                "conformance_sha256": conformance["content_sha256"],
                "evidence_matrix_sha256": matrix["content_sha256"],
                "compatibility_ledger_sha256": ledger["content_sha256"],
            },
            "inventory": {
                "source_files": 6,
                "cells": 5,
                "technologies": 5,
                "coordination_dependencies": 5,
                "conformance_cases": conformance["corpus"]["case_count"],
                "targeted_boundary_cases": conformance["corpus"]["targeted_boundary_case_count"],
                "mutation_cases": conformance["corpus"]["mutation_case_count"],
                "blocked_cases": conformance["corpus"]["blocked_case_count"],
                "compatibility_items": len(ledger["entries"]),
                "customer_source": False,
            },
            "qualification_gates": gates,
            "wave_2_integrated_development_ready": True,
            "development_ready": True,
            "factory_dispatch_allowed": False,
            "native_execution_observed": False,
            "native_runtime_qualified": False,
            "mainframe_equivalent": False,
            "production_release_allowed": False,
            "production_ready": False,
            "claim_unlocked": "LIGHTYEAR can qualify the exact six-file ACCOUNTV reference slice as a bounded integrated COBOL, PL/I, Db2, JCL, and HLASM development contract while keeping external program behavior, native execution, dispatch, mainframe equivalence, and production release blocked.",
        }
    )


def validate_integrated_qualification(
    project_root: Path, payload: Mapping[str, Any] | None = None
) -> list[str]:
    expected = build_integrated_qualification(project_root)
    payload = dict(payload or load_json(project_root / "pilot/integrated-qualification/qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("integrated-pilot-qualification-identity-invalid")
    if not _content_valid(payload):
        errors.append("integrated-pilot-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("integrated-pilot-qualification-drift")
    gates = [item.get("gate") for item in payload.get("qualification_gates", []) if isinstance(item, dict)]
    if len(gates) != 12 or len(set(gates)) != 12:
        errors.append("integrated-pilot-qualification-gates-incomplete")
    if any(payload.get(name) is not False for name in FALSE_CLAIMS):
        errors.append("integrated-pilot-qualification-overclaim")
    return sorted(set(errors))


def build_artifacts(project_root: Path, output_root: Path) -> dict[str, Any]:
    conformance = build_integrated_conformance(project_root)
    matrix = build_evidence_matrix(project_root)
    ledger = build_integrated_ledger(project_root)
    qualification = build_integrated_qualification(project_root)
    write_json(output_root / "conformance.receipt.json", conformance)
    write_json(output_root / "evidence-matrix.json", matrix)
    write_json(output_root / "compatibility-ledger.json", ledger)
    write_json(output_root / "qualification.json", qualification)
    return {
        "status": "passed",
        "conformance_sha256": conformance["content_sha256"],
        "evidence_matrix_sha256": matrix["content_sha256"],
        "ledger_sha256": ledger["content_sha256"],
        "qualification_sha256": qualification["content_sha256"],
        "wave_2_integrated_development_ready": True,
        "mainframe_equivalent": False,
        "production_ready": False,
    }


def verify_artifacts(project_root: Path) -> list[str]:
    root = project_root / "pilot/integrated-qualification"
    conformance = load_json(root / "conformance.receipt.json")
    matrix = load_json(root / "evidence-matrix.json")
    ledger = load_json(root / "compatibility-ledger.json")
    qualification = load_json(root / "qualification.json")
    errors = (
        validate_integrated_conformance(project_root, conformance)
        + validate_evidence_matrix(project_root, matrix)
        + validate_integrated_ledger(ledger)
        + validate_integrated_qualification(project_root, qualification)
    )
    if ledger != build_integrated_ledger(project_root):
        errors.append("integrated-pilot-ledger-drift")
    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LIGHTYEAR integrated pilot qualification")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    output = (args.output_root or root / "pilot/integrated-qualification").resolve()
    if args.command == "build":
        result = build_artifacts(root, output)
    else:
        errors = verify_artifacts(root)
        result = {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "wave_2_integrated_development_ready": not errors,
            "mainframe_equivalent": False,
            "production_ready": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
