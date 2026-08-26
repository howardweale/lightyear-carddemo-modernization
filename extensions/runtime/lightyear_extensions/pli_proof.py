from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import source_hashes, write_json

from .contracts import ExtensionContractError, canonical_hash


WORKLOAD_ID = "workload:carddemo-pli-auth-risk"
EXPECTED_CHECKS = {
    "curated_behavior_contract",
    "db2_lookup_contract",
    "differential_behavior_match",
    "mixed_language_call_contract",
    "mutation_and_negative_verification",
    "bounded_candidate",
    "typed_static_graph",
    "live_zos_baseline",
}


def behavior_contract() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_type": "lightyear-pli-mixed-behavior-contract",
        "workload_id": WORKLOAD_ID,
        "scope": "ACCTPL1 bounded authorization-risk cell",
        "steps": [
            "READ AUTHIN into AUTHORIZATION_RECORD",
            "SELECT APPROVED_AMT and AUTH_FRAUD into APPROVED_AMOUNT and FRAUD_FLAG from CARDDEMO.AUTHFRDS by TRANSACTION_ID",
            "CALC_RISK: fraud Y gives 100.00; otherwise DIVIDE(amount,100,5,2)",
            "CALL CBACT04C using OPTIONS(COBOL) and EXTERNAL_PARMS",
            "WRITE AUTHORIZATION_RECORD to AUTHOUT",
        ],
        "record_contract": {
            "card_number": {"type": "CHAR", "length": 16},
            "transaction_id": {"type": "CHAR", "logical_length": 15, "pli_length": 16, "padding": "right-space"},
            "authorization_code": {"type": "CHAR", "length": 6},
            "approved_amount": {"type": "DECIMAL", "precision": 12, "scale": 2},
            "fraud_flag": {"type": "CHAR", "length": 1, "values": ["N", "Y"]},
            "risk_score": {"type": "DECIMAL", "precision": 5, "scale": 2, "rounding": "truncate"},
        },
        "cobol_call": {
            "program": "CBACT04C",
            "calling_convention": "OPTIONS(COBOL)",
            "parameter": "EXTERNAL_PARMS",
            "fields": {"PARM_LENGTH": 10, "PARM_DATE": "2026-08-20"},
            "boundary": "Invocation contract only; CBACT04C file processing remains independently verified by the INTCALC cell.",
        },
        "truth_boundary": "Local executable development evidence; no compiled or executed PL/I observation on z/OS.",
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def fixtures() -> dict[str, Any]:
    base = {
        "card_number": "4000000000000001",
        "transaction_id": "TX0000000000001",
        "authorization_code": "Z99999",
        "approved_amount": "999.99",
        "fraud_flag": "Y",
    }
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "fixture_type": "lightyear-pli-mixed-boundary-fixtures",
        "workload_id": WORKLOAD_ID,
        "authfrds": {
            "TX0000000000001": {"approved_amount": "125.50", "fraud_flag": "N"},
            "TX0000000000002": {"approved_amount": "0.00", "fraud_flag": "Y"},
        },
        "cases": [
            {"id": "db2-overwrite-non-fraud", "record": base},
            {"id": "db2-overwrite-fraud", "record": {**base, "transaction_id": "TX0000000000002", "approved_amount": "125.50", "fraud_flag": "N"}},
            {"id": "sql-not-found", "record": {**base, "transaction_id": "TX0000000000999"}},
            {"id": "invalid-card-width", "record": {**base, "card_number": "4000"}},
            {"id": "invalid-transaction-width", "record": {**base, "transaction_id": "TOO-LONG-TRANSACTION"}},
            {"id": "invalid-fraud-flag", "record": {**base, "fraud_flag": "?"}},
            {"id": "invalid-decimal", "record": {**base, "approved_amount": "not-a-decimal"}},
        ],
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def build_proof(project_root: Path, graph: Mapping[str, Any], fragment: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    contract = behavior_contract()
    fixture_set = fixtures()
    candidate = _candidate_module(project_root)
    results = []
    for case in fixture_set["cases"]:
        expected = _oracle(case["record"], fixture_set["authfrds"])
        actual = candidate.execute(case["record"], fixture_set["authfrds"])
        results.append({
            "case_id": case["id"],
            "equivalent": expected == actual,
            "expected_sha256": canonical_hash(expected),
            "actual_sha256": canonical_hash(actual),
        })
    mutations = {
        "fraud-score": {"fraud_score": "99.99"},
        "risk-divisor": {"divisor": "10"},
        "risk-rounding": {"rounding": ROUND_UP},
        "skip-db-overwrite": {"overwrite_db_fields": False},
        "wrong-cobol-program": {"cobol_program": "CBACT01C"},
        "wrong-parm-length": {"parm_length": 8},
        "wrong-parm-date": {"parm_date": "2026-08-21"},
        "call-on-error": {"call_on_error": True},
        "write-on-error": {"write_on_error": True},
    }
    mutation_results = []
    for name, policy in mutations.items():
        detected = any(
            _oracle(case["record"], fixture_set["authfrds"])
            != candidate.execute(case["record"], fixture_set["authfrds"], policy)
            for case in fixture_set["cases"]
        )
        mutation_results.append({"mutation": name, "detected": detected})
    comparison: dict[str, Any] = {
        "schema_version": "1.0",
        "comparison_type": "lightyear-pli-mixed-differential-comparison",
        "workload_id": WORKLOAD_ID,
        "evidence_class": "local_observed",
        "case_results": results,
        "mutation_results": mutation_results,
        "equivalent": all(item["equivalent"] for item in results),
        "all_mutations_detected": all(item["detected"] for item in mutation_results),
    }
    comparison["content_sha256"] = canonical_hash(comparison)
    checks = {
        "typed_static_graph": _valid_fragment(fragment, graph),
        "curated_behavior_contract": contract["content_sha256"] == canonical_hash(contract, {"content_sha256"}),
        "mixed_language_call_contract": _source_contract(project_root),
        "db2_lookup_contract": "legacy:db2-table:CARDDEMO.AUTHFRDS" in {
            item.get("entity_id") for item in fragment.get("external_references", [])
        },
        "bounded_candidate": hasattr(candidate, "execute"),
        "differential_behavior_match": comparison["equivalent"],
        "mutation_and_negative_verification": comparison["all_mutations_detected"],
        "live_zos_baseline": False,
    }
    bindings = _bindings(project_root, graph, fragment, contract, fixture_set, comparison)
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "receipt_type": "lightyear-pli-mixed-development-proof",
        "workload_id": WORKLOAD_ID,
        "evidence_class": "local_observed",
        "bindings": bindings,
        "checks": checks,
        "development_ready": all(checks[name] for name in EXPECTED_CHECKS - {"live_zos_baseline"}),
        "mainframe_equivalent": False,
        "production_ready": False,
        "status": "passed" if all(checks[name] for name in EXPECTED_CHECKS - {"live_zos_baseline"}) else "failed",
        "unresolved_gaps": [
            "No authorized compiled and executed ACCTPL1 observation exists on z/OS.",
            "No independently signed live PL/I differential comparison exists.",
            "The committed receipt binds Java source; Java compilation and tests are a separate CI control.",
        ],
    }
    receipt["content_sha256"] = canonical_hash(receipt)
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "behavior-contract.json", contract)
    write_json(output_root / "fixtures.json", fixture_set)
    write_json(output_root / "comparison.json", comparison)
    write_json(output_root / "development.receipt.json", receipt)
    return receipt


