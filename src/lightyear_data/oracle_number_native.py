"""Materialize and run the first catalog family using an external Oracle wallet.

No container or database is provisioned here. SQL emits observations, never a
passed flag. Python compares those observations with independent expectations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from .contracts import content_hash, sign

ROOT = Path("data-modernization/oracle-native-execution-gate")
MARKER = "LY_NUMBER_OBSERVATION="
IDENTITY = "LY_NUMBER_IDENTITY="
EXPECTED = {
    "arithmetic": "124.00", "null_value": None, "rounded": "2.35",
    "maximum": "999.99", "overflow_code": -1438, "recovery": "124.00",
    "nls_dot": "124.00", "nls_comma": "124,00",
}
FOCUS_PROBES = {
    "canonical semantics": ("arithmetic",),
    "null and absence semantics": ("null_value",),
    "boundary and overflow semantics": ("rounded", "maximum", "overflow_code"),
    "session, ordering, and version semantics": ("nls_dot", "nls_comma"),
    "failure and diagnostic semantics": ("overflow_code", "recovery"),
}
DIMENSION_PROBES = {
    "canonical": (), "null-boundary": ("null_value",),
    "session-version": ("nls_dot", "nls_comma"),
    "failure-recovery": ("overflow_code", "recovery"),
}


def number_cases(root: Path) -> list[dict]:
    corpus = json.loads((root / "data-modernization/oracle-core-sql-coverage/core-sql-corpus.json").read_text(encoding="utf-8"))
    cases = [item for item in corpus["results"] if item["domain_id"] == "types" and item["topic"] == "number"]
    if len(cases) != 20 or len({item["behavior_id"] for item in cases}) != 5:
        raise ValueError("NUMBER catalog family changed; review the harness bindings")
    return cases


def probes(case: dict) -> tuple[str, ...]:
    return tuple(sorted(set(FOCUS_PROBES[case["focus"]] + DIMENSION_PROBES[case["dimension"]])))


def render_case(case: dict, lane: str) -> str:
    if lane not in ("19c", "26ai") or not re.fullmatch(r"ORA-TYPE-00[1-5]-CASE-0[1-4]", case["id"]):
        raise ValueError("Unexpected NUMBER case or lane")
    fields = {
        "arithmetic": "v_sum", "null_value": "v_null", "rounded": "v_rounded",
        "maximum": "v_maximum", "overflow_code": "v_overflow", "recovery": "v_recovery",
        "nls_dot": "v_dot", "nls_comma": "v_comma",
    }
    pairs = ",\n      ".join(f"'{name}' VALUE {fields[name]}" for name in probes(case))
    return f"""-- Catalog case {case['id']}; lane {lane}; {case['focus']}; {case['dimension']}
-- Every value below comes from an Oracle expression or SQLCODE.
DECLARE
  v_sum VARCHAR2(32); v_null NUMBER; v_rounded VARCHAR2(32); v_maximum VARCHAR2(32);
  v_overflow NUMBER := 0; v_recovery VARCHAR2(32); v_sink NUMBER;
  v_dot VARCHAR2(32); v_comma VARCHAR2(32); v_json VARCHAR2(4000);
BEGIN
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,'''),
         CAST(NULL AS NUMBER) + 1,
         TO_CHAR(CAST(2.345 AS NUMBER(3,2)), 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,'''),
         TO_CHAR(CAST(999.99 AS NUMBER(5,2)), 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,''')
    INTO v_sum, v_null, v_rounded, v_maximum FROM dual;
  BEGIN
    SELECT CAST(1000 AS NUMBER(3,0)) INTO v_sink FROM dual;
  EXCEPTION WHEN OTHERS THEN v_overflow := SQLCODE;
  END;
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,''')
    INTO v_recovery FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ''.,''';
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00') INTO v_dot FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '',.''';
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00') INTO v_comma FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ''.,''';
  SELECT JSON_OBJECT('case_id' VALUE '{case['id']}', 'observations' VALUE
    JSON_OBJECT({pairs} NULL ON NULL) RETURNING VARCHAR2(4000)) INTO v_json FROM dual;
  DBMS_OUTPUT.PUT_LINE('{MARKER}' || v_json);
