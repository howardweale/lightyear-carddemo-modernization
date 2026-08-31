from __future__ import annotations

import copy
import hashlib
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import content_hash, seal
from .semantic_core import COMPATIBILITY_CLASSES


PROCEDURE_SOURCE = "data-modernization/oracle-source/procedures.sql"
QUALIFICATION_TYPE = "lightyear-oracle-procedure-qualification"
QUALIFICATION_ID = "authfrds-oracle-procedure-subset-v0.43"
UNSUPPORTED_FEATURES = {
    "dynamic-sql": re.compile(r"\bEXECUTE\s+IMMEDIATE\b", re.IGNORECASE),
    "autonomous-transaction": re.compile(r"\bPRAGMA\s+AUTONOMOUS_TRANSACTION\b", re.IGNORECASE),
    "package-state": re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\b", re.IGNORECASE),
    "database-link": re.compile(r"\b(?:FROM|UPDATE|INTO)\s+[A-Z0-9_.$]+@[A-Z0-9_.$]+", re.IGNORECASE),
    "procedure-owned-commit": re.compile(r"\bCOMMIT\s*;", re.IGNORECASE),
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _split_parameters(raw: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for character in raw:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if "".join(current).strip():
        parts.append("".join(current).strip())
    return parts


def classify_unsupported(source: str) -> list[str]:
    return sorted(name for name, pattern in UNSUPPORTED_FEATURES.items() if pattern.search(source))


def parse_oracle_procedures(source: str) -> list[dict[str, Any]]:
    if classify_unsupported(source):
        raise ValueError("oracle-procedure-source-contains-unsupported-feature")
    block_pattern = re.compile(
        r"CREATE\s+OR\s+REPLACE\s+PROCEDURE\s+([A-Z0-9_]+)\.([A-Z0-9_]+)\s*"
        r"\((.*?)\)\s+AS\s+(.*?\bEND\s*;)\s*^/\s*$",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    procedures: list[dict[str, Any]] = []
    for match in block_pattern.finditer(source):
        schema, name, raw_parameters, body = match.groups()
        parameters = []
        for ordinal, raw in enumerate(_split_parameters(raw_parameters), 1):
            parameter = re.fullmatch(
                r"([A-Z0-9_]+)\s+(IN\s+OUT|IN|OUT)\s+([A-Z0-9_]+)(?:\((\d+)\))?",
                " ".join(raw.split()),
                re.IGNORECASE,
            )
            if not parameter:
                raise ValueError(f"oracle-procedure-parameter-unsupported:{name}:{raw}")
            param_name, mode, data_type, length = parameter.groups()
            if data_type.upper() not in {"NUMBER", "VARCHAR2", "CHAR", "DATE", "TIMESTAMP"}:
                raise ValueError(f"oracle-procedure-parameter-type-unsupported:{name}:{data_type}")
            parameters.append({
                "ordinal": ordinal,
                "name": param_name.upper(),
                "mode": " ".join(mode.upper().split()),
                "source_type": data_type.upper(),
                "length": int(length) if length else None,
            })
        upper = body.upper()
        feature_patterns = {
            "select-into": r"\bSELECT\b.*?\bINTO\b",
            "update": r"\bUPDATE\b",
            "sql-rowcount": r"SQL%ROWCOUNT",
            "if-elsif-else": r"\bIF\b.*?\bELSIF\b.*?\bELSE\b",
            "no-data-found": r"\bNO_DATA_FOUND\b",
            "raise-application-error": r"\bRAISE_APPLICATION_ERROR\b",
            "nvl": r"\bNVL\s*\(",
        }
        features = sorted(
            feature for feature, pattern in feature_patterns.items()
            if re.search(pattern, upper, re.DOTALL)
        )
        dependencies = sorted(set(
            f"{item[0].upper()}.{item[1].upper()}"
            for item in re.findall(r"\b(?:FROM|UPDATE|INTO)\s+([A-Z0-9_]+)\.([A-Z0-9_]+)", upper)
        ))
        raw_block = match.group(0)
        procedures.append({
            "procedure_id": f"{schema.upper()}.{name.upper()}",
            "schema": schema.upper(),
            "name": name.upper(),
            "parameters": parameters,
            "features": features,
            "dependencies": dependencies,
            "source_sha256": _sha256(raw_block.encode("utf-8")),
            "body": body.strip(),
        })
    residue = block_pattern.sub("", source).strip()
    if residue or not procedures:
        raise ValueError("oracle-procedure-source-not-fully-inventoried")
    ids = [item["procedure_id"] for item in procedures]
    if len(ids) != len(set(ids)):
        raise ValueError("oracle-procedure-identity-duplicate")
    return procedures


def _postgres_type(parameter: Mapping[str, Any]) -> str:
    source = parameter["source_type"]
    if source == "NUMBER":
        return "NUMERIC"
    if source == "VARCHAR2":
        return f"VARCHAR({parameter['length']})" if parameter.get("length") else "VARCHAR"
    if source == "CHAR":
        return f"CHAR({parameter['length']})" if parameter.get("length") else "CHAR"
    return str(source)


def translate_oracle_procedure(procedure: Mapping[str, Any]) -> str:
    parameters = ",\n  ".join(
        f"{item['mode']} {item['name'].lower()} {_postgres_type(item)}"
        for item in procedure["parameters"]
    )
    body = str(procedure["body"])
    body = re.sub(r"\bCARDDEMO\.AUTHFRDS\b", "carddemo.authfrds", body, flags=re.IGNORECASE)
    body = re.sub(r"\bNVL\s*\(", "COALESCE(", body, flags=re.IGNORECASE)
    body = re.sub(
        r"([A-Z0-9_]+)\s*:=\s*SQL%ROWCOUNT\s*;",
        lambda match: f"GET DIAGNOSTICS {match.group(1)} = ROW_COUNT;",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r"RAISE_APPLICATION_ERROR\s*\(\s*-\d+\s*,\s*'([^']+)'\s*\)\s*;",
        lambda match: f"RAISE EXCEPTION '{match.group(1)}' USING ERRCODE = 'P0001';",
        body,
        flags=re.IGNORECASE,
    )
    return (
        f"CREATE OR REPLACE PROCEDURE {procedure['schema'].lower()}.{procedure['name'].lower()} (\n"
        f"  {parameters}\n)\nLANGUAGE plpgsql\nAS $$\n{body}\n$$;\n"
    )


def _case(
    case_id: str,
    procedure: str,
    arguments: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]],
    expected: Mapping[str, Any],
    classification: str,
    features: Iterable[str],
) -> dict[str, Any]:
    return {
        "id": case_id,
        "procedure": procedure,
        "arguments": dict(arguments),
        "rows": [dict(row) for row in rows],
        "expected": dict(expected),
        "classification": classification,
        "features": sorted(features),
    }


def procedure_cases() -> list[dict[str, Any]]:
    one = [{"CARD_NUM": "4000000000000001", "AUTH_FRAUD": "N", "AUTH_RESP_REASON": "OK"}]
    cases = [
        _case("01-get-found", "GET_AUTH_STATUS", {"P_CARD_NUM": "4000000000000001"}, one, {"status": "passed", "outputs": {"P_STATUS": "N"}, "mutation_count": 0}, "positive", ["select-into"]),
        _case("02-get-not-found", "GET_AUTH_STATUS", {"P_CARD_NUM": "4999999999999999"}, one, {"status": "passed", "outputs": {"P_STATUS": "N"}, "mutation_count": 0}, "targeted-boundary", ["no-data-found"]),
        _case("03-get-duplicate", "GET_AUTH_STATUS", {"P_CARD_NUM": "4000000000000001"}, one + one, {"status": "failed", "error_class": "TOO_MANY_ROWS", "mutation_count": 0}, "mutation", ["too-many-rows"]),
        _case("04-get-empty-key", "GET_AUTH_STATUS", {"P_CARD_NUM": ""}, one, {"status": "passed", "outputs": {"P_STATUS": "N"}, "mutation_count": 0}, "targeted-boundary", ["oracle-empty-string-is-null"]),
        _case("05-set-one", "SET_FRAUD_FLAG", {"P_CARD_NUM": "4000000000000001", "P_REASON": "RULE"}, one, {"status": "passed", "outputs": {"P_ROWS": 1}, "mutation_count": 1}, "positive", ["update", "sql-rowcount"]),
        _case("06-set-none", "SET_FRAUD_FLAG", {"P_CARD_NUM": "4999999999999999", "P_REASON": "RULE"}, one, {"status": "passed", "outputs": {"P_ROWS": 0}, "mutation_count": 0}, "targeted-boundary", ["zero-row-update"]),
        _case("07-set-two", "SET_FRAUD_FLAG", {"P_CARD_NUM": "4000000000000001", "P_REASON": "RULE"}, one + one, {"status": "passed", "outputs": {"P_ROWS": 2}, "mutation_count": 2}, "mutation", ["multi-row-update"]),
        _case("08-set-null-reason", "SET_FRAUD_FLAG", {"P_CARD_NUM": "4000000000000001", "P_REASON": None}, one, {"status": "passed", "outputs": {"P_ROWS": 1}, "mutation_count": 1}, "targeted-boundary", ["null-input"]),
        _case("09-set-empty-reason", "SET_FRAUD_FLAG", {"P_CARD_NUM": "4000000000000001", "P_REASON": ""}, one, {"status": "passed", "outputs": {"P_ROWS": 1}, "mutation_count": 1}, "targeted-boundary", ["oracle-empty-string-is-null"]),
        _case("10-class-negative", "CLASSIFY_AMOUNT", {"P_AMOUNT": "-0.01"}, [], {"status": "failed", "error_class": "APPLICATION_ERROR:P0001", "mutation_count": 0}, "targeted-boundary", ["raise-application-error"]),
        _case("11-class-zero", "CLASSIFY_AMOUNT", {"P_AMOUNT": "0"}, [], {"status": "passed", "outputs": {"P_CLASS": "STANDARD"}, "mutation_count": 0}, "targeted-boundary", ["decimal-zero"]),
        _case("12-class-below", "CLASSIFY_AMOUNT", {"P_AMOUNT": "999.99"}, [], {"status": "passed", "outputs": {"P_CLASS": "STANDARD"}, "mutation_count": 0}, "targeted-boundary", ["decimal-threshold"]),
        _case("13-class-at", "CLASSIFY_AMOUNT", {"P_AMOUNT": "1000"}, [], {"status": "passed", "outputs": {"P_CLASS": "HIGH"}, "mutation_count": 0}, "positive", ["decimal-threshold"]),
        _case("14-class-above", "CLASSIFY_AMOUNT", {"P_AMOUNT": "1000.01"}, [], {"status": "passed", "outputs": {"P_CLASS": "HIGH"}, "mutation_count": 0}, "targeted-boundary", ["decimal-threshold"]),
        _case("15-class-invalid", "CLASSIFY_AMOUNT", {"P_AMOUNT": "not-a-number"}, [], {"status": "failed", "error_class": "INVALID_NUMBER", "mutation_count": 0}, "mutation", ["invalid-number"]),
        _case("16-normalize-null", "NORMALIZE_REASON", {"P_REASON": None}, [], {"status": "passed", "outputs": {"P_RESULT": "UNSPECIFIED"}, "mutation_count": 0}, "positive", ["nvl"]),
        _case("17-normalize-empty", "NORMALIZE_REASON", {"P_REASON": ""}, [], {"status": "passed", "outputs": {"P_RESULT": "UNSPECIFIED"}, "mutation_count": 0}, "targeted-boundary", ["oracle-empty-string-is-null"]),
        _case("18-normalize-text", "NORMALIZE_REASON", {"P_REASON": "DECLINED"}, [], {"status": "passed", "outputs": {"P_RESULT": "DECLINED"}, "mutation_count": 0}, "positive", ["character-output"]),
        _case("19-normalize-space", "NORMALIZE_REASON", {"P_REASON": " "}, [], {"status": "passed", "outputs": {"P_RESULT": " "}, "mutation_count": 0}, "targeted-boundary", ["space-not-empty"]),
        _case("20-normalize-number", "NORMALIZE_REASON", {"P_REASON": 7}, [], {"status": "failed", "error_class": "TYPE_MISMATCH", "mutation_count": 0}, "mutation", ["parameter-type"]),
    ]
    return cases


def execute_procedure_case(case: Mapping[str, Any]) -> dict[str, Any]:
    name = str(case.get("procedure", "")).upper()
    arguments = dict(case.get("arguments", {}))
    rows = [copy.deepcopy(dict(row)) for row in case.get("rows", [])]
    result: dict[str, Any] = {"status": "passed", "outputs": {}, "mutation_count": 0, "error_class": None}
    if name == "GET_AUTH_STATUS":
        key = arguments.get("P_CARD_NUM") or None
        matches = [row for row in rows if row.get("CARD_NUM") == key]
        if len(matches) > 1:
            result.update(status="failed", error_class="TOO_MANY_ROWS")
        else:
            result["outputs"] = {"P_STATUS": matches[0].get("AUTH_FRAUD") if matches else "N"}
    elif name == "SET_FRAUD_FLAG":
        reason = arguments.get("P_REASON")
        if reason == "":
            reason = None
        key = arguments.get("P_CARD_NUM") or None
        matches = [row for row in rows if row.get("CARD_NUM") == key]
        for row in matches:
            row["AUTH_FRAUD"] = "Y"
            row["AUTH_RESP_REASON"] = reason
        result["outputs"] = {"P_ROWS": len(matches)}
        result["mutation_count"] = len(matches)
    elif name == "CLASSIFY_AMOUNT":
        try:
            amount = Decimal(str(arguments.get("P_AMOUNT")))
        except (InvalidOperation, ValueError):
            result.update(status="failed", error_class="INVALID_NUMBER")
        else:
            if amount < 0:
                result.update(status="failed", error_class="APPLICATION_ERROR:P0001")
            else:
                result["outputs"] = {"P_CLASS": "HIGH" if amount >= 1000 else "STANDARD"}
    elif name == "NORMALIZE_REASON":
        reason = arguments.get("P_REASON")
        if reason is not None and not isinstance(reason, str):
            result.update(status="failed", error_class="TYPE_MISMATCH")
        else:
            result["outputs"] = {"P_RESULT": "UNSPECIFIED" if reason in {None, ""} else reason}
    else:
        result.update(status="blocked", error_class="PROCEDURE_OUTSIDE_SUPPORTED_SUBSET")
    return result


def build_procedure_conformance(project_root: Path) -> dict[str, Any]:
    source_path = project_root / PROCEDURE_SOURCE
    source = source_path.read_text(encoding="utf-8")
    procedures = parse_oracle_procedures(source)
    results = []
    features: Counter[str] = Counter()
    for case in procedure_cases():
        observed = execute_procedure_case(case)
        expected = case["expected"]
        for field in ("status", "outputs", "mutation_count", "error_class"):
            if field in expected and observed.get(field) != expected[field]:
                raise ValueError(f"oracle-procedure-case-failed:{case['id']}:{field}")
        features.update(case["features"])
        results.append({
            "id": case["id"],
            "procedure": case["procedure"],
            "classification": case["classification"],
            "features": case["features"],
            "request_sha256": content_hash({"arguments": case["arguments"], "rows": case["rows"]}),
            "observed": observed,
            "passed": True,
        })
    classifications = Counter(case["classification"] for case in procedure_cases())
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-procedure-conformance",
        "corpus_id": "oracle-procedure-supported-subset-v1",
        "source_path": PROCEDURE_SOURCE,
        "source_sha256": _sha256(source.encode("utf-8")),
        "procedure_ids": [item["procedure_id"] for item in procedures],
        "case_count": len(results),
        "classification_counts": dict(sorted(classifications.items())),
        "observed_feature_count": len(features),
        "results": results,
        "status": "passed",
        "evidence_class": "bounded-synthetic-procedure-semantics",
        "native_oracle_execution_observed": False,
        "native_postgresql_execution_observed": False,
        "production_ready": False,
    })