def validate_development_receipt(
    receipt: Mapping[str, Any], project_root: Path, graph: Mapping[str, Any], fragment: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema_version") != "1.0" or receipt.get("receipt_type") != "lightyear-pli-mixed-development-proof":
        errors.append("PL/I development receipt identity is invalid")
    if receipt.get("content_sha256") != canonical_hash(receipt, {"content_sha256"}):
        errors.append("PL/I development receipt content_sha256 is invalid")
    checks = receipt.get("checks", {})
    if set(checks) != EXPECTED_CHECKS:
        errors.append("PL/I development receipt has an unexpected check set")
    elif checks.get("live_zos_baseline") is not False or not all(
        checks.get(name) is True for name in EXPECTED_CHECKS - {"live_zos_baseline"}
    ):
        errors.append("PL/I development checks are incomplete or overstate live evidence")
    if receipt.get("development_ready") is not True or receipt.get("mainframe_equivalent") is not False:
        errors.append("PL/I development receipt readiness boundary is invalid")
    if receipt.get("production_ready") is not False or receipt.get("status") != "passed":
        errors.append("PL/I development receipt status boundary is invalid")
    contract = behavior_contract()
    fixture_set = fixtures()
    comparison_path = project_root / "extensions/pli/modernization/comparison.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8")) if comparison_path.exists() else {}
    if (
        comparison.get("content_sha256") != canonical_hash(comparison, {"content_sha256"})
        or comparison.get("equivalent") is not True
        or comparison.get("all_mutations_detected") is not True
    ):
        errors.append("PL/I development comparison is invalid")
    canonical_root = project_root / "extensions/pli/modernization"
    for name, generated in (("behavior-contract.json", contract), ("fixtures.json", fixture_set)):
        path = canonical_root / name
        if not path.exists() or json.loads(path.read_text(encoding="utf-8")) != generated:
            errors.append(f"PL/I development artifact is stale: {name}")
    expected = _bindings(project_root, graph, fragment, contract, fixture_set, comparison)
    if receipt.get("bindings") != expected:
        errors.append("PL/I development receipt bindings are stale")
    return errors