END;
/
"""


def materialize(root: Path) -> dict:
    cases = number_cases(root)
    for lane in ("19c", "26ai"):
        directory = root / ROOT / "cases" / lane
        directory.mkdir(parents=True, exist_ok=True)
        for case in cases:
            (directory / (case["id"] + ".sql")).write_text(render_case(case, lane), encoding="utf-8", newline="\n")
    return {"topic_family_count": 1, "case_count": 20, "materialized_harness_count": 40,
            "native_executed_case_count": 0, "status": "materialized-not-executed"}


def verify_harnesses(root: Path) -> None:
    for lane in ("19c", "26ai"):
        for case in number_cases(root):
            path = root / ROOT / "cases" / lane / (case["id"] + ".sql")
            if path.read_bytes() != render_case(case, lane).encode():
                raise ValueError(f"NUMBER harness drift: {lane}/{case['id']}")


IDENTITY_SQL = """
SELECT 'LY_NUMBER_IDENTITY=' || JSON_OBJECT(
  'version_full' VALUE (SELECT version_full FROM v$instance),
  'banner' VALUE (SELECT banner_full FROM v$version WHERE banner_full LIKE 'Oracle%'),
  'dbid' VALUE (SELECT TO_CHAR(dbid) FROM v$database),
  'container_name' VALUE SYS_CONTEXT('USERENV','CON_NAME'),
  'character_set' VALUE (SELECT value FROM nls_database_parameters WHERE parameter='NLS_CHARACTERSET'),
  'national_character_set' VALUE (SELECT value FROM nls_database_parameters WHERE parameter='NLS_NCHAR_CHARACTERSET'),
  'database_timezone' VALUE DBTIMEZONE,
  'options' VALUE (SELECT JSON_ARRAYAGG(parameter || ':' || value ORDER BY parameter RETURNING CLOB) FROM v$option) FORMAT JSON,
  'session' VALUE JSON_OBJECT(
    'current_schema' VALUE SYS_CONTEXT('USERENV','CURRENT_SCHEMA'),
    'current_edition' VALUE SYS_CONTEXT('USERENV','CURRENT_EDITION_NAME'),
    'session_timezone' VALUE SESSIONTIMEZONE,
    'nls_date_format' VALUE (SELECT value FROM nls_session_parameters WHERE parameter='NLS_DATE_FORMAT'),
    'nls_timestamp_format' VALUE (SELECT value FROM nls_session_parameters WHERE parameter='NLS_TIMESTAMP_FORMAT'),
    'nls_numeric_characters' VALUE (SELECT value FROM nls_session_parameters WHERE parameter='NLS_NUMERIC_CHARACTERS'),
    'nls_sort' VALUE (SELECT value FROM nls_session_parameters WHERE parameter='NLS_SORT'),
    'nls_comp' VALUE (SELECT value FROM nls_session_parameters WHERE parameter='NLS_COMP'),
    'isolation_level' VALUE NULL)
  RETURNING CLOB) FROM dual;