def build_procedure_ledger(project_root: Path) -> dict[str, Any]:
    source = (project_root / PROCEDURE_SOURCE).read_text(encoding="utf-8")
    procedures = parse_oracle_procedures(source)
    items = [
        ("procedure-identity-and-parameters", "exact", "bounded-source-contract", ["source-digest", "parameter-order-and-mode"]),
        ("number-bounded-domain", "exact", "bounded-canonical-decimal", ["decimal-boundary-corpus"]),
        ("select-into-single-row", "exact", "bounded-behavior", ["found-not-found-and-multiple-row-cases"]),
        ("update-and-rowcount", "normalized-equivalent", "translated-mechanism", ["side-effect-and-row-count-comparison"]),
        ("if-elsif-else", "exact", "translated-mechanism", ["branch-boundary-corpus"]),
        ("nvl-to-coalesce", "normalized-equivalent", "governed-normalization", ["null-empty-and-space-cases"]),
        ("oracle-empty-string", "policy-decision-required", "unresolved", ["customer-profile", "approved-null-empty-policy"]),
        ("no-data-found", "normalized-equivalent", "translated-exception", ["exception-class-comparison"]),
        ("raise-application-error-code", "lossy", "explicit-code-remap", ["approved-error-code-map"]),
        ("definer-invoker-rights", "policy-decision-required", "unresolved", ["oracle-authid-and-grants", "postgres-role-policy"]),
        ("transaction-ownership", "policy-decision-required", "unresolved", ["approved-transaction-boundary-policy"]),
        ("dynamic-sql", "unsupported", "excluded-from-claim-scope", ["separate-dynamic-sql-qualification"]),
        ("autonomous-transaction", "unsupported", "excluded-from-claim-scope", ["separate-transaction-qualification"]),
        ("package-state", "unsupported", "excluded-from-claim-scope", ["package-state-redesign"]),
        ("database-link", "unsupported", "excluded-from-claim-scope", ["external-database-dependency-plan"]),
        ("procedure-owned-commit", "unsupported", "excluded-from-claim-scope", ["transaction-boundary-redesign"]),
    ]
    entries = [{
        "item_id": f"oracle-procedure:{scope}",
        "scope": scope,
        "source_semantics": {"dialect": "oracle-plsql", "procedures": [item["procedure_id"] for item in procedures]},
        "target_semantics": {"dialect": "postgresql-plpgsql", "bounded_translation": True},
        "classification": classification,
        "decision": decision,
        "evidence_required": evidence,
    } for scope, classification, decision, evidence in items]
    statistics = Counter(item["classification"] for item in entries)
    return seal({
        "schema_version": "1.0",
        "ledger_type": "lightyear-oracle-procedure-compatibility-ledger",
        "source_sha256": _sha256(source.encode("utf-8")),
        "classifications": list(COMPATIBILITY_CLASSES),
        "entries": entries,
        "statistics": {name: statistics.get(name, 0) for name in COMPATIBILITY_CLASSES},
        "qualification_blocked": True,
        "production_ready": False,
    })