def _oracle(record: Mapping[str, Any], authfrds: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    trace: list[str] = []
    if (
        not isinstance(record.get("card_number"), str) or len(record["card_number"]) != 16
        or not isinstance(record.get("transaction_id"), str) or len(record["transaction_id"]) != 15
        or not isinstance(record.get("authorization_code"), str) or len(record["authorization_code"]) != 6
        or record.get("fraud_flag") not in {"N", "Y"}
        or not _oracle_decimal_12_2(record.get("approved_amount"))
    ):
        return {"status": "INPUT_ERROR", "error": "record-contract", "authorization_record": None, "risk_score": None, "cobol_calls": [], "trace": []}
    trace.extend(("READ_AUTHIN", "SELECT_AUTHFRDS"))
    transaction_id = record["transaction_id"]
    selected = authfrds.get(transaction_id)
    if selected is None:
        return {"status": "SQL_NOT_FOUND", "error": transaction_id, "authorization_record": None, "risk_score": None, "cobol_calls": [], "trace": trace}
    amount = Decimal(selected["approved_amount"])
    flag = selected["fraud_flag"]
    trace.append("CALC_RISK")
    score = Decimal("100.00") if flag == "Y" else (amount / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    call = {"program": "CBACT04C", "calling_convention": "OPTIONS(COBOL)", "parm_length": 10, "parm_date": "2026-08-20"}
    trace.extend(("CALL_CBACT04C", "WRITE_AUTHOUT"))
    return {
        "status": "NORMAL", "error": None,
        "authorization_record": {
            "card_number": record["card_number"], "transaction_id": transaction_id,
            "transaction_id_fixed_16": transaction_id.ljust(16),
            "authorization_code": record["authorization_code"],
            "approved_amount": f"{amount:.2f}", "fraud_flag": flag,
        },
        "risk_score": f"{score:.2f}", "cobol_calls": [call], "trace": trace,
    }


def _candidate_module(project_root: Path) -> Any:
    path = project_root / "factory/benchmarks/pli_authorization_candidate.py"
    spec = importlib.util.spec_from_file_location("lightyear_pli_authorization_candidate", path)
    if not spec or not spec.loader:
        raise ExtensionContractError("Cannot load PL/I modernization candidate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _valid_fragment(fragment: Mapping[str, Any], graph: Mapping[str, Any]) -> bool:
    return bool(
        fragment.get("content_sha256") == canonical_hash(fragment, {"content_sha256"})
        and fragment.get("base_graph", {}).get("content_sha256") == graph.get("content_sha256")
    )


def _source_contract(project_root: Path) -> bool:
    text = (project_root / "extensions/pli/reference/ACCTPL1.pli").read_text(encoding="utf-8")
    required = ["ENTRY OPTIONS(COBOL)", "CALL CBACT04C(EXTERNAL_PARMS)", "DIVIDE(AMOUNT, 100, 5, 2)", "PARM_LENGTH FIXED BINARY(15) INIT(10)"]
    return all(item in text for item in required)


def _bindings(
    project_root: Path, graph: Mapping[str, Any], fragment: Mapping[str, Any],
    contract: Mapping[str, Any], fixture_set: Mapping[str, Any], comparison: Mapping[str, Any],
) -> dict[str, Any]:
    paths = {
        "pli_source_sha256": project_root / "extensions/pli/reference/ACCTPL1.pli",
        "pli_include_sha256": project_root / "extensions/pli/reference/AUTHCOM.inc",
        "python_candidate_sha256": project_root / "factory/benchmarks/pli_authorization_candidate.py",
        "java_candidate_sha256": project_root / "candidate-java/src/main/java/ai/lightyear/carddemo/service/MixedPliAuthorizationService.java",
        "java_test_sha256": project_root / "candidate-java/src/test/java/ai/lightyear/carddemo/service/MixedPliAuthorizationServiceTest.java",
        "data_fixture_source_sha256": project_root / "data-modernization/fixtures/authfrds.fixtures.json",
    }
    return {
        "canonical_graph_sha256": graph.get("content_sha256"),
        "pli_fragment_sha256": fragment.get("content_sha256"),
        "behavior_contract_sha256": contract.get("content_sha256"),
        "fixtures_sha256": fixture_set.get("content_sha256"),
        "comparison_sha256": comparison.get("content_sha256"),
        **{name: source_hashes(path)[0] if path.exists() else None for name, path in paths.items()},
    }


def _oracle_decimal_12_2(value: Any) -> bool:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return number.is_finite() and number.as_tuple().exponent >= -2 and len(number.as_tuple().digits) <= 12
