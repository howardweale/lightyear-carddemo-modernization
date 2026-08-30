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
QUALIFICATION_TYPE = "lightyear-pli-qualification"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def build_pli_ledger(graph_receipt: Mapping[str, Any]) -> dict[str, Any]:
    specs = (
        ("program-and-internal-procedure", "exact", "bounded-contract", ["positive-program-and-procedure-cases"]),
        ("scalar-and-structure-declarations", "normalized-equivalent", "governed-normalization", ["layout-and-level-vectors"]),
        ("fixed-binary-representation", "policy-decision-required", "unresolved", ["compiler-options-and-native-byte-layout"]),
        ("fixed-decimal-arithmetic", "normalized-equivalent", "governed-normalization", ["scale-sign-rounding-and-overflow-vectors"]),
        ("picture-and-complex-arithmetic", "unsupported", "excluded-from-claim-scope", ["expanded-parser-and-native-baseline"]),
        ("character-fixed-and-varying", "normalized-equivalent", "governed-normalization", ["length-padding-truncation-and-varying-prefix-tests"]),
        ("arrays-and-dimensions", "unsupported", "excluded-from-claim-scope", ["array-bounds-layout-and-subscript-qualification"]),
        ("based-controlled-and-pointer-storage", "unsupported", "excluded-from-claim-scope", ["storage-lifetime-aliasing-and-pointer-baseline"]),
        ("include-resolution", "policy-decision-required", "unresolved", ["compiler-search-order-and-complete-include-closure"]),
        ("preprocessor-macros", "unsupported", "excluded-from-claim-scope", ["IBM-preprocessor-expansion-and-options"]),
        ("static-call-and-options-cobol", "normalized-equivalent", "governed-normalization", ["parameter-layout-entry-and-linkage-tests"]),
        ("dynamic-and-generic-entry-resolution", "unsupported", "excluded-from-claim-scope", ["runtime-target-and-generic-resolution-baseline"]),
        ("conditions-and-on-units", "policy-decision-required", "unresolved", ["condition-prefix-reversion-and-runtime-tests"]),
        ("sequential-file-io", "policy-decision-required", "unresolved", ["record-format-file-status-and-native-io-capture"]),
        ("embedded-db2-sql", "policy-decision-required", "unresolved", ["precompile-package-sqlcode-and-MS-35.1-evidence"]),
        ("exec-cics", "unsupported", "excluded-from-claim-scope", ["MS-39-CICS-qualification"]),
        ("ims-cbltdli", "unsupported", "excluded-from-claim-scope", ["MS-40-IMS-qualification"]),
        ("source-case-comments-and-continuation", "normalized-equivalent", "governed-normalization", ["mutation-conformance-cases"]),
        ("candidate-java-type-mapping", "lossy", "accepted-only-in-bounded-development-proof", ["compatibility-ledger-and-differential-vectors"]),
        ("ibm-compiler-and-language-environment", "unsupported", "excluded-from-claim-scope", ["compiler-listing-binder-map-load-module-and-zos-capture"]),
    )
    entries = [{
        "item_id": f"pli:{scope}",
        "scope": scope,
        "source_semantics": {"language": "IBM Enterprise PL/I", "claim": "bounded-synthetic-and-reference-evidence"},
        "target_semantics": {"contract": QUALIFICATION_TYPE},
        "classification": classification,
        "rationale": "Each PL/I behavior is governed independently; synthetic parsing and a local candidate cannot establish IBM compiler or z/OS runtime equivalence.",
        "evidence_required": evidence,
        "decision": decision,
    } for scope, classification, decision, evidence in specs]
    statistics = dict(Counter(item["classification"] for item in entries))
    for name in COMPATIBILITY_CLASSES:
        statistics.setdefault(name, 0)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "ledger_type": "lightyear-pli-compatibility-ledger",
        "graph_content_sha256": graph_receipt["content_sha256"],
        "classifications": list(COMPATIBILITY_CLASSES),
        "entries": entries,
        "statistics": statistics,
        "qualification_blocked": True,
        "mainframe_equivalent": False,
        "production_ready": False,
    })


