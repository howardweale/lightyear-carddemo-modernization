from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping

from .contracts import content_hash, seal


CORPUS_ID = "oracle-v23.3-first-eight-dialect-fixtures-v1"
OUTPUT_ROOT = Path("data-modernization/oracle-dialect-conformance")
OFFICIAL_COMMIT = "e3325a83e56c516815844025418a96ecaf219751"
FIXTURE_IDS = (
    "oracle-empty-string-null",
    "oracle-number-precision-scale",
    "oracle-date-time-arithmetic",
    "oracle-nvl-decode-coercion",
    "oracle-rownum-ordering",
    "oracle-select-for-update-sequence",
    "oracle-select-into-no-data-found",
    "oracle-lob-boundaries",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _case(case_id: str, operation: str, inputs: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": case_id,
        "operation": operation,
        "inputs": dict(inputs),
        "expected": dict(expected),
    }


def fixture_catalog(project_root: Path) -> dict[str, Any]:
    identified = json.loads(
        (project_root / "reference-estates/idempiere/oracle-semantic-fixtures.json").read_text(encoding="utf-8")
    )
    prior = {item["id"]: item for item in identified["fixtures"]}
    if tuple(item["id"] for item in identified["fixtures"]) != FIXTURE_IDS:
        raise ValueError("oracle-dialect-prior-fixture-identity-drift")

    clob_text = "Lightyear Oracle dialect"
    fixtures = [
        {
            "id": FIXTURE_IDS[0],
            "title": "Zero-length VARCHAR2 collapses to NULL",
            "authority": {
                "documentation": "https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Concatenation-Operator.html",
                "official_corpus_paths": [
                    "customer_orders/co_create.sql",
                    "human_resources/hr_create.sql",
                ],
            },
            "cases": [
                _case("empty-to-null", "oracle-character-normalize", {"value": ""}, {"value": None}),
                _case("null-remains-null", "oracle-character-normalize", {"value": None}, {"value": None}),
                _case("space-remains-value", "oracle-character-normalize", {"value": " "}, {"value": " "}),
            ],
        },
        {
            "id": FIXTURE_IDS[1],
            "title": "NUMBER precision, scale, rounding, and overflow",
            "authority": {
                "documentation": "https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html",
                "official_corpus_paths": [
                    "customer_orders/co_create.sql",
                    "human_resources/hr_create.sql",
                    "sales_history/sh_create.sql",
                ],
            },
            "cases": [
                _case("round-scale-one", "oracle-number-cast", {"value": "123.89", "precision": 6, "scale": 1}, {"value": "123.9"}),
                _case("round-small-number", "oracle-number-cast", {"value": ".000127", "precision": 4, "scale": 5}, {"value": "0.00013"}),
                _case("precision-overflow", "oracle-number-cast", {"value": "123.89", "precision": 3, "scale": 2}, {"error": "ORA-01438"}),
            ],
        },
        {
            "id": FIXTURE_IDS[2],
            "title": "DATE retains seconds and uses day arithmetic",
            "authority": {
                "documentation": "https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html",
                "official_corpus_paths": [
                    "customer_orders/co_create.sql",
                    "human_resources/hr_create.sql",
                    "sales_history/sh_create.sql",
                ],
            },
            "cases": [
                _case("retain-seconds", "oracle-date-retain", {"value": "2024-02-29T23:59:59"}, {"value": "2024-02-29T23:59:59"}),
                _case("add-one-second", "oracle-date-add-seconds", {"value": "2024-02-29T23:59:59", "seconds": 1}, {"value": "2024-03-01T00:00:00"}),
                _case("trunc-day", "oracle-date-trunc", {"value": "2024-03-01T17:12:03"}, {"value": "2024-03-01T00:00:00"}),
            ],
        },
        {
            "id": FIXTURE_IDS[3],
            "title": "NVL conversion and DECODE null matching",
            "authority": {
                "documentation": [
                    "https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/NVL.html",
                    "https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/DECODE.html",
                ],
                "official_corpus_paths": ["human_resources/hr_create.sql"],
            },
            "cases": [
                _case("nvl-null", "oracle-nvl", {"value": None, "fallback": "fallback"}, {"value": "fallback"}),
                _case("nvl-empty", "oracle-nvl", {"value": "", "fallback": "fallback"}, {"value": "fallback"}),
                _case("decode-null-equals-null", "oracle-decode", {"value": None, "searches": [None, "A"], "results": ["null-match", "a-match"], "default": "miss"}, {"value": "null-match"}),
            ],
        },
        {
            "id": FIXTURE_IDS[4],
            "title": "ROWNUM filtering precedes same-level ordering",
            "authority": {
                "documentation": "https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/ROWNUM-Pseudocolumn.html",
                "official_corpus_paths": ["human_resources/hr_create.sql"],
            },
            "cases": [
                _case("rownum-before-order", "oracle-rownum-then-order", {"values": [3, 1, 2], "limit": 2}, {"values": [1, 3]}),
                _case("order-before-rownum", "oracle-order-then-rownum", {"values": [3, 1, 2], "limit": 2}, {"values": [1, 2]}),
                _case("rownum-greater-than-one", "oracle-rownum-greater-than", {"values": [3, 1, 2], "threshold": 1}, {"values": []}),
            ],
        },
        {
            "id": FIXTURE_IDS[5],
            "title": "SELECT FOR UPDATE sequence allocation stays transactional",
            "authority": {
                "documentation": "https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SELECT.html",
                "official_corpus_paths": ["customer_orders/co_create.sql"],
            },
            "cases": [
                _case("two-allocations", "oracle-sequence-allocate", {"initial": 100, "count": 2}, {"allocated": [101, 102], "committed_value": 102}),
                _case("rollback-allocation", "oracle-sequence-rollback", {"initial": 200, "count": 1}, {"allocated": [201], "committed_value": 200}),
                _case("serialized-sessions", "oracle-sequence-sessions", {"initial": 7, "sessions": ["A", "B"]}, {"allocations": [{"session": "A", "value": 8}, {"session": "B", "value": 9}], "committed_value": 9}),
            ],
        },
        {
            "id": FIXTURE_IDS[6],
            "title": "SELECT INTO distinguishes zero, one, and multiple rows",
            "authority": {
                "documentation": [
                    "https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/SELECT-INTO-statement.html",
                    "https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/predefined-exceptions.html",
                ],
                "official_corpus_paths": ["human_resources/hr_code.sql"],
            },
            "cases": [
                _case("no-row-handler", "oracle-select-into", {"rows": [], "no_data_default": "DEFAULT"}, {"value": "DEFAULT", "handled": "NO_DATA_FOUND"}),
                _case("single-row", "oracle-select-into", {"rows": [42], "no_data_default": "DEFAULT"}, {"value": 42, "handled": None}),
                _case("multiple-rows", "oracle-select-into", {"rows": [1, 2], "no_data_default": "DEFAULT"}, {"error": "ORA-01422"}),
            ],
        },
        {
            "id": FIXTURE_IDS[7],
            "title": "BLOB bytes and CLOB characters remain distinct",
            "authority": {
                "documentation": "https://docs.oracle.com/en/database/oracle/oracle-database/26/adlob/LOB-classifications.html",
                "official_corpus_paths": ["customer_orders/co_create.sql"],
            },
            "cases": [
                _case("blob-byte-content", "oracle-blob", {"hex": "0001ff"}, {"byte_length": 3, "sha256": _sha256(bytes.fromhex("0001ff"))}),
                _case("clob-character-content", "oracle-clob", {"text": clob_text}, {"character_length": len(clob_text), "sha256": _sha256(clob_text.encode("utf-8"))}),
                _case("null-lobs", "oracle-lob-null", {"blob": None, "clob": None}, {"blob_is_null": True, "clob_is_null": True}),
            ],
        },
    ]
    for fixture in fixtures:
        fixture["priority"] = prior[fixture["id"]]["priority"]
        fixture["idempiere_source_paths"] = prior[fixture["id"]]["source_paths"]
    return seal({
        "schema_version": "1.0",
        "catalog_type": "lightyear-oracle-dialect-fixture-catalog",
        "corpus_id": CORPUS_ID,
        "official_sample_schema_commit": OFFICIAL_COMMIT,
        "official_sample_schemas": ["customer_orders", "human_resources", "sales_history"],
        "fixtures": fixtures,
        "fixture_count": len(fixtures),
        "case_count": sum(len(item["cases"]) for item in fixtures),
        "native_oracle_sql_emitted": True,
        "native_oracle_executed": False,
        "production_ready": False,
    })


def _oracle_character(value: Any) -> Any:
    return None if value == "" else value


def _oracle_number(value: Any, precision: int, scale: int) -> dict[str, Any]:
    number = Decimal(str(value))
    quantum = Decimal(1).scaleb(-scale)
    rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
    limit = Decimal(10) ** (precision - scale)
    if abs(rounded) >= limit:
        return {"error": "ORA-01438"}
    return {"value": format(rounded, "f")}


def execute_case(case: Mapping[str, Any]) -> dict[str, Any]:
    operation = str(case["operation"])
    inputs = dict(case["inputs"])
    if operation == "oracle-character-normalize":
        return {"value": _oracle_character(inputs.get("value"))}
    if operation == "oracle-number-cast":
        return _oracle_number(inputs["value"], int(inputs["precision"]), int(inputs["scale"]))
    if operation.startswith("oracle-date-"):
        value = datetime.fromisoformat(str(inputs["value"]))
        if operation == "oracle-date-add-seconds":
            value += timedelta(seconds=int(inputs["seconds"]))
        elif operation == "oracle-date-trunc":
            value = value.replace(hour=0, minute=0, second=0, microsecond=0)
        return {"value": value.isoformat(timespec="seconds")}
    if operation == "oracle-nvl":
        value = _oracle_character(inputs.get("value"))
        return {"value": inputs["fallback"] if value is None else value}
    if operation == "oracle-decode":
        value = _oracle_character(inputs.get("value"))
        for search, result in zip(inputs["searches"], inputs["results"]):
            if value == _oracle_character(search):
                return {"value": result}
        return {"value": inputs.get("default")}
    if operation == "oracle-rownum-then-order":
        return {"values": sorted(inputs["values"][: int(inputs["limit"])])}
    if operation == "oracle-order-then-rownum":
        return {"values": sorted(inputs["values"])[: int(inputs["limit"])]}
    if operation == "oracle-rownum-greater-than":
        return {"values": [] if int(inputs["threshold"]) >= 1 else list(inputs["values"])}
    if operation in {"oracle-sequence-allocate", "oracle-sequence-rollback"}:
        initial = int(inputs["initial"])
        allocated = list(range(initial + 1, initial + int(inputs["count"]) + 1))
        committed = initial if operation.endswith("rollback") else allocated[-1]
        return {"allocated": allocated, "committed_value": committed}
    if operation == "oracle-sequence-sessions":
        initial = int(inputs["initial"])
        allocations = [
            {"session": session, "value": initial + offset}
            for offset, session in enumerate(inputs["sessions"], 1)
        ]
        return {"allocations": allocations, "committed_value": allocations[-1]["value"]}
    if operation == "oracle-select-into":
        rows = list(inputs["rows"])
        if not rows:
            return {"value": inputs["no_data_default"], "handled": "NO_DATA_FOUND"}
        if len(rows) > 1:
            return {"error": "ORA-01422"}
        return {"value": rows[0], "handled": None}
    if operation == "oracle-blob":
        raw = bytes.fromhex(str(inputs["hex"]))
        return {"byte_length": len(raw), "sha256": _sha256(raw)}
    if operation == "oracle-clob":
        text = str(inputs["text"])
        return {"character_length": len(text), "sha256": _sha256(text.encode("utf-8"))}
    if operation == "oracle-lob-null":
        return {"blob_is_null": inputs.get("blob") is None, "clob_is_null": inputs.get("clob") is None}
    raise ValueError(f"oracle-dialect-operation-unsupported:{operation}")


def native_oracle_sql() -> str:
    return """-- LIGHTYEAR MS #49 native Oracle fixture harness
-- Source authority: oracle-samples/db-sample-schemas v23.3 at e3325a83e56c516815844025418a96ecaf219751
-- This script emits LY49|<fixture-id>|PASS or raises an application error.
SET SERVEROUTPUT ON
SET DEFINE OFF
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

DECLARE
  v VARCHAR2(1) := '';
BEGIN
  IF v IS NOT NULL OR ' ' IS NULL THEN RAISE_APPLICATION_ERROR(-20001, 'empty-string-null'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-empty-string-null|PASS');
END;
/

BEGIN EXECUTE IMMEDIATE 'DROP TABLE ly49_number_probe PURGE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;
/
CREATE TABLE ly49_number_probe (v NUMBER(3,2));
DECLARE
  a NUMBER(6,1) := 123.89;
  b NUMBER(4,5) := .000127;
  overflow_seen BOOLEAN := FALSE;
BEGIN
  BEGIN INSERT INTO ly49_number_probe VALUES (123.89); EXCEPTION WHEN OTHERS THEN overflow_seen := SQLCODE = -1438; END;
  IF a != 123.9 OR b != .00013 OR NOT overflow_seen THEN RAISE_APPLICATION_ERROR(-20002, 'number'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-number-precision-scale|PASS');
END;
/
DROP TABLE ly49_number_probe PURGE;

DECLARE
  d DATE := TO_DATE('2024-02-29 23:59:59', 'YYYY-MM-DD HH24:MI:SS');
BEGIN
  IF TO_CHAR(d + 1/86400, 'YYYY-MM-DD HH24:MI:SS') != '2024-03-01 00:00:00'
     OR TO_CHAR(TRUNC(d), 'YYYY-MM-DD HH24:MI:SS') != '2024-02-29 00:00:00'
  THEN RAISE_APPLICATION_ERROR(-20003, 'date'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-date-time-arithmetic|PASS');
END;
/

BEGIN
  IF NVL('', 'fallback') != 'fallback' OR DECODE(NULL, NULL, 'match', 'miss') != 'match'
  THEN RAISE_APPLICATION_ERROR(-20004, 'nvl-decode'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-nvl-decode-coercion|PASS');
END;
/

DECLARE
  before_order VARCHAR2(20);
  after_order VARCHAR2(20);
  impossible NUMBER;
BEGIN
  WITH values_in_fetch_order (seq, v) AS (SELECT 1,3 FROM dual UNION ALL SELECT 2,1 FROM dual UNION ALL SELECT 3,2 FROM dual)
  SELECT LISTAGG(v, ',') WITHIN GROUP (ORDER BY v) INTO before_order
    FROM (SELECT v FROM (SELECT v FROM values_in_fetch_order ORDER BY seq) WHERE ROWNUM <= 2);
  WITH values_to_sort (v) AS (SELECT 3 FROM dual UNION ALL SELECT 1 FROM dual UNION ALL SELECT 2 FROM dual)
  SELECT LISTAGG(v, ',') WITHIN GROUP (ORDER BY v) INTO after_order
    FROM (SELECT v FROM (SELECT v FROM values_to_sort ORDER BY v) WHERE ROWNUM <= 2);
  SELECT COUNT(*) INTO impossible FROM dual WHERE ROWNUM > 1;
  IF before_order != '1,3' OR after_order != '1,2' OR impossible != 0
  THEN RAISE_APPLICATION_ERROR(-20005, 'rownum'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-rownum-ordering|PASS');
END;
/

BEGIN EXECUTE IMMEDIATE 'DROP TABLE ly49_sequence PURGE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;
/
CREATE TABLE ly49_sequence (id NUMBER PRIMARY KEY, current_value NUMBER NOT NULL);
INSERT INTO ly49_sequence VALUES (1, 100);
COMMIT;
DECLARE
  v NUMBER;
BEGIN
  SELECT current_value INTO v FROM ly49_sequence WHERE id = 1 FOR UPDATE;
  UPDATE ly49_sequence SET current_value = v + 1 WHERE id = 1;
  SAVEPOINT before_second;
  UPDATE ly49_sequence SET current_value = current_value + 1 WHERE id = 1;
  ROLLBACK TO before_second;
  SELECT current_value INTO v FROM ly49_sequence WHERE id = 1;
  IF v != 101 THEN RAISE_APPLICATION_ERROR(-20006, 'for-update-sequence'); END IF;
  COMMIT;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-select-for-update-sequence|PASS');
END;
/
DROP TABLE ly49_sequence PURGE;

DECLARE
  v NUMBER;
  no_data_seen BOOLEAN := FALSE;
  too_many_seen BOOLEAN := FALSE;
BEGIN
  BEGIN SELECT 1 INTO v FROM dual WHERE 1 = 0; EXCEPTION WHEN NO_DATA_FOUND THEN no_data_seen := TRUE; END;
  BEGIN SELECT column_value INTO v FROM TABLE(sys.odcinumberlist(1,2)); EXCEPTION WHEN TOO_MANY_ROWS THEN too_many_seen := TRUE; END;
  IF NOT no_data_seen OR NOT too_many_seen THEN RAISE_APPLICATION_ERROR(-20007, 'select-into'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-select-into-no-data-found|PASS');
END;
/

BEGIN EXECUTE IMMEDIATE 'DROP TABLE ly49_lobs PURGE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;
/
CREATE TABLE ly49_lobs (id NUMBER PRIMARY KEY, binary_value BLOB, character_value CLOB);
INSERT INTO ly49_lobs VALUES (1, HEXTORAW('0001FF'), TO_CLOB('Lightyear Oracle dialect'));
DECLARE
  blob_length NUMBER;
  clob_length NUMBER;
BEGIN
  SELECT DBMS_LOB.GETLENGTH(binary_value), DBMS_LOB.GETLENGTH(character_value)
    INTO blob_length, clob_length FROM ly49_lobs WHERE id = 1;
  IF blob_length != 3 OR clob_length != 24 THEN RAISE_APPLICATION_ERROR(-20008, 'lob'); END IF;
  ROLLBACK;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-lob-boundaries|PASS');
END;
/
DROP TABLE ly49_lobs PURGE;
EXIT SUCCESS
"""


def build_conformance_receipt(project_root: Path, catalog: Mapping[str, Any], sql: str) -> dict[str, Any]:
    manifest = json.loads(
        (project_root / "reference-estates/oracle/corpus-manifest.json").read_text(encoding="utf-8")
    )
    if manifest["source"]["commit"] != OFFICIAL_COMMIT:
        raise ValueError("oracle-dialect-official-corpus-pin-mismatch")
    results = []
    for fixture in catalog["fixtures"]:
        for case in fixture["cases"]:
            observed = execute_case(case)
            passed = observed == case["expected"]
            results.append({
                "fixture_id": fixture["id"],
                "case_id": case["id"],
                "request_sha256": content_hash({"operation": case["operation"], "inputs": case["inputs"]}),
                "expected_sha256": content_hash(case["expected"]),
                "observed": observed,
                "passed": passed,
            })
    if not all(item["passed"] for item in results):
        failed = next(item for item in results if not item["passed"])
        raise ValueError(f"oracle-dialect-case-failed:{failed['fixture_id']}:{failed['case_id']}")
    return seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-oracle-dialect-model-conformance",
        "corpus_id": CORPUS_ID,
        "catalog_sha256": catalog["content_sha256"],
        "official_corpus_manifest_sha256": content_hash(manifest),
        "official_sample_schema_commit": OFFICIAL_COMMIT,
        "native_sql_sha256": _sha256(sql.encode("utf-8")),
        "fixture_count": len(catalog["fixtures"]),
        "case_count": len(results),
        "results": results,
        "status": "passed-bounded-model",
        "oracle_dialect_authority_acquired": True,
        "bounded_model_execution_observed": True,
        "native_oracle_execution_observed": False,
        "native_oracle_conformance": False,
        "idempiere_application_equivalence": False,
        "cloudbank_mapping_complete": False,
        "migration_complete": False,
        "production_ready": False,
    })


