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
CONFORMANCE_TYPE = "lightyear-hlasm-conformance-receipt"
LEDGER_TYPE = "lightyear-hlasm-compatibility-ledger"
QUALIFICATION_TYPE = "lightyear-hlasm-qualification"
CORPUS_ID = "lightyear-hlasm-synthetic-conformance-v1"

GRAPH_MINIMUMS = {
    "nodes": {
        "assembler_dsect": 1,
        "assembler_field": 5,
        "assembler_instruction": 41,
        "assembler_macro": 1,
        "assembler_program": 2,
        "assembler_symbol": 23,
    },
    "edges": {
        "BRANCHES_TO": 9,
        "HAS_FIELD": 5,
        "USES_DSECT": 1,
        "USES_MACRO": 1,
    },
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
    condition_code: int | None = None,
    register_changes: Mapping[str, int] | None = None,
    memory_writes: list[dict[str, Any]] | None = None,
    trace: list[str] | None = None,
    diagnostics: list[str] | None = None,
    status: str = "passed",
) -> dict[str, Any]:
    return {
        "status": status,
        "response": response,
        "result_count": result_count,
        "mutation_count": mutation_count,
        "condition_code": condition_code,
        "register_changes": dict(register_changes or {}),
        "memory_writes": memory_writes or [],
        "trace": trace or [],
        "diagnostics": diagnostics or [],
    }


def _date_format(request: Mapping[str, Any]) -> dict[str, Any]:
    input_type = str(request.get("input_type", ""))[:1]
    output_type = str(request.get("output_type", ""))[:1]
    padded = str(request.get("input_date", ""))[:20].ljust(20)
    output = " " * 20
    error = " " * 38
    branch = "GOTOERR"
    if input_type == "1":
        if padded[4:5] != "-" and output_type != "2":
            output = f"{padded[:4]}-{padded[4:6]}-{padded[6:8]}".ljust(20)
            branch = "EXITL"
    elif input_type == "2" and output_type != "1":
        output = f"{padded[:4]}{padded[5:7]}{padded[8:10]}".ljust(20)
        branch = "EXITL"
    if branch == "GOTOERR":
        error = "INVALID INPUT".ljust(38)
    return {
        "input_type": input_type,
        "input_date": padded,
        "output_type": output_type,
        "output_date": output,
        "error_message": error,
        "branch": branch,
    }