def validate_pli_ledger(ledger: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("ledger_type") != "lightyear-pli-compatibility-ledger":
        errors.append("pli-ledger-identity-invalid")
    if ledger.get("content_sha256") != content_hash(ledger):
        errors.append("pli-ledger-content-hash-invalid")
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("pli-ledger-classifications-invalid")
    entries = [item for item in ledger.get("entries", []) if isinstance(item, dict)]
    if len(entries) != 20 or len({item.get("item_id") for item in entries}) != len(entries):
        errors.append("pli-ledger-entry-set-invalid")
    if any(item.get("classification") not in COMPATIBILITY_CLASSES for item in entries):
        errors.append("pli-ledger-classification-invalid")
    if any(item.get("decision") != "unresolved" for item in entries if item.get("classification") == "policy-decision-required"):
        errors.append("pli-ledger-policy-auto-accepted")
    if any(item.get("decision") != "excluded-from-claim-scope" for item in entries if item.get("classification") == "unsupported"):
        errors.append("pli-ledger-unsupported-not-excluded")
    expected = Counter(item.get("classification") for item in entries)
    if any(ledger.get("statistics", {}).get(name) != expected.get(name, 0) for name in COMPATIBILITY_CLASSES):
        errors.append("pli-ledger-statistics-invalid")
    if ledger.get("qualification_blocked") is not True:
        errors.append("pli-ledger-qualification-gate-invalid")
    if ledger.get("mainframe_equivalent") is not False or ledger.get("production_ready") is not False:
        errors.append("pli-ledger-overclaims-readiness")
    return sorted(set(errors))


def build_pli_qualification(project_root: Path) -> dict[str, Any]:
    graph = _load(project_root / "knowledge/graph.receipt.json")
    manifest = _load(project_root / "extensions/pli/conformance/corpus/manifest.json")
    matrix = _load(project_root / "extensions/pli/conformance/support-matrix.json")
    coverage = _load(project_root / "extensions/pli/conformance/coverage.receipt.json")
    development = _load(project_root / "extensions/pli/modernization/development.receipt.json")
    build = _load(project_root / "extensions/pli/attestation/build.receipt.json")
    ledger = build_pli_ledger(graph)
    cases = manifest["cases"]
    classifications = Counter(item["classification"] for item in cases)
    source = project_root / "extensions/pli/reference/ACCTPL1.pli"
    includes = sorted((project_root / "extensions/pli/reference").glob("*.inc"))
    inventory = {
        "reference_programs": 1,
        "reference_source_lines": len(source.read_text(encoding="utf-8").splitlines()),
        "reference_includes": len(includes),
        "corpus_cases": len(cases),
        "positive_cases": classifications["positive"],
        "mutation_cases": classifications["mutation"],
        "targeted_boundary_cases": classifications["boundary"],
        "blocked_cases": sum(item["expected_status"] == "blocked" for item in cases),
        "supported_construct_categories": len(matrix["constructs"]),
        "explicitly_unsupported_categories": len(matrix["explicitly_unsupported"]),
        "customer_source": False,
    }
    gates = [
        {"gate": "corpus-and-provenance", "status": "passed-bounded-synthetic", "evidence": inventory},
        {"gate": "lexical-and-statement-parsing", "status": "passed-supported-subset", "evidence": {"coverage_sha256": coverage["content_sha256"], "native_parser": False}},
        {"gate": "declarations-layout-and-arithmetic", "status": "passed-bounded-development", "evidence": {"fixed_decimal": True, "fixed_binary_native_layout": False, "based_storage": False}},
        {"gate": "control-flow-conditions-and-procedures", "status": "passed-static-subset", "evidence": {"internal_procedure": True, "on_condition_discovery": True, "runtime_condition_semantics": False}},
        {"gate": "include-and-preprocessor-closure", "status": "policy-decision-required", "evidence": {"include_fixture_count": len(includes), "macro_expansion_supported": False}},
        {"gate": "mixed-language-call-linkage", "status": "passed-bounded-development", "evidence": {"pli_to_cobol": True, "dynamic_calls": False}},
        {"gate": "db2-cics-ims-and-file-boundaries", "status": "excluded-separate-qualification", "evidence": {"db2_milestone": "MS-35.1", "cics_milestone": "MS-39", "ims_milestone": "MS-40", "native_file_io": False}},
        {"gate": "candidate-differential-and-mutations", "status": "passed-local-development", "evidence": {"development_receipt_sha256": development["content_sha256"], "mutation_cases": inventory["mutation_cases"]}},
        {"gate": "reproducible-candidate-build", "status": "passed-candidate-only", "evidence": {"build_receipt_sha256": build["content_sha256"], "original_pli_compiled": False}},
        {"gate": "ibm-compile-link-execute-and-equivalence", "status": "blocked-no-authorized-zos-evidence", "evidence": {"compiler_listing": False, "binder_map": False, "load_module": False, "execution_capture": False, "signed_equivalence": False}},
    ]
    return seal({
        "schema_version": SCHEMA_VERSION,
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": "carddemo-pli-v0.37",
        "bindings": {"graph_content_sha256": graph["content_sha256"], "compatibility_ledger_sha256": ledger["content_sha256"], "manifest_sha256": manifest["content_sha256"], "support_matrix_sha256": matrix["content_sha256"]},
        "inventory": inventory,
        "qualification_gates": gates,
        "required_native_evidence": ["IBM Enterprise PL/I compiler listing and exact options", "preprocessor expansion and include-resolution listing", "binder map and load-module identity", "Language Environment options and condition behavior", "authorized z/OS inputs, outputs, SQL/CICS/IMS effects and execution trace", "independently signed differential equivalence receipt"],
        "qualification_mechanism_ready": True,
        "development_ready": True,
        "enterprise_pli_qualified": False,
        "native_compiler_qualified": False,
        "runtime_equivalent": False,
        "mainframe_equivalent": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can qualify a bounded PL/I supported subset and mixed PL/I-COBOL-Db2 development cell without claiming general Enterprise PL/I or z/OS equivalence.",
    })


def validate_pli_qualification(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_pli_qualification(project_root)
    payload = dict(payload or _load(project_root / "readiness/pli/qualification.json"))
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("pli-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("pli-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("pli-qualification-drift")
    gates = [item.get("gate") for item in payload.get("qualification_gates", []) if isinstance(item, dict)]
    if len(gates) != 10 or len(set(gates)) != 10:
        errors.append("pli-qualification-gates-incomplete")
    false_claims = ("enterprise_pli_qualified", "native_compiler_qualified", "runtime_equivalent", "mainframe_equivalent", "production_ready")
    if any(payload.get(name) is not False for name in false_claims):
        errors.append("pli-qualification-overclaims-readiness")
    return sorted(set(errors))


def build_artifacts(project_root: Path, output_root: Path) -> dict[str, Any]:
    ledger = build_pli_ledger(_load(project_root / "knowledge/graph.receipt.json"))
    qualification = build_pli_qualification(project_root)
    write_json(output_root / "compatibility-ledger.json", ledger)
    write_json(output_root / "qualification.json", qualification)
    return {"status": "passed", "ledger_sha256": ledger["content_sha256"], "qualification_sha256": qualification["content_sha256"], "mainframe_equivalent": False, "production_ready": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LIGHTYEAR PL/I qualification hardening")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    output = (args.output_root or root / "readiness/pli").resolve()
    if args.command == "build":
        result = build_artifacts(root, output)
    else:
        expected = build_pli_ledger(_load(root / "knowledge/graph.receipt.json"))
        ledger_path = root / "readiness/pli/compatibility-ledger.json"
        ledger = _load(ledger_path) if ledger_path.is_file() else {}
        errors = validate_pli_ledger(ledger) + validate_pli_qualification(root)
        if ledger != expected:
            errors.append("pli-ledger-drift")
        result = {"status": "passed" if not errors else "failed", "errors": sorted(set(errors)), "mainframe_equivalent": False, "production_ready": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