def build_oracle_dialect_artifacts(project_root: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    catalog = fixture_catalog(project_root)
    sql = native_oracle_sql()
    receipt = build_conformance_receipt(project_root, catalog, sql)
    return catalog, receipt, sql


def validate_conformance_receipt(project_root: Path, payload: Mapping[str, Any]) -> list[str]:
    catalog = fixture_catalog(project_root)
    expected = build_conformance_receipt(project_root, catalog, native_oracle_sql())
    receipt = dict(payload)
    errors = []
    if receipt != expected:
        errors.append("oracle-dialect-conformance-receipt-drift")
    if receipt.get("content_sha256") != content_hash(receipt):
        errors.append("oracle-dialect-conformance-receipt-integrity-invalid")
    for name in (
        "native_oracle_execution_observed", "native_oracle_conformance",
        "idempiere_application_equivalence", "cloudbank_mapping_complete",
        "migration_complete", "production_ready",
    ):
        if receipt.get(name) is not False:
            errors.append(f"oracle-dialect-overclaim:{name}")
    if receipt.get("bounded_model_execution_observed") is not True:
        errors.append("oracle-dialect-model-execution-missing")
    return sorted(set(errors))


def validate_oracle_dialect_artifacts(project_root: Path) -> list[str]:
    catalog, receipt, sql = build_oracle_dialect_artifacts(project_root)
    expected: dict[str, Any] = {
        "fixture-catalog.json": catalog,
        "model-conformance.receipt.json": receipt,
    }
    errors = []
    output = project_root / OUTPUT_ROOT
    for name, payload in expected.items():
        path = output / name
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != payload:
            errors.append(f"oracle-dialect-artifact-drift:{name}")
    actual_receipt_path = output / "model-conformance.receipt.json"
    if actual_receipt_path.is_file():
        errors.extend(validate_conformance_receipt(
            project_root,
            json.loads(actual_receipt_path.read_text(encoding="utf-8")),
        ))
    sql_path = output / "native-oracle-fixtures.sql"
    if not sql_path.is_file() or sql_path.read_text(encoding="utf-8") != sql:
        errors.append("oracle-dialect-artifact-drift:native-oracle-fixtures.sql")
    for name in (
        "native_oracle_execution_observed", "native_oracle_conformance",
        "idempiere_application_equivalence", "cloudbank_mapping_complete",
        "migration_complete", "production_ready",
    ):
        if receipt.get(name) is not False:
            errors.append(f"oracle-dialect-overclaim:{name}")
    if receipt.get("fixture_count") != 8 or receipt.get("case_count") != 24:
        errors.append("oracle-dialect-corpus-size-invalid")
    if not all(item.get("passed") for item in receipt.get("results", [])):
        errors.append("oracle-dialect-model-case-failed")
    return sorted(set(errors))