def execute_conformance_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Execute a bounded semantic vector without emulating an assembler or z/OS CPU."""
    request = case.get("request", {})
    operation = str(request.get("operation", "")).upper()

    if operation == "DATE_FORMAT":
        value = _date_format(request)
        valid = not value["error_message"].strip()
        return _result(
            "SUCCESS" if valid else "INVALID_INPUT",
            result_count=int(valid),
            mutation_count=1,
            memory_writes=[
                {"field": "COOUTDT", "value": value["output_date"]},
                {"field": "COERMSG", "value": value["error_message"]},
            ],
            trace=["CLI COINTYPE", f"B {value['branch']}", "MVC OUTPUT" if valid else "MVC COERMSG"],
            diagnostics=[] if valid else ["source-routes-to-invalid-input"],
        )

    if operation == "DSECT_LAYOUT":
        fields = [("COINTYPE", 0, 1), ("COINPDT", 1, 20), ("COOUTYPE", 21, 1), ("COOUTDT", 22, 20), ("COERMSG", 42, 38)]
        requested = str(request.get("field", ""))
        selected = [item for item in fields if not requested or item[0] == requested]
        return _result("SUCCESS" if selected else "ADDRESSING_ERROR", result_count=len(selected), trace=["COPY COCDATFT", f"DSECT LENGTH {sum(item[2] for item in fields)}"])

    if operation in {"MVC", "MVI", "ST"}:
        length = int(request.get("length", 1 if operation == "MVI" else 4))
        offset = int(request.get("offset", 0))
        area_length = int(request.get("area_length", 80))
        valid = length > 0 and offset >= 0 and offset + length <= area_length
        writes = [{"offset": offset, "length": length}] if valid else []
        return _result(
            "SUCCESS" if valid else "ADDRESSING_ERROR",
            result_count=int(valid), mutation_count=int(valid), memory_writes=writes, trace=[f"{operation} {offset}({length})"],
            diagnostics=[] if valid else ["bounded-storage-range-exceeded"],
        )

    if operation in {"CLI", "CLC"}:
        left = str(request.get("left", ""))
        right = str(request.get("right", ""))
        code = 0 if left == right else (1 if left < right else 2)
        return _result("CONDITION_TRUE" if code == 0 else "CONDITION_FALSE", result_count=int(code == 0), condition_code=code, trace=[f"{operation} CC={code}"])

    if operation in {"BE", "BNE", "B"}:
        code = int(request.get("condition_code", 0))
        taken = operation == "B" or (operation == "BE" and code == 0) or (operation == "BNE" and code != 0)
        return _result("BRANCH_TAKEN" if taken else "BRANCH_NOT_TAKEN", result_count=int(taken), condition_code=code, trace=[f"{operation} {request.get('target', 'TARGET')}"])

    if operation == "REGISTER_SEQUENCE":
        return _result("SUCCESS", result_count=1, register_changes={"R13": 4096, "R15": 0}, trace=["STM R14,R12,12(R13)", "LR R13,R12", "LM R14,R12,12(R13)", "SR R15,R15", "BR R14"])
    if operation == "STM":
        first, last = int(request.get("first", 14)), int(request.get("last", 12))
        count = (last - first) % 16 + 1
        return _result("SUCCESS", result_count=count, mutation_count=count, memory_writes=[{"save_area_registers": count}], trace=[f"STM {first},{last}"])
    if operation == "LM":
        first, last = int(request.get("first", 14)), int(request.get("last", 12))
        count = (last - first) % 16 + 1
        return _result("SUCCESS", result_count=count, register_changes={f"R{first}": 1, f"R{last}": 1}, trace=[f"LM {first},{last}"])
    if operation in {"L", "LA", "LR", "SR"}:
        target = str(request.get("target", "R2"))
        source = int(request.get("source", 0))
        if operation == "SR":
            value = 0 if request.get("same_register", True) else int(request.get("target_value", 0)) - source
        elif operation == "LA":
            value = int(request.get("base", 0)) + int(request.get("displacement", 0))
        else:
            value = source
        return _result("SUCCESS", result_count=1, condition_code=0 if operation == "SR" and value == 0 else None, register_changes={target: value}, trace=[f"{operation} {target}"])

    if operation in {"USING", "DROP"}:
        register = str(request.get("register", "R12"))
        active = operation == "USING"
        return _result("SUCCESS", result_count=1, trace=[f"{operation} {request.get('base', 'CSECT')},{register}"], diagnostics=[f"addressability-{'established' if active else 'removed'}"])
    if operation == "COPY":
        member = str(request.get("member", ""))
        found = member == "COCDATFT"
        return _result("SUCCESS" if found else "ASSEMBLY_ERROR", result_count=int(found), trace=[f"COPY {member}"], diagnostics=[] if found else ["copy-member-not-in-pinned-source"])
    if operation == "MACRO_EXPAND":
        name = str(request.get("name", ""))
        found = name == "ASMWAIT"
        return _result("MODELED" if found else "ASSEMBLY_ERROR", result_count=int(found), trace=["ASMWAIT BINLBL", "STIMER WAIT,BINTVL=BINLBL"] if found else [f"MACRO {name}"], diagnostics=["static-expansion-only"] if found else ["macro-not-in-pinned-source"])
    if operation == "LTORG":
        return _result("MODELED", result_count=int(request.get("literal_count", 1)), trace=["LTORG"], diagnostics=["literal-placement-is-assembler-dependent"])
    if operation == "COBOL_PARAMETER_LIST":
        valid = int(request.get("r1_entries", 1)) == 1 and int(request.get("record_length", 0)) == 80
        return _result("MODELED" if valid else "ADDRESSING_ERROR", result_count=int(valid), trace=["L R2,0(R1)", "USING COREC,R2"], diagnostics=["native-le-linkage-not-observed"])
    if operation == "MVSWAIT_HANDOFF":
        interval = int(request.get("interval", 0))
        valid = 0 <= interval <= 0x7FFFFFFF
        return _result(
            "MODELED" if valid else "INVALID_INTERVAL", result_count=int(valid), trace=["L R5,0(R1)", "L R1,0(R5)", "ST R1,BINLBL", "ASMWAIT BINLBL"],
            diagnostics=["stimer-not-invoked", "elapsed-time-not-qualified"],
        )

    unsupported = {
        "PRIVILEGED_INSTRUCTION": "privileged-system-state-unsupported",
        "VECTOR_CRYPTO": "vector-and-crypto-instruction-families-unsupported",
        "SELF_MODIFYING_CODE": "self-modifying-code-unsupported",
        "AUTHORIZED_SVC": "svc-and-authorized-services-unsupported",
    }
    if operation in unsupported:
        return _result("UNSUPPORTED", status="blocked", diagnostics=[unsupported[operation]], trace=[operation])
    return _result("UNSUPPORTED", status="blocked", diagnostics=["unsupported-operation"], trace=[operation or "MISSING"])


def validate_hlasm_graph(graph_receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    statistics = graph_receipt.get("statistics", {})
    for group, field in (("nodes", "nodes_by_kind"), ("edges", "edges_by_relation")):
        observed = statistics.get(field, {})
        for name, minimum in GRAPH_MINIMUMS[group].items():
            if not isinstance(observed.get(name), int) or observed.get(name, 0) < minimum:
                errors.append(f"hlasm-graph-{group}-{name}-below-minimum")
    if not isinstance(graph_receipt.get("content_sha256"), str):
        errors.append("hlasm-graph-content-hash-missing")
    return sorted(errors)


def _corpus(project_root: Path) -> tuple[Path, dict[str, Any]]:
    path = project_root / "readiness/asm-date/conformance/cases.json"
    manifest = _load(path)
    if manifest.get("content_sha256") != content_hash(manifest):
        raise ValueError("HLASM corpus manifest content_sha256 is invalid")
    if manifest.get("corpus_id") != CORPUS_ID:
        raise ValueError("HLASM corpus identity is invalid")
    return path, manifest


def build_hlasm_conformance(project_root: Path) -> dict[str, Any]:
    _, manifest = _corpus(project_root)
    graph = _load(project_root / "knowledge/graph.receipt.json")
    graph_errors = validate_hlasm_graph(graph)
    if graph_errors:
        raise ValueError("HLASM graph coverage failed: " + ", ".join(graph_errors))
    cases = manifest.get("cases", [])
    ids = [item.get("id") for item in cases if isinstance(item, dict)]
    if len(cases) != 40 or len(set(ids)) != 40 or any(not item for item in ids):
        raise ValueError("HLASM corpus must bind the exact 40-case set")
    results: list[dict[str, Any]] = []
    features: Counter[str] = Counter()
    for case in cases:
        observed = execute_conformance_case(case)
        if (
            observed["status"] != case.get("expected_status")
            or observed["response"] != case.get("expected_response")
            or observed["mutation_count"] != case.get("expected_mutation_count")
        ):
            raise ValueError(f"HLASM conformance expectation failed: {case['id']}")
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
            "programs": ["COBDATFT", "MVSWAIT"],
            "instruction_subset": ["B", "BE", "BNE", "BR", "CLC", "CLI", "L", "LA", "LM", "LR", "MVC", "MVI", "SR", "ST", "STM"],
            "directives": ["COPY", "CSECT", "DROP", "DSECT", "DS", "END", "EQU", "LTORG", "MACRO", "MEND", "START", "USING"],
            "responses": sorted({item["observed"]["response"] for item in results}),
            "explicit_native_gaps": [
                "authorized HLASM assembly, macro expansion, object generation, and binder execution",
                "native z/Architecture instruction, condition-code, addressing, storage-key, and protection behavior",
                "AMODE, RMODE, residency, reentrancy, and executable module attributes",
                "Language Environment and COBOL linkage, save-area, recovery, and abend behavior",
                "STIMER, SVC, authorized services, timing, dispatching, and system state",
            ],
        },
        "results": results,
        "status": "passed",
        "claim_boundary": {
            "native_hlasm_qualified": False,
            "assembler_qualified": False,
            "binder_qualified": False,
            "le_linkage_qualified": False,
            "system_services_qualified": False,
            "runtime_equivalent": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        },
    })


def validate_hlasm_conformance(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_hlasm_conformance(project_root)
    payload = dict(payload or _load(project_root / "readiness/asm-date/conformance.receipt.json"))
    errors: list[str] = []
    if payload.get("receipt_type") != CONFORMANCE_TYPE:
        errors.append("hlasm-conformance-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("hlasm-conformance-content-hash-invalid")
    if payload != expected:
        errors.append("hlasm-conformance-drift")
    if any(payload.get("claim_boundary", {}).get(name) is not False for name in (
        "native_hlasm_qualified", "assembler_qualified", "binder_qualified", "le_linkage_qualified",
        "system_services_qualified", "runtime_equivalent", "mainframe_equivalent", "production_ready",
    )):
        errors.append("hlasm-conformance-overclaims-readiness")
    return sorted(set(errors))


def build_hlasm_ledger(graph_receipt: Mapping[str, Any]) -> dict[str, Any]:
    specs = (
        ("program-and-entry-identity", "exact", "bounded-contract", ["source-member-and-entry-directive-binding"]),
        ("csect-and-start", "normalized-equivalent", "governed-normalization", ["control-section-and-origin-vectors"]),
        ("instruction-and-operand-discovery", "exact", "bounded-contract", ["line-addressed-mnemonic-and-operand-inventory"]),
        ("equ-symbols-and-labels", "exact", "bounded-contract", ["symbol-definition-and-branch-target-binding"]),
        ("dsect-identity", "exact", "bounded-contract", ["COCDATFT-source-and-copy-binding"]),
        ("ds-field-layout", "exact", "bounded-contract", ["offset-length-and-total-size-vectors"]),
        ("alignment-and-padding", "policy-decision-required", "unresolved", ["assembler-alignment-and-caller-layout-baseline"]),
        ("ebcdic-literals-and-collation", "policy-decision-required", "unresolved", ["CCSID-literal-pool-and-byte-compare-baseline"]),
        ("mvc-and-mvi", "normalized-equivalent", "governed-normalization", ["overlap-range-and-byte-write-vectors"]),
        ("cli-and-clc", "normalized-equivalent", "governed-normalization", ["unsigned-byte-compare-and-condition-code-vectors"]),
        ("condition-codes", "normalized-equivalent", "governed-normalization", ["CC-zero-low-high-and-consumer-vectors"]),
        ("b-be-bne-and-br", "normalized-equivalent", "governed-normalization", ["taken-not-taken-and-return-target-vectors"]),
        ("l-la-st-lr-and-sr", "normalized-equivalent", "governed-normalization", ["register-address-value-and-overflow-vectors"]),
        ("stm-lm-save-area", "policy-decision-required", "unresolved", ["native-save-area-chain-and-register-preservation"]),
        ("using-and-drop", "normalized-equivalent", "governed-normalization", ["base-register-addressability-vectors"]),
        ("copy-member-resolution", "exact", "bounded-contract", ["SYSLIB-search-order-and-member-digest"]),
        ("literal-pools-and-ltorg", "lossy", "accepted-only-in-bounded-planning", ["assembler-generated-literal-address-and-placement"]),
        ("macro-definition-and-expansion", "normalized-equivalent", "governed-normalization", ["ASMWAIT-parameter-and-expansion-vectors"]),
        ("cobol-parameter-list", "policy-decision-required", "unresolved", ["native-R1-pointer-list-and-31-bit-addressing-baseline"]),
        ("standard-linkage", "policy-decision-required", "unresolved", ["R13-R14-R15-save-area-and-LE-baseline"]),
        ("amode-rmode-and-residency", "policy-decision-required", "unresolved", ["object-and-load-module-attribute-baseline"]),
        ("assembler-diagnostics-and-object-code", "unsupported", "excluded-from-claim-scope", ["authorized-HLASM-listing-and-object-deck"]),
        ("binder-and-external-symbol-resolution", "unsupported", "excluded-from-claim-scope", ["binder-map-load-library-and-entry-evidence"]),
        ("stimer-and-mvswait-timing", "unsupported", "excluded-from-claim-scope", ["authorized-STIMER-elapsed-time-and-abend-vectors"]),
        ("abend-recovery-and-dumps", "unsupported", "excluded-from-claim-scope", ["ESTAE-recovery-dump-and-return-code-evidence"]),
        ("storage-keys-and-protection", "unsupported", "excluded-from-claim-scope", ["native-key-fetch-protection-and-address-space-evidence"]),
        ("privileged-svc-and-authorized-services", "unsupported", "excluded-from-claim-scope", ["authorized-state-and-SVC-qualification"]),
        ("self-modifying-vector-and-crypto-code", "unsupported", "excluded-from-claim-scope", ["separate-instruction-family-and-cache-coherency-qualification"]),
    )
    entries = [{
        "item_id": f"hlasm:{scope}",
        "scope": scope,
        "source_semantics": {"platform": "IBM HLASM and z/Architecture", "claim": "bounded-static-and-synthetic-evidence"},
        "target_semantics": {"contract": QUALIFICATION_TYPE},
        "classification": classification,
        "rationale": "Static inventory and deterministic bounded vectors are governed separately from native assembly, object code, linkage, system services, CPU, storage, and recovery behavior.",
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


def validate_hlasm_ledger(ledger: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != LEDGER_TYPE:
        errors.append("hlasm-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("hlasm-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("hlasm-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    if len(entries) != 28 or len({item.get("item_id") for item in entries}) != len(entries):
        errors.append("hlasm-ledger-entry-set-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("hlasm-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("hlasm-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("hlasm-ledger-unsupported-not-excluded")
    counts = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != counts.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("hlasm-ledger-statistics-invalid")
    if ledger.get("qualification_blocked") is not True:
        errors.append("hlasm-ledger-qualification-gate-invalid")
    if ledger.get("mainframe_equivalent") is not False or ledger.get("production_ready") is not False:
        errors.append("hlasm-ledger-overclaims-readiness")
    return sorted(set(errors))


def build_hlasm_qualification(project_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    _, manifest = _corpus(project_root)
    conformance = build_hlasm_conformance(project_root)
    ledger = build_hlasm_ledger(graph)
    comparison = _load(project_root / "readiness/asm-date/comparison.json")
    readiness = _load(project_root / "readiness/asm-date/readiness-receipt.json")
    nodes = graph["statistics"]["nodes_by_kind"]
    edges = graph["statistics"]["edges_by_relation"]
    corpus = conformance["corpus"]
    inventory = {
        "assembler_programs": nodes.get("assembler_program", 0),
        "assembler_instructions": nodes.get("assembler_instruction", 0),
        "assembler_symbols": nodes.get("assembler_symbol", 0),
        "assembler_dsects": nodes.get("assembler_dsect", 0),
        "assembler_fields": nodes.get("assembler_field", 0),
        "assembler_macros": nodes.get("assembler_macro", 0),
        "branch_edges": edges.get("BRANCHES_TO", 0),
        "uses_dsect_edges": edges.get("USES_DSECT", 0),
        "uses_macro_edges": edges.get("USES_MACRO", 0),
        "corpus_cases": corpus["case_count"],
        "targeted_boundary_cases": corpus["targeted_boundary_case_count"],
        "mutation_cases": corpus["mutation_case_count"],
        "blocked_cases": corpus["blocked_case_count"],
        "observed_feature_categories": conformance["coverage"]["observed_feature_count"],
        "customer_source": False,
    }
    gates = [
        {"gate": "estate-graph-inventory", "status": "passed-static", "evidence": {"graph_sha256": graph["content_sha256"], **{key: inventory[key] for key in ("assembler_programs", "assembler_instructions", "assembler_symbols", "assembler_dsects", "assembler_fields", "assembler_macros")}}},
        {"gate": "corpus-and-provenance", "status": "passed-bounded-synthetic", "evidence": {"conformance_sha256": conformance["content_sha256"], **corpus}},
        {"gate": "program-directives-symbols-and-source", "status": "passed-static", "evidence": {"programs": conformance["coverage"]["programs"], "directives": conformance["coverage"]["directives"]}},
        {"gate": "dsect-fields-storage-and-literals", "status": "passed-bounded-semantic", "evidence": {"dsects": inventory["assembler_dsects"], "fields": inventory["assembler_fields"], "native_alignment_observed": False}},
        {"gate": "instruction-and-memory-subset", "status": "passed-bounded-semantic", "evidence": {"instruction_subset": conformance["coverage"]["instruction_subset"], "native_cpu_observed": False}},
        {"gate": "condition-codes-and-branches", "status": "passed-bounded-semantic", "evidence": {"branch_edges": inventory["branch_edges"], "native_psw_observed": False}},
        {"gate": "register-addressing-save-area-and-linkage", "status": "policy-decision-required", "evidence": {"synthetic_register_vectors": True, "native_le_or_cobol_linkage_observed": False}},
        {"gate": "macro-stimer-amode-rmode-and-binder", "status": "excluded-unqualified", "evidence": {"macro_expansion_static": True, "stimer": False, "amode_rmode": False, "binder": False}},
        {"gate": "privileged-storage-protection-recovery-and-broad-instructions", "status": "excluded-unqualified", "evidence": {"privileged": False, "storage_protection": False, "recovery": False, "broad_instruction_families": False}},
        {"gate": "cobdatft-private-differential-proof", "status": "passed-local-development", "evidence": {"comparison_sha256": comparison["content_sha256"], "readiness_sha256": readiness["content_sha256"], "behavior_match": comparison.get("behavior_match") is True}},
        {"gate": "authorized-native-hlasm-build-and-execution", "status": "blocked-no-authorized-zos-evidence", "evidence": {"zos_observed_baseline": readiness.get("checks", {}).get("zos_observed_baseline") is True, "assembly_listing": False, "binder_map": False, "load_module": False, "signed_equivalence": False}},
    ]
    return seal({
        "schema_version": SCHEMA_VERSION,
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": "carddemo-hlasm-v0.41",
        "bindings": {
            "graph_content_sha256": graph["content_sha256"],
            "manifest_sha256": manifest["content_sha256"],
            "conformance_sha256": conformance["content_sha256"],
            "compatibility_ledger_sha256": ledger["content_sha256"],
            "date_comparison_sha256": comparison["content_sha256"],
            "date_readiness_sha256": readiness["content_sha256"],
        },
        "inventory": inventory,
        "qualification_gates": gates,
        "required_native_evidence": [
            "authorized z/OS, HLASM, macro library, assembler option, operator, and security identities",
            "source, macro, COPY member, assembly listing, object deck, binder map, and load module digests",
            "native instruction, condition-code, branch, addressing, overlap, alignment, and literal-pool vectors",
            "AMODE, RMODE, residency, reentrancy, entry point, and external-symbol attributes",
            "COBOL and Language Environment parameter-list, save-area, register, return, and abend evidence",
            "STIMER interval, elapsed-time, dispatching, invalid-parameter, and recovery evidence",
            "storage-key, protection, SVC, authorized-state, dump, and operational-policy decisions",
            "independently signed differential equivalence receipt",
        ],
        "qualification_mechanism_ready": True,
        "development_ready": True,
        "native_hlasm_qualified": False,
        "assembler_qualified": False,
        "binder_qualified": False,
        "le_linkage_qualified": False,
        "system_services_qualified": False,
        "runtime_equivalent": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can inventory and fail-closed qualify the bounded COBDATFT/MVSWAIT HLASM subset without claiming native assembly, binding, linkage, system-service, CPU, runtime, mainframe, or production equivalence.",
    })


def validate_hlasm_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_hlasm_qualification(project_root)
    payload = dict(payload or _load(project_root / "readiness/asm-date/qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("hlasm-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("hlasm-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("hlasm-qualification-drift")
    gates = [item.get("gate") for item in payload.get("qualification_gates", []) if isinstance(item, dict)]
    if len(gates) != 11 or len(set(gates)) != 11:
        errors.append("hlasm-qualification-gates-incomplete")
    if any(payload.get(name) is not False for name in (
        "native_hlasm_qualified", "assembler_qualified", "binder_qualified", "le_linkage_qualified",
        "system_services_qualified", "runtime_equivalent", "mainframe_equivalent", "production_ready",
    )):
        errors.append("hlasm-qualification-overclaims-readiness")
    return sorted(set(errors))


def build_artifacts(project_root: Path, output_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    conformance = build_hlasm_conformance(project_root)
    ledger = build_hlasm_ledger(graph)
    qualification = build_hlasm_qualification(project_root)
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
    parser = argparse.ArgumentParser(description="LIGHTYEAR HLASM qualification hardening")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    output = (args.output_root or root / "readiness/asm-date").resolve()
    if args.command == "build":
        result = build_artifacts(root, output)
    else:
        expected_conformance = build_hlasm_conformance(root)
        expected_ledger = build_hlasm_ledger(_load(root / "knowledge/graph.receipt.json"))
        conformance = _load(root / "readiness/asm-date/conformance.receipt.json")
        ledger = _load(root / "readiness/asm-date/compatibility-ledger.json")
        errors = validate_hlasm_conformance(root, conformance) + validate_hlasm_ledger(ledger) + validate_hlasm_qualification(root)
        if conformance != expected_conformance:
            errors.append("hlasm-conformance-drift")
        if ledger != expected_ledger:
            errors.append("hlasm-ledger-drift")
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