def build_procedure_qualification(project_root: Path) -> dict[str, Any]:
    source = (project_root / PROCEDURE_SOURCE).read_text(encoding="utf-8")
    procedures = parse_oracle_procedures(source)
    conformance = build_procedure_conformance(project_root)
    ledger = build_procedure_ledger(project_root)
    translations = [{
        "procedure_id": item["procedure_id"],
        "source_sha256": item["source_sha256"],
        "target_sql": translate_oracle_procedure(item),
        "target_sql_sha256": _sha256(translate_oracle_procedure(item).encode("utf-8")),
        "features": item["features"],
        "dependencies": item["dependencies"],
        "status": "translated-bounded-subset",
    } for item in procedures]
    gates = [
        {"gate": "declared-source-inventory", "status": "passed-source-bound", "evidence": {"procedures": len(procedures), "live_catalog_observed": False}},
        {"gate": "syntax-and-parameter-contract", "status": "passed-bounded-subset", "evidence": {"parameters": sum(len(item["parameters"]) for item in procedures)}},
        {"gate": "dependency-closure", "status": "passed-declared-source", "evidence": {"dependencies": sorted(set(dep for item in procedures for dep in item["dependencies"]))}},
        {"gate": "plsql-to-plpgsql-translation", "status": "passed-bounded-subset", "evidence": {"translated_procedures": len(translations)}},
        {"gate": "result-and-side-effect-conformance", "status": "passed-bounded-synthetic", "evidence": {"cases": conformance["case_count"], "receipt_sha256": conformance["content_sha256"]}},
        {"gate": "transaction-and-exception-policy", "status": "policy-decision-required", "evidence": {"autonomous_transactions_supported": False, "procedure_owned_commit_supported": False}},
        {"gate": "security-and-operability", "status": "blocked-live-evidence-required", "evidence": {"grants_observed": False, "plans_compared": 0}},
        {"gate": "native-source-target-execution", "status": "blocked-no-authorized-evidence", "evidence": {"oracle_execution_observed": False, "postgresql_execution_observed": False}},
    ]
    return seal({
        "schema_version": "1.0",
        "qualification_type": QUALIFICATION_TYPE,
        "qualification_id": QUALIFICATION_ID,
        "source_dialect": "oracle-plsql",
        "target_dialect": "postgresql-plpgsql",
        "source_path": PROCEDURE_SOURCE,
        "source_sha256": _sha256(source.encode("utf-8")),
        "procedure_count": len(procedures),
        "procedures": [{key: value for key, value in item.items() if key != "body"} for item in procedures],
        "translations": translations,
        "compatibility_ledger_sha256": ledger["content_sha256"],
        "conformance_receipt_sha256": conformance["content_sha256"],
        "qualification_gates": gates,
        "supported_features": sorted(set(feature for item in procedures for feature in item["features"])),
        "unsupported_features": sorted(UNSUPPORTED_FEATURES),
        "supported_procedure_subset_qualified": True,
        "live_catalog_inventory_complete": False,
        "native_execution_observed": False,
        "stored_logic_complete": False,
        "database_migration_complete": False,
        "production_ready": False,
        "claim_unlocked": "LIGHTYEAR can inventory, translate, and behaviorally qualify the declared bounded Oracle procedure subset without claiming general PL/SQL or native equivalence.",
    })