"""


def parse_observations(stdout: str, cases: list[dict]) -> tuple[dict, dict]:
    identities, observations = [], {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if line.startswith(IDENTITY):
            identities.append(json.loads(line[len(IDENTITY):]))
        elif line.startswith(MARKER):
            value = json.loads(line[len(MARKER):])
            case_id = value["case_id"]
            if case_id in observations:
                raise ValueError("Duplicate native case observation")
            observations[case_id] = value["observations"]
    if len(identities) != 1 or set(observations) != {case["id"] for case in cases}:
        raise ValueError("Incomplete or unexpected native observations/identity")
    return identities[0], observations


def observed_results(root: Path, lane: str, observations: dict, started: str, completed: str) -> list[dict]:
    results = []
    for case in number_cases(root):
        observed = observations[case["id"]]
        expected = {name: EXPECTED[name] for name in probes(case)}
        path = root / ROOT / "cases" / lane / (case["id"] + ".sql")
        results.append({
            "case_id": case["id"], "behavior_id": case["behavior_id"],
            "status": "passed-native" if observed == expected else "failed-native",
            "bounded_expectation_sha256": content_hash({"expected": case["expected"]}),
            "harness_sql_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "observed_result_sha256": content_hash({"observed": observed}),
            "native_probe_expectation_sha256": content_hash({"expected": expected}),
            "observations": observed,
            "diagnostic_codes": [f"ORA-{abs(observed['overflow_code']):05d}"]
                if type(observed.get("overflow_code")) is int and observed["overflow_code"] else [],
            "started_at": started, "completed_at": completed,
        })
    return results


def run(root: Path, lane: str, wallet_alias: str, client: str, key: str, runner: str) -> dict:
    from .oracle_native_gate import build_native_case_manifest, validate_native_execution_receipt
    if not key or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", wallet_alias):
        raise ValueError("An external signing key and wallet alias are required")
    if lane not in ("19c", "26ai") or not re.fullmatch(r"[A-Za-z0-9._:@/+,-]{1,256}", runner):
        raise ValueError("A valid lane and runner identity are required")
    verify_harnesses(root)
    cases = number_cases(root)
    sql = """SET ECHO OFF FEEDBACK OFF HEADING OFF PAGESIZE 0 VERIFY OFF DEFINE OFF
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LONG 100000 LONGCHUNKSIZE 100000 LINESIZE 32767 TRIMSPOOL ON
WHENEVER OSERROR EXIT FAILURE
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
ALTER SESSION SET TIME_ZONE = '+00:00';
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF6';
ALTER SESSION SET NLS_SORT = 'BINARY';
ALTER SESSION SET NLS_COMP = 'BINARY';
ALTER SESSION SET ISOLATION_LEVEL = READ COMMITTED;
""" + IDENTITY_SQL + "\n".join(render_case(case, lane) for case in cases) + "\nEXIT\n"
    started = datetime.now(timezone.utc).isoformat()
    execution = subprocess.run([client, "-L", "-S", f"/@{wallet_alias}"], input=sql,
                               text=True, capture_output=True, timeout=180, check=False)
    completed = datetime.now(timezone.utc).isoformat()
    if execution.returncode or re.search(r"(?m)^\s*(?:ORA|SP2)-\d+", execution.stdout + "\n" + execution.stderr):
        raise ValueError("Oracle client failed; no native receipt published (raw output not persisted)")
    identity, observations = parse_observations(execution.stdout, cases)
    banner = identity.pop("banner")
    if lane == "26ai" and not re.search(r"26\s*ai", banner, re.I):
        raise ValueError("Database banner does not identify Oracle 26ai")
    session = identity.pop("session")
    # USERENV has no ISOLATION_LEVEL parameter. This runner explicitly set it
    # above and accepted the SQL client's success; distinguish that provenance
    # from the settings actually read back by IDENTITY_SQL.
    session["isolation_level"] = "READ COMMITTED"
    session["isolation_level_provenance"] = "explicit ALTER SESSION accepted"
    identity.update(database_lane=lane,
                    version_banner_sha256=hashlib.sha256(banner.encode()).hexdigest(),
                    dbid_sha256=hashlib.sha256(identity.pop("dbid").encode()).hexdigest(),
                    option_set_sha256=content_hash({"options": identity.pop("options")}))
    results = observed_results(root, lane, observations, started, completed)
    groups = {case["behavior_id"] for case in cases}
    verified = sum(all(row["status"] == "passed-native" for row in results if row["behavior_id"] == behavior)
                   for behavior in groups)
    receipt = sign({
        "schema_version": "1.0", "receipt_type": "lightyear-oracle-native-execution-receipt",
        "release": "0.51.0", "manifest_sha256": build_native_case_manifest(root)["content_sha256"],
        "run_id": "oracle-number-" + uuid.uuid4().hex, "runner_identity": runner,
        "raw_stdout_sha256": hashlib.sha256(execution.stdout.encode()).hexdigest(),
        "raw_stderr_sha256": hashlib.sha256(execution.stderr.encode()).hexdigest(),
        "database_identity": identity, "session_settings": session,
        "security": {"external_wallet_authentication": True, "credentials_in_arguments": False,
                     "credentials_persisted": False, "raw_stdout_persisted": False, "raw_stderr_persisted": False},
        "results": results, "native_executed_case_count": len(results),
        "native_passed_case_count": sum(row["status"] == "passed-native" for row in results),
        "native_verified_behavior_count": verified, "native_oracle_conformance": False,
        "target_equivalence_observed": False, "idempiere_application_equivalence": False,
        "cloudbank_mapping_complete": False, "migration_complete": False, "production_ready": False,
    }, key, runner)
    errors = validate_native_execution_receipt(root, receipt, key)
    if errors:
        raise ValueError("Native receipt rejected: " + ", ".join(errors))
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("materialize", "verify", "run"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--lane", choices=("19c", "26ai"))
    parser.add_argument("--wallet-alias")
    parser.add_argument("--client", default="sqlplus")
    parser.add_argument("--runner")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "materialize":
            result = materialize(args.root)
        elif args.command == "verify":
            verify_harnesses(args.root)
            result = {"status": "passed-materialization-check", "native_execution_observed": False}
        else:
            if not all((args.lane, args.wallet_alias, args.runner, args.output)):
                raise ValueError("run requires --lane, --wallet-alias, --runner and --output")
            result = run(args.root, args.lane, args.wallet_alias, args.client,
                         os.environ.get("LIGHTYEAR_ORACLE_NATIVE_EVIDENCE_KEY", ""), args.runner)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Never overwrite an earlier signed run.
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2))
        return 1 if result.get("native_passed_case_count", 20) != 20 else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
