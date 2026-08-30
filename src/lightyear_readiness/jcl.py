from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import write_json
from lightyear_data.contracts import content_hash, seal
from lightyear_data.semantic_core import COMPATIBILITY_CLASSES


SCHEMA_VERSION = "1.0"
QUALIFICATION_TYPE = "lightyear-jcl-qualification"
LEDGER_TYPE = "lightyear-jcl-compatibility-ledger"
CONFORMANCE_TYPE = "lightyear-jcl-conformance-receipt"
SUPPORTED_OPERATIONS = {
    "JOB", "PROC", "PEND", "EXEC", "DD", "SET", "INCLUDE", "JCLLIB",
    "IF", "ELSE", "ENDIF", "OUTPUT",
}
UNSUPPORTED_OPERATIONS = {"XMIT", "CNTL", "ENDCNTL", "COMMAND"}
VALID_DISPOSITIONS = {"NEW", "OLD", "SHR", "MOD"}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _source_hash(path: Path) -> str:
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _diagnostic(code: str, line: int, column: int = 1) -> dict[str, Any]:
    return {"code": code, "line": line, "column": column}


def _parameters(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in re.finditer(r"(?:^|,)\s*([A-Z0-9$#@]+)\s*=\s*(\([^)]*\)|'[^']*'|[^,\s]+)", text, re.I):
        result[match.group(1).upper()] = match.group(2).strip()
    return result


def parse_jcl_source(source: str, path: str = "fixture.jcl") -> dict[str, Any]:
    """Parse a deliberately bounded JCL subset without implying JES execution semantics."""
    features: set[str] = set()
    diagnostics: list[dict[str, Any]] = []
    statements: list[dict[str, Any]] = []
    container_count = 0
    if_depth = 0
    in_stream = False

    for line_number, raw in enumerate(source.replace("\r\n", "\n").replace("\r", "\n").splitlines(), 1):
        line = raw.rstrip()
        upper = line.upper()
        if in_stream:
            if upper.startswith("/*"):
                in_stream = False
                continue
            if not upper.startswith("//"):
                continue
            in_stream = False
        if not line.strip():
            continue
        if upper.startswith("//*"):
            if re.search(r"(?:%OPC|%TWS|CONTROL-M|CA7|ESP)", upper):
                features.add("scheduler-directive")
                diagnostics.append(_diagnostic("unsupported-scheduler-directive", line_number))
            else:
                features.add("comment")
            continue
        if upper.startswith("/*"):
            features.add("jes-control-statement")
            diagnostics.append(_diagnostic("unsupported-jes-control-statement", line_number))
            continue
        if re.match(r"^//\s+[A-Z0-9$#@]+\s*=", upper):
            features.add("continued-parameters")
            if re.search(r"&[A-Z0-9$#@]+", upper):
                features.add("symbolic-reference")
            if re.search(r"\bDCB\s*=", upper):
                features.add("record-layout")
            if re.search(r"\bSPACE\s*=", upper):
                features.add("space-allocation")
            continue
        if not upper.startswith("//"):
            diagnostics.append(_diagnostic("malformed-jcl-record", line_number))
            continue

        match = re.match(r"^//([A-Z0-9$#@.]*)\s+([A-Z]+)\b(.*)$", upper)
        if not match:
            diagnostics.append(_diagnostic("malformed-jcl-statement", line_number))
            continue
        name, operation, tail = match.groups()
        parts = name.split(".") if name else []
        if any(len(part) > 8 for part in parts):
            diagnostics.append(_diagnostic("invalid-statement-name", line_number, 3))
        if operation in UNSUPPORTED_OPERATIONS or operation not in SUPPORTED_OPERATIONS:
            diagnostics.append(_diagnostic("unsupported-operation", line_number))
            statements.append({"name": name, "operation": operation, "line": line_number})
            continue

        params = _parameters(tail)
        statements.append({"name": name, "operation": operation, "line": line_number, "parameters": params})
        if re.search(r"&[A-Z0-9$#@]+", tail):
            features.add("symbolic-reference")

        if operation == "JOB":
            container_count += 1
            features.add("job-card")
            if "RESTART" in params:
                features.add("restart-control")
            if "TYPRUN" in params:
                features.add("typrun-control")
        elif operation == "PROC":
            container_count += 1
            features.add("procedure-definition")
            if "=" in tail:
                features.add("symbolic-default")
        elif operation == "PEND":
            features.add("procedure-end")
        elif operation == "SET":
            features.add("symbolic-set")
        elif operation == "INCLUDE":
            features.add("include-member")
        elif operation == "JCLLIB":
            features.add("procedure-library")
        elif operation == "EXEC":
            executable = params.get("PGM")
            procedure = params.get("PROC")
            bare = re.match(r"\s*([A-Z0-9$#@-]+)(?:\s|,|$)", tail)
            if executable:
                features.add("program-exec")
                target = executable.strip("'\"")
                if target == "IDCAMS":
                    features.add("utility-exec")
                elif target in {"IKJEFT01", "IKJEFT1A", "IKJEFT1B"}:
                    features.add("db2-boundary")
                elif target == "DFSRRC00":
                    features.add("ims-boundary")
                elif target.startswith("DFH"):
                    features.add("cics-boundary")
            elif procedure or (bare and "=" not in bare.group(1)):
                features.add("procedure-exec")
            else:
                diagnostics.append(_diagnostic("exec-target-missing", line_number))
            if "COND" in params:
                features.add("condition-code-bypass")
            if "PARM" in params:
                features.add("program-parameters")
            if any(key in params for key in ("TIME", "REGION")):
                features.add("execution-limits")
        elif operation == "DD":
            features.add("dd-statement")
            if "." in name:
                features.add("dd-override")
            if not name:
                features.add("dd-concatenation")
            if "DSN" in params:
                dsn = params["DSN"]
                features.add("dataset-allocation")
                if "&&" in dsn:
                    features.add("temporary-dataset")
                if re.search(r"\([+-]?\d+\)$", dsn):
                    features.add("generation-dataset")
            if "DISP" in params:
                features.add("disposition")
                primary = params["DISP"].lstrip("(").split(",", 1)[0].strip()
                if primary not in VALID_DISPOSITIONS:
                    diagnostics.append(_diagnostic("invalid-disposition", line_number))
            if "SYSOUT" in params:
                features.add("sysout")
            if re.search(r"\bDUMMY\b", tail):
                features.add("dummy-dd")
            if "DCB" in params:
                features.add("record-layout")
            if "SPACE" in params:
                features.add("space-allocation")
            if (
                re.search(r"(?:^|,)\s*\*(?:\s|$)", tail)
                or re.search(r"(?:^|,)\s*DATA(?:\s|,|$)", tail)
            ) and "DSN" not in params:
                features.add("instream-data")
                in_stream = True
        elif operation == "IF":
            features.add("conditional-control")
            if_depth += 1
        elif operation == "ELSE":
            features.add("conditional-control")
            if if_depth == 0:
                diagnostics.append(_diagnostic("unmatched-else", line_number))
        elif operation == "ENDIF":
            features.add("conditional-control")
            if if_depth == 0:
                diagnostics.append(_diagnostic("unmatched-endif", line_number))
            else:
                if_depth -= 1
        elif operation == "OUTPUT":
            features.add("output-descriptor")

    if if_depth:
        diagnostics.append(_diagnostic("unterminated-if", max(1, len(source.splitlines()))))
    if container_count == 0:
        diagnostics.append(_diagnostic("missing-job-or-procedure", 1))
    if container_count > 1:
        diagnostics.append(_diagnostic("multiple-job-or-procedure-containers", 1))
    diagnostics = sorted(diagnostics, key=lambda item: (item["line"], item["column"], item["code"]))
    return {
        "path": path,
        "status": "blocked" if diagnostics else "passed",
        "features": sorted(features),
        "statements": statements,
        "diagnostics": diagnostics,
    }


def _corpus_paths(project_root: Path) -> tuple[Path, Path]:
    corpus = project_root / "readiness/jcl/corpus"
    return corpus, corpus / "manifest.json"


def build_jcl_conformance(project_root: Path) -> dict[str, Any]:
    corpus, manifest_path = _corpus_paths(project_root)
    manifest = _load(manifest_path)
    graph = _load(project_root / "knowledge/graph.receipt.json")
    if manifest.get("content_sha256") != content_hash(manifest):
        raise ValueError("JCL corpus manifest content_sha256 is invalid")
    cases = manifest.get("cases", [])
    declared = [str(item.get("path", "")) for item in cases if isinstance(item, dict)]
    actual = sorted(path.name for path in corpus.glob("*.jcl"))
    if sorted(declared) != actual or len(set(declared)) != len(declared):
        raise ValueError("JCL corpus manifest must bind the exact source set")

    results: list[dict[str, Any]] = []
    feature_counts: Counter[str] = Counter()
    for case in cases:
        path = corpus / case["path"]
        parsed = parse_jcl_source(path.read_text(encoding="utf-8"), case["path"])
        diagnostic_codes = [item["code"] for item in parsed["diagnostics"]]
        expected_features = sorted(case["expected_features"])
        passed = (
            parsed["status"] == case["expected_status"]
            and diagnostic_codes == case["expected_diagnostics"]
            and all(feature in parsed["features"] for feature in expected_features)
        )
        if not passed:
            raise ValueError(f"JCL conformance expectation failed: {case['id']}")
        feature_counts.update(parsed["features"])
        results.append({
            "id": case["id"],
            "path": case["path"],
            "classification": case["classification"],
            "status": parsed["status"],
            "features": parsed["features"],
            "diagnostics": parsed["diagnostics"],
            "source_sha256": _source_hash(path),
            "passed": True,
        })
    classifications = Counter(item["classification"] for item in cases)
    blocked = sum(item["status"] == "blocked" for item in results)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "receipt_type": CONFORMANCE_TYPE,
        "corpus_id": manifest["corpus_id"],
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
            "observed_features": sorted(feature_counts),
            "observed_feature_count": len(feature_counts),
            "explicit_native_gaps": [
                "JES2/JES3 conversion and interpretation",
                "catalog and SMS allocation effects",
                "authorized program and utility execution",
                "scheduler dependency and calendar semantics",
                "restart, checkpoint, condition-code, and abend behavior",
                "RACF identity and surrogate submission controls",
            ],
        },
        "results": results,
        "status": "passed",
        "claim_boundary": {
            "jes_qualified": False,
            "scheduler_qualified": False,
            "runtime_equivalent": False,
            "restart_equivalent": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        },
    })