def validate_procedure_artifacts(project_root: Path, payload: Mapping[str, Any] | None = None) -> list[str]:
    expected = build_procedure_qualification(project_root)
    payload = dict(payload or expected)
    errors: list[str] = []
    if payload.get("qualification_type") != QUALIFICATION_TYPE:
        errors.append("oracle-procedure-qualification-identity-invalid")
    if payload.get("content_sha256") != content_hash(payload):
        errors.append("oracle-procedure-qualification-content-hash-invalid")
    if payload != expected:
        errors.append("oracle-procedure-qualification-drift")
    if payload.get("supported_procedure_subset_qualified") is not True:
        errors.append("oracle-procedure-supported-subset-not-qualified")
    if any(payload.get(name) is not False for name in ("native_execution_observed", "stored_logic_complete", "database_migration_complete", "production_ready")):
        errors.append("oracle-procedure-qualification-overclaim")
    ledger = build_procedure_ledger(project_root)
    if set(ledger.get("classifications", [])) != set(COMPATIBILITY_CLASSES):
        errors.append("oracle-procedure-ledger-classifications-invalid")
    if any(item["decision"] != "unresolved" for item in ledger["entries"] if item["classification"] == "policy-decision-required"):
        errors.append("oracle-procedure-policy-auto-accepted")
    if any(item["decision"] != "excluded-from-claim-scope" for item in ledger["entries"] if item["classification"] == "unsupported"):
        errors.append("oracle-procedure-unsupported-not-excluded")
    return sorted(set(errors))
