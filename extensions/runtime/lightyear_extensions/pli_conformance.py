from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import source_hashes

from .contracts import ExtensionContractError, canonical_hash
from .pli import PACK_ID, PACK_VERSION
from .pli_frontend import parse_pli_source


RECEIPT_TYPE = "lightyear-pli-discovery-conformance"
EVIDENCE_CLASS = "synthetic-static-conformance"


def _load_content_addressed(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("content_sha256") != canonical_hash(payload, {"content_sha256"}):
        raise ExtensionContractError(f"{label} content_sha256 is invalid: {path}")
    return payload


def _case_result(case: Mapping[str, Any], parsed: Mapping[str, Any]) -> dict[str, Any]:
    actual_constructs = Counter(item["kind"] for item in parsed["constructs"])
    actual_diagnostics = [item["code"] for item in parsed["diagnostics"]]
    expected_constructs = case.get("expected_constructs", {})
    expected_diagnostics = sorted(case.get("expected_diagnostics", []))
    expectations = {
        "status": parsed["status"] == case["expected_status"],
        "constructs": all(actual_constructs[name] >= count for name, count in expected_constructs.items()),
        "diagnostics": sorted(actual_diagnostics) == expected_diagnostics,
    }
    return {
        "case_id": case["id"],
        "path": case["path"],
        "classification": case["classification"],
        "expected_status": case["expected_status"],
        "actual_status": parsed["status"],
        "constructs": dict(sorted(actual_constructs.items())),
        "recognized": copy.deepcopy(parsed["constructs"]),
        "references": copy.deepcopy(parsed["references"]),
        "diagnostics": copy.deepcopy(parsed["diagnostics"]),
        "expectations": expectations,
        "passed": all(expectations.values()),
    }


def build_conformance_lab(
    graph: Mapping[str, Any],
    corpus_root: Path,
    manifest_path: Path,
    support_matrix_path: Path,
    repository_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repository_root = repository_root.resolve()
    corpus_root = corpus_root.resolve()
    if repository_root not in corpus_root.parents:
        raise ExtensionContractError("PL/I conformance corpus must be inside the repository root")
    manifest = _load_content_addressed(manifest_path, "PL/I corpus manifest")
    support_matrix = _load_content_addressed(support_matrix_path, "PL/I support matrix")
    if manifest.get("corpus_id") != "lightyear-pli-synthetic-conformance-v1":
        raise ExtensionContractError("PL/I corpus identity is invalid")
    cases = manifest.get("cases", [])
    if len(cases) < 20:
        raise ExtensionContractError("PL/I conformance corpus requires at least 20 cases")
    case_ids = [case.get("id") for case in cases]
    case_paths = [case.get("path") for case in cases]
    if len(case_ids) != len(set(case_ids)) or len(case_paths) != len(set(case_paths)):
        raise ExtensionContractError("PL/I conformance case ids and paths must be unique")
    if case_ids != sorted(case_ids):
        raise ExtensionContractError("PL/I conformance cases must be sorted by id")
    actual_paths = {
        path.relative_to(corpus_root).as_posix()
        for path in corpus_root.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".pli", ".pl1", ".inc"}
    }
    declared_paths = set(case_paths)
    if actual_paths != declared_paths:
        missing = sorted(declared_paths - actual_paths)
        undeclared = sorted(actual_paths - declared_paths)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if undeclared:
            details.append(f"undeclared: {', '.join(undeclared)}")
        raise ExtensionContractError(
            "PL/I conformance manifest must declare the exact source set (" + "; ".join(details) + ")"
        )

    include_names = {
        path.stem.upper() for path in corpus_root.rglob("*.inc") if path.is_file()
    }
    results: list[dict[str, Any]] = []
    source_bindings: list[dict[str, Any]] = []
    all_constructs: Counter[str] = Counter()
    all_diagnostics: Counter[str] = Counter()
    for case in cases:
        relative = str(case["path"])
        source = (corpus_root / relative).resolve()
        if corpus_root not in source.parents or not source.is_file():
            raise ExtensionContractError(f"PL/I conformance source is absent or unsafe: {relative}")
        logical_sha, transport_sha = source_hashes(source)
        parsed = parse_pli_source(
            source.read_text(encoding="utf-8", errors="strict"),
            source.relative_to(repository_root).as_posix(),
            include_names=include_names,
        )
        result = _case_result(case, parsed)
        results.append(result)
        all_constructs.update(result["constructs"])
        all_diagnostics.update(item["code"] for item in result["diagnostics"])
        source_bindings.append({
            "case_id": case["id"],
            "path": source.relative_to(repository_root).as_posix(),
            "logical_sha256": logical_sha,
            "transport_sha256": transport_sha,
        })

    golden: dict[str, Any] = {
        "schema_version": "1.0",
        "result_type": "lightyear-pli-conformance-golden",
        "corpus_id": manifest["corpus_id"],
        "parser": {"id": PACK_ID, "version": PACK_VERSION, "frontend": "tokenized-statement-parser"},
        "results": results,
        "source_bindings": source_bindings,
    }
    golden["content_sha256"] = canonical_hash(golden)

    positive = [item for item in results if item["expected_status"] == "passed"]
    blockers = [item for item in results if item["expected_status"] == "blocked"]
    mutation_cases = [item for item in results if item["classification"] == "mutation"]
    supported_ids = {item["id"] for item in support_matrix.get("constructs", []) if item["status"] == "supported"}
    exercised_ids = set(all_constructs)
    unresolved = [
        {
            "case_id": item["case_id"],
            "path": item["path"],
            "code": diagnostic["code"],
            "line": diagnostic["line"],
            "column": diagnostic["column"],
        }
        for item in results
        for diagnostic in item["diagnostics"]
    ]
    checks = {
        "exact_manifest_source_set": actual_paths == declared_paths,
        "corpus_minimum_20_cases": len(results) >= 20,
        "all_case_expectations_match": all(item["passed"] for item in results),
        "positive_cases_parse": bool(positive) and all(item["actual_status"] == "passed" for item in positive),
        "unsupported_cases_are_explicit_blockers": bool(blockers) and all(
            item["actual_status"] == "blocked" and item["diagnostics"] for item in blockers
        ),
        "mutation_cases_resist_false_facts": len(mutation_cases) >= 5 and all(item["passed"] for item in mutation_cases),
        "supported_matrix_is_exercised": supported_ids.issubset(exercised_ids),
        "source_locations_are_present": all(
            all(
                "line" in located and "column" in located
                for located in [*item["recognized"], *item["references"], *item["diagnostics"]]
            )
            for item in results
        ),
    }
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "receipt_type": RECEIPT_TYPE,
        "evidence_class": EVIDENCE_CLASS,
        "status": "passed" if all(checks.values()) else "failed",
        "language_pack": {"id": PACK_ID, "version": PACK_VERSION},
        "bindings": {
            "canonical_graph_sha256": graph["content_sha256"],
            "corpus_manifest_sha256": manifest["content_sha256"],
            "support_matrix_sha256": support_matrix["content_sha256"],
            "golden_results_sha256": golden["content_sha256"],
        },
        "corpus": {
            "id": manifest["corpus_id"],
            "case_count": len(results),
            "program_case_count": sum(not item["path"].casefold().endswith(".inc") for item in results),
            "include_case_count": sum(item["path"].casefold().endswith(".inc") for item in results),
            "positive_case_count": len(positive),
            "blocked_case_count": len(blockers),
            "mutation_case_count": len(mutation_cases),
            "synthetic": True,
            "customer_source": False,
        },
        "coverage": {
            "recognized_constructs": dict(sorted(all_constructs.items())),
            "explicit_gap_codes": dict(sorted(all_diagnostics.items())),
            "unresolved_constructs": unresolved,
            "unsupported_syntax": list(support_matrix.get("explicitly_unsupported", [])),
            "located_construct_count": sum(len(item["recognized"]) for item in results),
            "supported_matrix_construct_count": len(supported_ids),
            "exercised_supported_construct_count": len(supported_ids & exercised_ids),
            "parser_confidence": "supported-subset-observed",
            "provenance": "synthetic-conformance-corpus",
        },
        "checks": checks,
        "claim_boundary": {
            "static_discovery_only": True,
            "runtime_executed": False,
            "ibm_compiler_semantics_proven": False,
            "arbitrary_enterprise_pli_supported": False,
            "mainframe_equivalent": False,
            "production_ready": False,
        },
        "limitations": [
            "The corpus is synthetic and does not represent a customer PL/I estate.",
            "The parser implements a measured supported subset, not IBM Enterprise PL/I compiler semantics.",
            "Static discovery and mutation resistance do not establish runtime equivalence.",
        ],
        "production_ready": False,
    }
    receipt["content_sha256"] = canonical_hash(receipt)
    return golden, receipt