def validate_jcl_conformance(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_jcl_conformance(project_root)
    payload = dict(payload or _load(project_root / "readiness/jcl/conformance.receipt.json"))
    errors: list[str] = []
    if payload.get("receipt_type") != CONFORMANCE_TYPE:
        errors.append("jcl-conformance-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("jcl-conformance-content-hash-invalid")
    if payload != expected:
        errors.append("jcl-conformance-drift")
    claims = payload.get("claim_boundary", {})
    if any(claims.get(name) is not False for name in (
        "jes_qualified", "scheduler_qualified", "runtime_equivalent",
        "restart_equivalent", "mainframe_equivalent", "production_ready",
    )):
        errors.append("jcl-conformance-overclaims-readiness")
    return sorted(set(errors))


def build_jcl_ledger(graph_receipt: Mapping[str, Any]) -> dict[str, Any]:
    specs = (
        ("job-card-and-accounting", "exact", "bounded-contract", ["job-card-parse-cases"]),
        ("job-class-message-and-notify-routing", "policy-decision-required", "unresolved", ["installation-policy-and-JES-baseline"]),
        ("cataloged-and-instream-procedures", "normalized-equivalent", "governed-normalization", ["procedure-expansion-and-override-cases"]),
        ("symbolic-parameters-and-set", "policy-decision-required", "unresolved", ["substitution-order-and-system-symbol-baseline"]),
        ("include-and-jcllib-search-order", "policy-decision-required", "unresolved", ["exact-procedure-library-and-include-closure"]),
        ("exec-pgm-resolution", "normalized-equivalent", "governed-normalization", ["load-library-and-program-identity-evidence"]),
        ("exec-procedure-resolution", "policy-decision-required", "unresolved", ["cataloged-procedure-resolution-listing"]),
        ("parm-time-and-region", "normalized-equivalent", "governed-normalization", ["parameter-and-limit-vectors"]),
        ("dd-name-and-concatenation", "normalized-equivalent", "governed-normalization", ["ordered-concatenation-and-override-cases"]),
        ("dsn-and-temporary-datasets", "normalized-equivalent", "governed-normalization", ["dataset-identity-and-lifetime-cases"]),
        ("disposition-and-catalog-effects", "policy-decision-required", "unresolved", ["normal-and-abnormal-termination-catalog-baseline"]),
        ("gdg-resolution-and-rolloff", "policy-decision-required", "unresolved", ["live-catalog-generation-baseline"]),
        ("dcb-record-layout-and-labels", "policy-decision-required", "unresolved", ["catalog-SMS-and-open-time-resolution"]),
        ("space-sms-and-volume-allocation", "lossy", "accepted-only-in-bounded-planning", ["storage-class-management-class-and-volume-policy"]),
        ("instream-data-dummy-and-sysout", "normalized-equivalent", "governed-normalization", ["delimiter-spool-and-record-fidelity-cases"]),
        ("cond-and-if-then-else", "policy-decision-required", "unresolved", ["step-return-code-abend-and-bypass-baseline"]),
        ("restart-and-checkpoint", "policy-decision-required", "unresolved", ["authorized-restart-and-data-state-evidence"]),
        ("ibm-utilities", "unsupported", "excluded-from-claim-scope", ["utility-specific-control-and-output-qualification"]),
        ("scheduler-directives-and-calendars", "unsupported", "excluded-from-claim-scope", ["scheduler-export-dependencies-and-calendar-baseline"]),
        ("jes-control-statements", "unsupported", "excluded-from-claim-scope", ["installation-JES2-or-JES3-control-baseline"]),
        ("db2-cics-ims-execution-boundaries", "unsupported", "excluded-from-claim-scope", ["MS-35.1-MS-39-and-MS-40-native-evidence"]),
        ("racf-submission-and-surrogate-identity", "policy-decision-required", "unresolved", ["authorized-identity-and-security-policy-evidence"]),
    )
    entries = [{
        "item_id": f"jcl:{scope}",
        "scope": scope,
        "source_semantics": {"language": "IBM z/OS JCL", "claim": "bounded-static-and-synthetic-evidence"},
        "target_semantics": {"contract": QUALIFICATION_TYPE},
        "classification": classification,
        "rationale": "JCL syntax, installation policy, and runtime effects are governed independently; static parsing cannot establish JES, catalog, scheduler, or restart equivalence.",
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


def validate_jcl_ledger(ledger: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != LEDGER_TYPE:
        errors.append("jcl-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("jcl-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("jcl-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    if len(entries) != 22 or len({item.get("item_id") for item in entries}) != len(entries):
        errors.append("jcl-ledger-entry-set-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("jcl-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("jcl-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("jcl-ledger-unsupported-not-excluded")
    expected = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != expected.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("jcl-ledger-statistics-invalid")
    if ledger.get("qualification_blocked") is not True:
        errors.append("jcl-ledger-qualification-gate-invalid")
    if ledger.get("mainframe_equivalent") is not False or ledger.get("production_ready") is not False:
        errors.append("jcl-ledger-overclaims-readiness")
    return sorted(set(errors))


def build_jcl_qualification(project_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    manifest = _load(project_root / "readiness/jcl/corpus/manifest.json")
    conformance = build_jcl_conformance(project_root)
    ledger = build_jcl_ledger(graph)
    nodes = graph["statistics"]["nodes_by_kind"]
    edges = graph["statistics"]["edges_by_relation"]
    corpus = conformance["corpus"]
    inventory = {
        "jobs": nodes.get("jcl_job", 0),
        "procedures": nodes.get("jcl_procedure", 0),
        "steps": nodes.get("jcl_step", 0),
        "dd_allocations": nodes.get("jcl_dd_allocation", 0),
        "dd_names": nodes.get("jcl_dd_name", 0),
        "execute_edges": edges.get("EXECUTES", 0),
        "dd_edges": edges.get("HAS_DD", 0),
        "dataset_bindings": edges.get("ALLOCATES", 0),
        "corpus_cases": corpus["case_count"],
        "targeted_boundary_cases": corpus["targeted_boundary_case_count"],
        "mutation_cases": corpus["mutation_case_count"],
        "blocked_cases": corpus["blocked_case_count"],
        "observed_feature_categories": conformance["coverage"]["observed_feature_count"],
        "customer_source": False,
    }
    gates = [
        {"gate": "estate-inventory", "status": "passed-static", "evidence": {"graph_sha256": graph["content_sha256"], "jobs": inventory["jobs"], "procedures": inventory["procedures"], "steps": inventory["steps"], "dd_allocations": inventory["dd_allocations"]}},
        {"gate": "corpus-and-provenance", "status": "passed-bounded-synthetic", "evidence": {"conformance_sha256": conformance["content_sha256"], **corpus}},
        {"gate": "lexical-and-statement-parsing", "status": "passed-supported-subset", "evidence": {"observed_feature_categories": inventory["observed_feature_categories"], "native_converter": False}},
        {"gate": "jobs-procedures-and-symbolics", "status": "passed-static-subset", "evidence": {"procedures": inventory["procedures"], "system_symbol_resolution_observed": False}},
        {"gate": "step-exec-and-program-resolution", "status": "passed-static-subset", "evidence": {"steps": inventory["steps"], "execute_edges": inventory["execute_edges"], "load_library_resolution_observed": False}},
        {"gate": "dd-dataset-and-allocation-semantics", "status": "passed-bounded-static", "evidence": {"dd_allocations": inventory["dd_allocations"], "dd_edges": inventory["dd_edges"], "live_catalog_observed": False, "sms_observed": False}},
        {"gate": "condition-codes-restart-and-recovery", "status": "policy-decision-required", "evidence": {"native_return_codes_observed": False, "abend_paths_observed": False, "restart_state_observed": False}},
        {"gate": "utilities-jes-scheduler-and-security-boundaries", "status": "excluded-unqualified", "evidence": {"utility_execution_observed": False, "scheduler_export_present": False, "racf_submission_observed": False}},
        {"gate": "mutation-tamper-and-overclaim-resistance", "status": "passed-local-development", "evidence": {"mutation_cases": inventory["mutation_cases"], "content_addressed": True}},
        {"gate": "authorized-jes-catalog-scheduler-execution", "status": "blocked-no-authorized-zos-evidence", "evidence": {"jes_conversion_listing": False, "spool_capture": False, "catalog_before_after": False, "scheduler_run_history": False, "signed_equivalence": False}},
    ]
    return seal({
        "schema_version": SCHEMA_VERSION,
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": "carddemo-jcl-v0.38",
        "bindings": {
            "graph_content_sha256": graph["content_sha256"],
            "compatibility_ledger_sha256": ledger["content_sha256"],
            "manifest_sha256": manifest["content_sha256"],
            "conformance_sha256": conformance["content_sha256"],
        },
        "inventory": inventory,
        "qualification_gates": gates,
        "required_native_evidence": [
            "exact submitted JCL and JES2/JES3 conversion listing",
            "resolved procedures, includes, symbolics, overrides, and installation defaults",
            "load-library, program, utility, and exit identities",
            "catalog and SMS before/after state for every DD allocation",
            "step return codes, abends, bypass decisions, spool outputs, and operator actions",
            "scheduler dependencies, calendars, resources, rerun and restart history",
            "RACF submitter, surrogate authority, and execution identity",
            "independently signed differential equivalence receipt",
        ],
        "qualification_mechanism_ready": True,
        "development_ready": True,
        "native_jcl_qualified": False,
        "jes_qualified": False,
        "scheduler_qualified": False,
        "runtime_equivalent": False,
        "restart_equivalent": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can inventory and fail-closed qualify a bounded static JCL subset without claiming JES, catalog, scheduler, restart, or z/OS runtime equivalence.",
    })


def validate_jcl_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_jcl_qualification(project_root)
    payload = dict(payload or _load(project_root / "readiness/jcl/qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("jcl-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("jcl-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("jcl-qualification-drift")
    gates = [item.get("gate") for item in payload.get("qualification_gates", []) if isinstance(item, dict)]
    if len(gates) != 10 or len(set(gates)) != 10:
        errors.append("jcl-qualification-gates-incomplete")
    false_claims = (
        "native_jcl_qualified", "jes_qualified", "scheduler_qualified", "runtime_equivalent",
        "restart_equivalent", "mainframe_equivalent", "production_ready",
    )
    if any(payload.get(name) is not False for name in false_claims):
        errors.append("jcl-qualification-overclaims-readiness")
    return sorted(set(errors))


def build_artifacts(project_root: Path, output_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    conformance = build_jcl_conformance(project_root)
    ledger = build_jcl_ledger(graph)
    qualification = build_jcl_qualification(project_root)
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
    parser = argparse.ArgumentParser(description="LIGHTYEAR JCL qualification hardening")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    output = (args.output_root or root / "readiness/jcl").resolve()
    if args.command == "build":
        result = build_artifacts(root, output)
    else:
        expected_conformance = build_jcl_conformance(root)
        expected_ledger = build_jcl_ledger(_load(root / "knowledge/graph.receipt.json"))
        conformance_path = root / "readiness/jcl/conformance.receipt.json"
        ledger_path = root / "readiness/jcl/compatibility-ledger.json"
        conformance = _load(conformance_path) if conformance_path.is_file() else {}
        ledger = _load(ledger_path) if ledger_path.is_file() else {}
        errors = (
            validate_jcl_conformance(root, conformance)
            + validate_jcl_ledger(ledger)
            + validate_jcl_qualification(root)
        )
        if conformance != expected_conformance:
            errors.append("jcl-conformance-drift")
        if ledger != expected_ledger:
            errors.append("jcl-ledger-drift")
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
