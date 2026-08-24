from __future__ import annotations

import hashlib
import json
import re
import secrets
import string
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .contracts import SCHEMA_VERSION, seal
from .postgres import PostgreSQLAdapter, TargetAdapter
from .oracle import OracleAdapter


SINGLETON_MARKERS = {"FD_PRIMARY_KEY", "FD_QUERY", "FD_TRANSACTION"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _row_hash(row: dict[str, Any]) -> str:
    return _sha(json.dumps(row, sort_keys=True, separators=(",", ":")))


def _diagnostic_codes(stdout: str, stderr: str) -> list[str]:
    """Expose vendor error identifiers without persisting SQL output or data."""
    return sorted(set(re.findall(r"\b(?:ORA|SP2)-\d+", stdout + "\n" + stderr)))


def _oracle_is_ready(result: subprocess.CompletedProcess[str]) -> bool:
    markers = {line.strip() for line in result.stdout.splitlines()}
    required = {"FD_PDB_OPEN=READ WRITE", "FD_READY"}
    return result.returncode == 0 and required.issubset(markers) and not _diagnostic_codes(result.stdout, result.stderr)


def _oracle_vendor_ready(result: subprocess.CompletedProcess[str]) -> bool:
    combined = result.stdout + "\n" + result.stderr
    return result.returncode == 0 and "DATABASE IS READY TO USE!" in combined


def _oracle_startup_reason(stdout: str, stderr: str) -> str:
    combined = stdout + "\n" + stderr
    if "su: Authentication failure" in combined:
        return "oracle-entrypoint-privilege-transition-failed"
    if "Listener configuration failed" in combined or "No valid IP Address returned" in combined:
        return "oracle-listener-configuration-failed"
    if "DATABASE SETUP WAS NOT SUCCESSFUL" in combined:
        return "oracle-database-setup-failed"
    return "oracle-container-startup-failed"


def parse_evidence(stdout: str) -> tuple[dict[str, Any], list[str]]:
    records: dict[str, list[Any]] = {"FD_COLUMN": [], "FD_INDEX": [], "FD_ROW": []}
    errors: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("FD_") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        if key not in records and key not in SINGLETON_MARKERS:
            errors.append(f"unknown-marker:{key}")
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            errors.append(f"malformed-marker:{key}")
            continue
        if key in SINGLETON_MARKERS:
            if key in records:
                errors.append(f"duplicate-marker:{key}")
            else:
                records[key] = value
        else:
            records[key].append(value)
    for key in SINGLETON_MARKERS:
        if key not in records:
            errors.append(f"missing-marker:{key}")
    return records, errors


def evaluate_target_evidence(
    adapter: TargetAdapter,
    model: dict[str, Any],
    fixtures: dict[str, Any],
    stdout: str,
    stderr: str,
    exit_code: int,
    runtime: str,
    image: str,
    image_identity: str,
    schema_sql: str,
    fixture_statements: str,
    verification_sql: str,
    security: dict[str, Any],
) -> dict[str, Any]:
    records, errors = parse_evidence(stdout)
    expectation = adapter.catalog_expectation(model)
    actual_columns = sorted(records["FD_COLUMN"], key=lambda item: item.get("ordinal", -1))
    actual_indexes = sorted(records["FD_INDEX"], key=lambda item: item.get("name", ""))
    actual_rows = sorted(records["FD_ROW"], key=lambda item: tuple(str(item.get(k, "")) for k in ("CARD_NUM", "AUTH_TS")))
    expected_rows = sorted(fixtures.get("rows", []), key=lambda item: tuple(str(item.get(k, "")) for k in ("CARD_NUM", "AUTH_TS")))
    expected_queries = {
        "fraud_authorization_count": fixtures.get("expected_results", {}).get("fraud_authorization_count"),
        "total_approved_amount": fixtures.get("expected_results", {}).get("total_approved_amount"),
    }
    expected_transaction = {"commit_rows": 1, "rollback_rows": 1}
    checks = {
        "complete_evidence": not errors,
        "exact_schema": actual_columns == expectation["columns"],
        "exact_primary_key": records.get("FD_PRIMARY_KEY") == expectation["primary_key"],
        "exact_indexes": actual_indexes == sorted(expectation["indexes"], key=lambda item: item["name"]),
        "row_count": len(actual_rows) == len(expected_rows) and len(expected_rows) > 0,
        "normalized_row_checksums": [_row_hash(row) for row in actual_rows] == [_row_hash(row) for row in expected_rows],
        "query_results": records.get("FD_QUERY") == expected_queries,
        "transaction_commit": (records.get("FD_TRANSACTION") or {}).get("commit_rows") == 1,
        "transaction_rollback": records.get("FD_TRANSACTION") == expected_transaction,
        "target_command": exit_code == 0,
    }
    if exit_code != 0:
        errors.append("target-command-failed")
    errors.extend(f"check-failed:{name}" for name, passed in checks.items() if not passed)
    mapping = adapter.mapping(model)
    return seal({
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "factorydark-target-data-equivalence",
        "evidence_class": "live-container-target-equivalence",
        "workload": "carddemo-authorization-authfrds",
        "source": "db2-zos-offline-contract",
        "target": adapter.dialect,
        "adapter": {"id": adapter.adapter_id, "version": adapter.adapter_version},
        "status": "passed" if not errors and all(checks.values()) else "failed",
        "production_ready": False,
        "runtime": runtime,
        "image": image,
        "image_identity": image_identity,
        "security": security,
        "checks": checks,
        "errors": sorted(set(errors)),
        "statistics": {
            "expected_columns": len(expectation["columns"]), "actual_columns": len(actual_columns),
            "expected_rows": len(expected_rows), "actual_rows": len(actual_rows),
        },
        "row_checksums": sorted(_row_hash(row) for row in actual_rows),
        "query_results": records.get("FD_QUERY"),
        "bindings": {
            "canonical_model_sha256": model.get("content_sha256"),
            "target_mapping_sha256": mapping.get("content_sha256"),
            "fixture_catalog_sha256": fixtures.get("content_sha256"),
            "schema_sql_sha256": _sha(schema_sql),
            "fixture_sql_sha256": _sha(fixture_statements),
            "verification_sql_sha256": _sha(verification_sql),
        },
        "stdout_sha256": _sha(stdout),
        "stderr_sha256": _sha(stderr),
        "diagnostic_codes": _diagnostic_codes(stdout, stderr),
        "gaps": [
            "live-db2-catalog-not-observed", "live-zos-data-not-compared",
            "cdc-and-cutover-not-proven",
        ] + [item["id"] for item in mapping.get("known_gaps", []) if item["id"] != "live-db2-catalog-not-observed"]
          + list(security.get("exceptions", [])),
    })


def aggregate_receipts(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    targets = {receipt.get("target", "unknown"): {
        "status": receipt.get("status"), "content_sha256": receipt.get("content_sha256"),
        "adapter": receipt.get("adapter"), "image_identity": receipt.get("image_identity"),
    } for receipt in receipts}
    required = {"postgresql-16", "oracle-26ai-free"}
    errors = []
    if set(targets) != required:
        errors.append("required-target-set-incomplete")
    if any(item.get("status") != "passed" for item in targets.values()):
        errors.append("target-equivalence-failed")
    return seal({
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "factorydark-multi-target-data-equivalence",
        "evidence_class": "live-container-multi-target-equivalence",
        "workload": "carddemo-authorization-authfrds",
        "status": "passed" if not errors else "failed",
        "production_ready": False,
        "targets": targets,
        "errors": errors,
        "gaps": ["live-db2-catalog-not-observed", "live-zos-data-not-compared", "cdc-and-cutover-not-proven"],
    })


def _json_expr_postgres(model: dict[str, Any]) -> str:
    parts = []
    for column in model["columns"]:
        name = column["name"]
        ref = f'"{name.lower()}"'
        source = column["source_type"]
        if source in {"CHAR", "VARCHAR"}:
            value = f"rtrim({ref})"
        elif source == "TIMESTAMP":
            value = f"to_char({ref}, 'YYYY-MM-DD\"T\"HH24:MI:SS.US')"
        elif source == "DATE":
            value = f"to_char({ref}, 'YYYY-MM-DD')"
        elif source == "DECIMAL":
            value = f"CASE WHEN {ref} IS NULL THEN NULL ELSE to_char({ref}, 'FM99999999999999999990" + (".00" if (column.get("scale") or 0) == 2 else "") + "') END"
        else:
            value = ref
        parts.extend([f"'{name}'", value])
    return "json_build_object(" + ", ".join(parts) + ")::text"


def postgres_verification_sql(model: dict[str, Any]) -> str:
    row_json = _json_expr_postgres(model)
    return f"""
SELECT 'FD_COLUMN=' || json_build_object(
  'name', column_name, 'ordinal', ordinal_position, 'data_type', data_type,
  'length', character_maximum_length, 'precision', numeric_precision,
  'scale', numeric_scale, 'nullable', is_nullable='YES')::text
FROM information_schema.columns WHERE table_schema='carddemo' AND table_name='authfrds'
ORDER BY ordinal_position;
SELECT 'FD_PRIMARY_KEY=' || json_build_object(
  'name', tc.constraint_name,
  'columns', json_agg(kcu.column_name ORDER BY kcu.ordinal_position))::text
FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu
ON tc.constraint_catalog=kcu.constraint_catalog AND tc.constraint_schema=kcu.constraint_schema
AND tc.constraint_name=kcu.constraint_name
WHERE tc.table_schema='carddemo' AND tc.table_name='authfrds' AND tc.constraint_type='PRIMARY KEY'
GROUP BY tc.constraint_name;
SELECT 'FD_INDEX=' || json_build_object(
  'name', ci.relname, 'unique', ix.indisunique,
  'columns', json_agg(json_build_object('name', a.attname, 'order',
    CASE WHEN (ix.indoption[s.n] & 1)=1 THEN 'DESC' ELSE 'ASC' END) ORDER BY s.n))::text
FROM pg_index ix JOIN pg_class ct ON ct.oid=ix.indrelid JOIN pg_namespace ns ON ns.oid=ct.relnamespace
JOIN pg_class ci ON ci.oid=ix.indexrelid CROSS JOIN LATERAL generate_subscripts(ix.indkey,1) s(n)
JOIN pg_attribute a ON a.attrelid=ct.oid AND a.attnum=ix.indkey[s.n]
WHERE ns.nspname='carddemo' AND ct.relname='authfrds' AND ci.relname='xauthfrd'
GROUP BY ci.relname, ix.indisunique;
SELECT 'FD_ROW=' || {row_json} FROM carddemo.authfrds ORDER BY card_num, auth_ts;
SELECT 'FD_QUERY=' || json_build_object(
  'fraud_authorization_count', count(*) FILTER (WHERE auth_fraud='Y'),
  'total_approved_amount', to_char(sum(approved_amt), 'FM99999999999999999990.00'))::text
FROM carddemo.authfrds;
CREATE TEMP TABLE fd_tx_probe(id INTEGER);
BEGIN; INSERT INTO fd_tx_probe VALUES (1); COMMIT;
SELECT count(*) AS fd_commit_count FROM fd_tx_probe \\gset
BEGIN; DELETE FROM fd_tx_probe; ROLLBACK;
SELECT 'FD_TRANSACTION=' || json_build_object('commit_rows', :fd_commit_count, 'rollback_rows', count(*))::text FROM fd_tx_probe;
"""


def _json_expr_oracle(model: dict[str, Any]) -> str:
    parts = []
    for column in model["columns"]:
        name = column["name"]
        source = column["source_type"]
        if source in {"CHAR", "VARCHAR"}:
            value = f"RTRIM({name})"
        elif source == "TIMESTAMP":
            value = f"TO_CHAR({name}, 'YYYY-MM-DD\"T\"HH24:MI:SS.FF6')"
        elif source == "DATE":
            value = f"TO_CHAR({name}, 'YYYY-MM-DD')"
        elif source == "DECIMAL":
            fmt = "FM99999999999999999990" + ("D00" if (column.get("scale") or 0) == 2 else "")
            value = f"TO_CHAR({name}, '{fmt}', 'NLS_NUMERIC_CHARACTERS=''.,''')"
        else:
            value = name
        parts.append(f"KEY '{name}' VALUE {value}")
    # Every bounded AUTHFRDS evidence record is comfortably below Oracle's
    # 4,000-byte SQL VARCHAR2 limit.  Returning VARCHAR2 keeps each marker on
    # one physical SQL*Plus line; CLOB output is chunked and can turn otherwise
    # valid JSON into several malformed evidence lines.
    return "JSON_OBJECT(" + ", ".join(parts) + " NULL ON NULL RETURNING VARCHAR2(4000))"


def oracle_verification_sql(model: dict[str, Any]) -> str:
    row_json = _json_expr_oracle(model)
    return f"""
WHENEVER OSERROR EXIT FAILURE
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0 LINESIZE 32767 WRAP OFF TRIMSPOOL ON
SELECT 'FD_COLUMN=' || JSON_OBJECT(
  KEY 'name' VALUE COLUMN_NAME, KEY 'ordinal' VALUE COLUMN_ID,
  KEY 'data_type' VALUE CASE WHEN DATA_TYPE='TIMESTAMP' THEN 'TIMESTAMP(' || DATA_SCALE || ')' ELSE DATA_TYPE END,
  KEY 'length' VALUE CASE WHEN DATA_TYPE IN ('CHAR','VARCHAR2') THEN CHAR_LENGTH END,
  KEY 'precision' VALUE DATA_PRECISION, KEY 'scale' VALUE DATA_SCALE,
  KEY 'nullable' VALUE CASE NULLABLE WHEN 'Y' THEN 'true' ELSE 'false' END FORMAT JSON
  NULL ON NULL RETURNING VARCHAR2(4000)) FROM ALL_TAB_COLUMNS
WHERE OWNER='CARDDEMO' AND TABLE_NAME='AUTHFRDS' ORDER BY COLUMN_ID;
SELECT 'FD_PRIMARY_KEY=' || JSON_OBJECT(KEY 'name' VALUE c.CONSTRAINT_NAME,
  KEY 'columns' VALUE JSON_ARRAYAGG(cc.COLUMN_NAME ORDER BY cc.POSITION RETURNING VARCHAR2(4000)) FORMAT JSON
  RETURNING VARCHAR2(4000))
FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS cc ON cc.OWNER=c.OWNER AND cc.CONSTRAINT_NAME=c.CONSTRAINT_NAME
WHERE c.OWNER='CARDDEMO' AND c.TABLE_NAME='AUTHFRDS' AND c.CONSTRAINT_TYPE='P' GROUP BY c.CONSTRAINT_NAME;
SET SERVEROUTPUT ON SIZE UNLIMITED
DECLARE
  FD_INDEX_NAME VARCHAR2(128) := 'XAUTHFRD';
  FD_UNIQUENESS VARCHAR2(9);
  FD_COLUMNS_JSON VARCHAR2(4000) := '[';
  FD_COLUMN_JSON VARCHAR2(4000);
  FD_COLUMN_NAME VARCHAR2(128);
  FD_EXPRESSION VARCHAR2(4000);
  FD_INDEX_JSON VARCHAR2(4000);
  FD_FIRST BOOLEAN := TRUE;
BEGIN
  SELECT UNIQUENESS INTO FD_UNIQUENESS
  FROM ALL_INDEXES
  WHERE OWNER='CARDDEMO' AND TABLE_NAME='AUTHFRDS' AND INDEX_NAME=FD_INDEX_NAME;

  FOR FD_COLUMN IN (
    SELECT INDEX_OWNER, INDEX_NAME, COLUMN_NAME, COLUMN_POSITION, DESCEND AS SORT_ORDER
    FROM ALL_IND_COLUMNS
    WHERE INDEX_OWNER='CARDDEMO' AND TABLE_NAME='AUTHFRDS' AND INDEX_NAME=FD_INDEX_NAME
    ORDER BY COLUMN_POSITION
  ) LOOP
    FD_COLUMN_NAME := FD_COLUMN.COLUMN_NAME;
    BEGIN
      SELECT COLUMN_EXPRESSION INTO FD_EXPRESSION
      FROM ALL_IND_EXPRESSIONS
      WHERE INDEX_OWNER=FD_COLUMN.INDEX_OWNER
        AND INDEX_NAME=FD_COLUMN.INDEX_NAME
        AND COLUMN_POSITION=FD_COLUMN.COLUMN_POSITION;
      IF FD_EXPRESSION IS NOT NULL THEN
        FD_COLUMN_NAME := REGEXP_SUBSTR(FD_EXPRESSION, '"([^"]+)"', 1, 1, NULL, 1);
        IF FD_COLUMN_NAME IS NULL THEN
          RAISE_APPLICATION_ERROR(-20001, 'Unsupported index expression');
        END IF;
      END IF;
    EXCEPTION
      WHEN NO_DATA_FOUND THEN NULL;
    END;

    SELECT JSON_OBJECT(
      KEY 'name' VALUE FD_COLUMN_NAME,
      KEY 'order' VALUE FD_COLUMN.SORT_ORDER
      RETURNING VARCHAR2(4000))
    INTO FD_COLUMN_JSON FROM DUAL;
    IF NOT FD_FIRST THEN
      FD_COLUMNS_JSON := FD_COLUMNS_JSON || ',';
    END IF;
    FD_COLUMNS_JSON := FD_COLUMNS_JSON || FD_COLUMN_JSON;
    FD_FIRST := FALSE;
  END LOOP;

  FD_COLUMNS_JSON := FD_COLUMNS_JSON || ']';
  SELECT JSON_OBJECT(
    KEY 'name' VALUE FD_INDEX_NAME,
    KEY 'unique' VALUE CASE FD_UNIQUENESS WHEN 'UNIQUE' THEN 'true' ELSE 'false' END FORMAT JSON,
    KEY 'columns' VALUE FD_COLUMNS_JSON FORMAT JSON
    RETURNING VARCHAR2(4000))
  INTO FD_INDEX_JSON FROM DUAL;
  DBMS_OUTPUT.PUT_LINE('FD_INDEX=' || FD_INDEX_JSON);
END;
/
SELECT 'FD_ROW=' || {row_json} FROM CARDDEMO.AUTHFRDS ORDER BY CARD_NUM, AUTH_TS;
SELECT 'FD_QUERY=' || JSON_OBJECT(
  KEY 'fraud_authorization_count' VALUE SUM(CASE WHEN AUTH_FRAUD='Y' THEN 1 ELSE 0 END),
  KEY 'total_approved_amount' VALUE TO_CHAR(SUM(APPROVED_AMT), 'FM99999999999999999990D00', 'NLS_NUMERIC_CHARACTERS=''.,''')
  RETURNING VARCHAR2(4000)) FROM CARDDEMO.AUTHFRDS;
CREATE GLOBAL TEMPORARY TABLE CARDDEMO.FD_TX_PROBE(
  ID NUMBER, COMMIT_ROWS NUMBER) ON COMMIT PRESERVE ROWS;
INSERT INTO CARDDEMO.FD_TX_PROBE(ID, COMMIT_ROWS) VALUES (1, NULL);
COMMIT;
UPDATE CARDDEMO.FD_TX_PROBE SET COMMIT_ROWS=(SELECT COUNT(*) FROM CARDDEMO.FD_TX_PROBE);
COMMIT;
DELETE FROM CARDDEMO.FD_TX_PROBE;
ROLLBACK;
SELECT 'FD_TRANSACTION=' || JSON_OBJECT(
  KEY 'commit_rows' VALUE MAX(COMMIT_ROWS), KEY 'rollback_rows' VALUE COUNT(*)
  RETURNING VARCHAR2(4000)) FROM CARDDEMO.FD_TX_PROBE;
EXIT
"""


class DockerTargetRunner:
    def __init__(self, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run, pause: Callable[[float], None] = time.sleep) -> None:
        self.run = run
        self.pause = pause

    def _image_identity(self, image: str) -> str:
        result = self.run(["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True, capture_output=True, timeout=30)
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unresolved"


class DockerPostgresExactRunner(DockerTargetRunner):
    def verify(self, model: dict[str, Any], fixtures: dict[str, Any], image: str | None = None) -> dict[str, Any]:
        adapter = PostgreSQLAdapter()
        image = image or adapter.default_image
        schema_sql = adapter.schema_sql(model)
        fixture_statements = adapter.fixture_sql(fixtures, model)
        verification_sql = postgres_verification_sql(model)
        name = "factorydark-pg-" + uuid.uuid4().hex[:12]
        command = ["docker", "run", "-d", "--rm", "--name", name, "--network", "none", "--read-only",
            "--user", "70:70", "--pids-limit", "128", "--memory", "512m", "--cpus", "1.0",
            "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=256m,uid=70,gid=70",
            "--tmpfs", "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=70,gid=70",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,uid=70,gid=70", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_DB=factorydark", image]
        started = self.run(command, text=True, capture_output=True, timeout=120)
        if started.returncode != 0:
            raise RuntimeError("PostgreSQL container failed to start: " + started.stderr.strip())
        try:
            for _ in range(120):
                ready = self.run(["docker", "exec", name, "psql", "-U", "postgres", "-d", "factorydark", "-Atqc", "SELECT 1"], text=True, capture_output=True, timeout=10)
                if ready.returncode == 0 and ready.stdout.strip() == "1":
                    break
                self.pause(0.5)
            else:
                raise RuntimeError("PostgreSQL did not become ready")
            result = self.run(["docker", "exec", "-i", name, "psql", "-U", "postgres", "-d", "factorydark", "-v", "ON_ERROR_STOP=1", "-At"],
                input=schema_sql + fixture_statements + verification_sql, text=True, capture_output=True, timeout=180)
            return evaluate_target_evidence(adapter, model, fixtures, result.stdout, result.stderr, result.returncode,
                "docker", image, self._image_identity(image), schema_sql, fixture_statements, verification_sql,
                {"network_mode": "none", "read_only_root": True, "cap_drop_all": True, "no_new_privileges": True})
        finally:
            self.run(["docker", "rm", "-f", name], text=True, capture_output=True, timeout=30)


class DockerOracleRunner(DockerTargetRunner):
    def verify(self, model: dict[str, Any], fixtures: dict[str, Any], image: str | None = None) -> dict[str, Any]:
        adapter = OracleAdapter()
        image = image or adapter.default_image
        schema_sql = adapter.schema_sql(model)
        fixture_statements = adapter.fixture_sql(fixtures, model)
        verification_sql = oracle_verification_sql(model)
        name = "factorydark-oracle-" + uuid.uuid4().hex[:10]
        network_name = "factorydark-oracle-net-" + uuid.uuid4().hex[:10]
        password = "Fd" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(30))
        env_path: Path | None = None
        network_created = False
        try:
            with tempfile.NamedTemporaryFile("w", prefix="factorydark-oracle-", suffix=".env", delete=False) as handle:
                handle.write("ORACLE_PWD=" + password + "\n")
                env_path = Path(handle.name)
            network = self.run(
                ["docker", "network", "create", "--internal", network_name],
                text=True, capture_output=True, timeout=30,
            )
            if network.returncode != 0:
                raise RuntimeError("Oracle internal network failed to start: " + network.stderr.strip())
            network_created = True
            command = ["docker", "run", "-d", "--name", name, "--network", network_name, "--pids-limit", "512",
                "--memory", "4g", "--cpus", "2.0", "--shm-size", "1g",
                "--env-file", str(env_path), image]
            started = self.run(command, text=True, capture_output=True, timeout=180)
            env_path.unlink(missing_ok=True)
            env_path = None
            if started.returncode != 0:
                raise RuntimeError("Oracle container failed to start: " + started.stderr.strip())
            ready_script = """WHENEVER OSERROR EXIT FAILURE
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT 'FD_PDB_OPEN=' || OPEN_MODE FROM V$PDBS WHERE NAME='FREEPDB1';
ALTER SESSION SET CONTAINER=FREEPDB1;
SELECT 'FD_READY' FROM DUAL;
EXIT
"""
            stable_ready_probes = 0
            for _ in range(300):
                ready = self.run(
                    ["docker", "exec", "-i", name, "bash", "-lc",
                     "sqlplus -L -s system/\"$ORACLE_PWD\"@//localhost:1521/FREE"],
                    input=ready_script, text=True, capture_output=True, timeout=20,
                )
                state = self.run(
                    ["docker", "inspect", "--format", "{{.State.Status}}", name],
                    text=True, capture_output=True, timeout=10,
                )
                startup_log = self.run(
                    ["docker", "logs", "--tail", "2000", name],
                    text=True, capture_output=True, timeout=30,
                )
                if state.returncode != 0 or state.stdout.strip() in {"exited", "dead"}:
                    combined = startup_log.stdout + "\n" + startup_log.stderr
                    reason = _oracle_startup_reason(startup_log.stdout, startup_log.stderr)
                    codes = ",".join(_diagnostic_codes(startup_log.stdout, startup_log.stderr)) or "none"
                    raise RuntimeError(
                        f"Oracle container exited during startup; reason={reason}; "
                        f"diagnostic_codes={codes}; log_sha256={_sha(combined)}"
                    )
                if _oracle_vendor_ready(startup_log) and _oracle_is_ready(ready):
                    stable_ready_probes += 1
                    if stable_ready_probes >= 2:
                        break
                else:
                    stable_ready_probes = 0
                self.pause(2.0)
            else:
                raise RuntimeError("Oracle Database Free did not become ready")
            script = ("WHENEVER OSERROR EXIT FAILURE\nWHENEVER SQLERROR EXIT SQL.SQLCODE\n"
                      "ALTER SESSION SET CONTAINER=FREEPDB1;\n" + schema_sql + fixture_statements + verification_sql)
            result = self.run(["docker", "exec", "-i", name, "bash", "-lc", "sqlplus -L -s system/\"$ORACLE_PWD\"@//localhost:1521/FREE"],
                input=script, text=True, capture_output=True, timeout=300)
            return evaluate_target_evidence(adapter, model, fixtures, result.stdout, result.stderr, result.returncode,
                "docker", image, self._image_identity(image), schema_sql, fixture_statements, verification_sql,
                {"network_mode": "internal-isolated-bridge", "internal_network": True,
                 "external_egress": False, "read_only_root": False, "cap_drop_all": False,
                 "no_new_privileges": False, "credentials_persisted": False,
                 "host_ports_published": False,
                 "startup_privilege_model": "oracle-vendor-default-entrypoint",
                 "exceptions": [
                     "oracle-entrypoint-requires-default-capabilities",
                     "oracle-entrypoint-incompatible-with-no-new-privileges",
                 ]})
        finally:
            if env_path is not None:
                env_path.unlink(missing_ok=True)
            self.run(["docker", "rm", "-f", name], text=True, capture_output=True, timeout=30)
            if network_created:
                self.run(["docker", "network", "rm", network_name], text=True, capture_output=True, timeout=30)