def validate_conformance_receipt(
    receipt: Mapping[str, Any],
    golden: Mapping[str, Any],
    graph: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if receipt.get("receipt_type") != RECEIPT_TYPE:
        errors.append("PL/I conformance receipt_type is invalid")
    if receipt.get("evidence_class") != EVIDENCE_CLASS:
        errors.append("PL/I conformance evidence_class is invalid")
    if receipt.get("language_pack") != {"id": PACK_ID, "version": PACK_VERSION}:
        errors.append("PL/I conformance language-pack identity is invalid")
    if receipt.get("content_sha256") != canonical_hash(receipt, {"content_sha256"}):
        errors.append("PL/I conformance content_sha256 is invalid")
    if golden.get("content_sha256") != canonical_hash(golden, {"content_sha256"}):
        errors.append("PL/I golden results content_sha256 is invalid")
    bindings = receipt.get("bindings", {})
    if bindings.get("canonical_graph_sha256") != graph.get("content_sha256"):
        errors.append("PL/I conformance targets a different canonical graph")
    if bindings.get("golden_results_sha256") != golden.get("content_sha256"):
        errors.append("PL/I conformance does not bind the supplied golden results")
    expected_checks = {
        "exact_manifest_source_set",
        "corpus_minimum_20_cases",
        "all_case_expectations_match",
        "positive_cases_parse",
        "unsupported_cases_are_explicit_blockers",
        "mutation_cases_resist_false_facts",
        "supported_matrix_is_exercised",
        "source_locations_are_present",
    }
    checks = receipt.get("checks", {})
    if receipt.get("status") != "passed" or set(checks) != expected_checks or not all(checks.values()):
        errors.append("PL/I conformance checks did not all pass")
    corpus = receipt.get("corpus", {})
    if not (
        corpus.get("case_count", 0) >= 20
        and corpus.get("program_case_count", 0) >= 1
        and corpus.get("include_case_count", 0) >= 1
        and corpus.get("positive_case_count", 0) >= 1
        and corpus.get("blocked_case_count", 0) >= 1
        and corpus.get("mutation_case_count", 0) >= 5
        and corpus.get("synthetic") is True
        and corpus.get("customer_source") is False
    ):
        errors.append("PL/I conformance corpus breadth or provenance is invalid")
    results = golden.get("results", [])
    if (
        golden.get("result_type") != "lightyear-pli-conformance-golden"
        or golden.get("parser", {}).get("version") != PACK_VERSION
        or len(results) != corpus.get("case_count")
        or len(golden.get("source_bindings", [])) != len(results)
        or not all(item.get("passed") is True for item in results)
        or not all(
            all(
                "line" in located and "column" in located
                for located in [*item.get("recognized", []), *item.get("references", []), *item.get("diagnostics", [])]
            )
            for item in results
        )
    ):
        errors.append("PL/I golden results are incomplete or inconsistent")
    coverage = receipt.get("coverage", {})
    unresolved = coverage.get("unresolved_constructs", [])
    if not (
        coverage.get("supported_matrix_construct_count", 0) >= 20
        and coverage.get("exercised_supported_construct_count")
        == coverage.get("supported_matrix_construct_count")
        and coverage.get("located_construct_count", 0) >= 1
        and coverage.get("parser_confidence") == "supported-subset-observed"
        and coverage.get("provenance") == "synthetic-conformance-corpus"
        and coverage.get("unsupported_syntax")
        and all(
            set(item) == {"case_id", "path", "code", "line", "column"}
            and item["line"] >= 1 and item["column"] >= 1
            for item in unresolved
        )
    ):
        errors.append("PL/I conformance coverage detail is invalid")
    boundary = receipt.get("claim_boundary", {})
    if boundary != {
        "static_discovery_only": True,
        "runtime_executed": False,
        "ibm_compiler_semantics_proven": False,
        "arbitrary_enterprise_pli_supported": False,
        "mainframe_equivalent": False,
        "production_ready": False,
    }:
        errors.append("PL/I conformance overstates runtime or mainframe equivalence")
    if receipt.get("production_ready") is not False:
        errors.append("PL/I conformance cannot be production ready")
    return errors
