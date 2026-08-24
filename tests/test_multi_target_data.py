from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from lightyear_data.live import (
    DockerOracleRunner,
    _diagnostic_codes,
    _oracle_is_ready,
    _oracle_startup_reason,
    _oracle_vendor_ready,
    aggregate_receipts,
    evaluate_target_evidence,
    oracle_verification_sql,
    parse_evidence,
    postgres_verification_sql,
)
from lightyear_data.oracle import OracleAdapter
from lightyear_data.postgres import PostgreSQLAdapter


ROOT = Path(__file__).resolve().parents[1]
MODEL = json.loads((ROOT / "data-modernization/canonical/authfrds.model.json").read_text())
FIXTURES = json.loads((ROOT / "data-modernization/fixtures/authfrds.fixtures.json").read_text())


def evidence(adapter: PostgreSQLAdapter | OracleAdapter) -> str:
    catalog = adapter.catalog_expectation(MODEL)
    lines = ["FD_COLUMN=" + json.dumps(item, separators=(",", ":")) for item in catalog["columns"]]
    lines.append("FD_PRIMARY_KEY=" + json.dumps(catalog["primary_key"], separators=(",", ":")))
    lines.extend("FD_INDEX=" + json.dumps(item, separators=(",", ":")) for item in catalog["indexes"])
    lines.extend("FD_ROW=" + json.dumps(item, separators=(",", ":")) for item in FIXTURES["rows"])
    lines.append('FD_QUERY={"fraud_authorization_count":1,"total_approved_amount":"125.50"}')
    lines.append('FD_TRANSACTION={"commit_rows":1,"rollback_rows":1}')
    return "\n".join(lines) + "\n"


def receipt(adapter: PostgreSQLAdapter | OracleAdapter, stdout: str | None = None):
    schema = adapter.schema_sql(MODEL)
    fixtures = adapter.fixture_sql(FIXTURES, MODEL)
    verification = postgres_verification_sql(MODEL) if isinstance(adapter, PostgreSQLAdapter) else oracle_verification_sql(MODEL)
    return evaluate_target_evidence(
        adapter, MODEL, FIXTURES, stdout or evidence(adapter), "", 0, "docker",
        adapter.default_image, "sha256:test-image", schema, fixtures, verification,
        {"network_mode": "none"},
    )


class MultiTargetDataTests(unittest.TestCase):
    def test_oracle_readiness_requires_exact_marker_and_no_vendor_error(self) -> None:
        false_positive = subprocess.CompletedProcess([], 0, "ORA-12541: no listener\n", "")
        mounted = subprocess.CompletedProcess([], 0, "FD_PDB_OPEN=MOUNTED\nFD_READY\n", "")
        ready = subprocess.CompletedProcess([], 0, "FD_PDB_OPEN=READ WRITE\nFD_READY\n", "")
        self.assertFalse(_oracle_is_ready(false_positive))
        self.assertFalse(_oracle_is_ready(mounted))
        self.assertTrue(_oracle_is_ready(ready))

    def test_oracle_vendor_readiness_requires_final_banner(self) -> None:
        initializing = subprocess.CompletedProcess([], 0, "Starting Oracle Database instance FREE", "")
        ready = subprocess.CompletedProcess([], 0, "DATABASE IS READY TO USE!", "")
        self.assertFalse(_oracle_vendor_ready(initializing))
        self.assertTrue(_oracle_vendor_ready(ready))

    def test_oracle_startup_reason_redacts_logs_to_a_stable_code(self) -> None:
        self.assertEqual(
            "oracle-entrypoint-privilege-transition-failed",
            _oracle_startup_reason("Password: su: Authentication failure", ""),
        )

    def test_vendor_diagnostics_disclose_codes_without_messages(self) -> None:
        codes = _diagnostic_codes(
            "ORA-00933: SQL command not properly ended\nprivate row value",
            "SP2-0734: unknown command",
        )
        self.assertEqual(["ORA-00933", "SP2-0734"], codes)

    def test_oracle_adapter_preserves_types_constraints_and_index_order(self) -> None:
        adapter = OracleAdapter()
        sql = adapter.schema_sql(MODEL)
        self.assertIn("TRANSACTION_AMT NUMBER(12,2)", sql)
        self.assertIn("MERCHANT_NAME VARCHAR2(22 CHAR)", sql)
        self.assertIn("CONSTRAINT PK_AUTHFRDS PRIMARY KEY (CARD_NUM, AUTH_TS)", sql)
        self.assertIn("(CARD_NUM ASC, AUTH_TS DESC)", sql)
        self.assertIn("NO AUTHENTICATION", sql)
        self.assertNotIn("QUOTA UNLIMITED ON USERS", sql)
        self.assertIn("DEFAULT_PERMANENT_TABLESPACE", sql)
        self.assertIn("DBMS_ASSERT.ENQUOTE_NAME", sql)
        timestamp = next(item for item in adapter.catalog_expectation(MODEL)["columns"] if item["name"] == "AUTH_TS")
        self.assertEqual(6, timestamp["scale"])
        self.assertIn("oracle-empty-string-is-null", {item["id"] for item in adapter.mapping(MODEL)["known_gaps"]})

    def test_oracle_verification_emits_bounded_single_line_json(self) -> None:
        sql = oracle_verification_sql(MODEL)
        row_expression = sql.split("SELECT 'FD_ROW=' || ", 1)[1].split(" FROM CARDDEMO.AUTHFRDS", 1)[0]
        self.assertEqual(row_expression.count("NULL ON NULL"), 1)
        self.assertNotIn("RETURNING CLOB", sql)
        self.assertIn("RETURNING VARCHAR2(4000)", sql)
        self.assertIn("WRAP OFF", sql)
        self.assertIn("WHENEVER SQLERROR EXIT SQL.SQLCODE", sql)

    def test_oracle_index_verification_resolves_descending_expression(self) -> None:
        sql = oracle_verification_sql(MODEL)
        self.assertIn("ALL_IND_EXPRESSIONS", sql)
        self.assertIn("REGEXP_SUBSTR(FD_EXPRESSION", sql)
        self.assertIn("FD_COLUMN.SORT_ORDER", sql)
        self.assertIn("RAISE_APPLICATION_ERROR(-20001", sql)
        self.assertNotIn("KEY 'name' VALUE c.COLUMN_NAME", sql)

    def test_oracle_transaction_probe_is_bind_free_and_statement_bounded(self) -> None:
        sql = oracle_verification_sql(MODEL)
        self.assertNotIn("VARIABLE fd_commit", sql)
        self.assertNotIn(":fd_commit", sql)
        self.assertNotIn("; COMMIT;", sql)
        self.assertNotIn("; ROLLBACK;", sql)
        self.assertIn("COMMIT_ROWS=(SELECT COUNT(*)", sql)
        self.assertIn("KEY 'commit_rows' VALUE MAX(COMMIT_ROWS)", sql)
        self.assertIn("KEY 'rollback_rows' VALUE COUNT(*)", sql)

    def test_exact_receipts_pass_for_both_targets(self) -> None:
        for adapter in (PostgreSQLAdapter(), OracleAdapter()):
            with self.subTest(adapter=adapter.adapter_id):
                result = receipt(adapter)
                self.assertEqual(result["status"], "passed", result["errors"])
                self.assertTrue(all(result["checks"].values()))
                self.assertEqual(result["image_identity"], "sha256:test-image")
                self.assertIn("verification_sql_sha256", result["bindings"])

    def test_empty_output_fails_closed(self) -> None:
        result = receipt(PostgreSQLAdapter(), "not evidence\n")
        self.assertEqual(result["status"], "failed")
        self.assertIn("missing-marker:FD_PRIMARY_KEY", result["errors"])
        self.assertFalse(result["checks"]["exact_schema"])

    def test_wrong_column_type_is_detected(self) -> None:
        output = evidence(PostgreSQLAdapter()).replace('"data_type":"numeric"', '"data_type":"double precision"', 1)
        result = receipt(PostgreSQLAdapter(), output)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["exact_schema"])

    def test_wrong_key_or_index_order_is_detected(self) -> None:
        output = evidence(PostgreSQLAdapter()).replace('["card_num","auth_ts"]', '["auth_ts","card_num"]')
        output = output.replace('"order":"DESC"', '"order":"ASC"')
        result = receipt(PostgreSQLAdapter(), output)
        self.assertFalse(result["checks"]["exact_primary_key"])
        self.assertFalse(result["checks"]["exact_indexes"])

    def test_duplicate_or_missing_row_is_detected(self) -> None:
        lines = evidence(PostgreSQLAdapter()).splitlines()
        first_row = next(line for line in lines if line.startswith("FD_ROW="))
        duplicated = "\n".join(lines + [first_row]) + "\n"
        result = receipt(PostgreSQLAdapter(), duplicated)
        self.assertFalse(result["checks"]["row_count"])
        self.assertFalse(result["checks"]["normalized_row_checksums"])
        missing = "\n".join(line for line in lines if line != first_row) + "\n"
        self.assertEqual(receipt(PostgreSQLAdapter(), missing)["status"], "failed")

    def test_mutated_row_value_query_and_rollback_are_detected(self) -> None:
        output = evidence(OracleAdapter()).replace('"APPROVED_AMT":"125.50"', '"APPROVED_AMT":"125.49"')
        output = output.replace('"total_approved_amount":"125.50"', '"total_approved_amount":"125.49"')
        output = output.replace('"rollback_rows":1', '"rollback_rows":0')
        result = receipt(OracleAdapter(), output)
        self.assertFalse(result["checks"]["normalized_row_checksums"])
        self.assertFalse(result["checks"]["query_results"])
        self.assertFalse(result["checks"]["transaction_rollback"])

    def test_duplicate_singleton_marker_fails_closed(self) -> None:
        output = evidence(PostgreSQLAdapter()) + 'FD_QUERY={"fraud_authorization_count":1,"total_approved_amount":"125.50"}\n'
        parsed, errors = parse_evidence(output)
        self.assertIn("duplicate-marker:FD_QUERY", errors)
        self.assertIn("FD_QUERY", parsed)

    def test_aggregate_requires_both_passing_targets(self) -> None:
        postgres = receipt(PostgreSQLAdapter())
        oracle = receipt(OracleAdapter())
        self.assertEqual(aggregate_receipts([postgres, oracle])["status"], "passed")
        self.assertEqual(aggregate_receipts([postgres])["status"], "failed")
        failed = copy.deepcopy(oracle); failed["status"] = "failed"
        self.assertEqual(aggregate_receipts([postgres, failed])["status"], "failed")

    def test_oracle_runner_does_not_persist_password_or_publish_port(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        output = evidence(OracleAdapter())
        def fake(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            if command[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(command, 0, "sha256:oracle-image\n", "")
            if command[:3] == ["docker", "exec", "-i"]:
                if "FD_READY" in str(kwargs.get("input", "")):
                    return subprocess.CompletedProcess(command, 0, "FD_PDB_OPEN=READ WRITE\nFD_READY\n", "")
                return subprocess.CompletedProcess(command, 0, output, "")
            if command[:3] == ["docker", "logs", "--tail"]:
                return subprocess.CompletedProcess(command, 0, "DATABASE IS READY TO USE!\n", "")
            return subprocess.CompletedProcess(command, 0, "ok", "")
        result = DockerOracleRunner(fake, lambda _: None).verify(MODEL, FIXTURES)
        self.assertEqual(result["status"], "passed", result["errors"])
        serialized = json.dumps(result)
        self.assertNotIn("ORACLE_PWD", serialized)
        network_create = next(command for command, _ in calls if command[:3] == ["docker", "network", "create"])
        self.assertIn("--internal", network_create)
        run_command = next(command for command, _ in calls if command[:2] == ["docker", "run"])
        self.assertIn("--env-file", run_command)
        self.assertNotIn("-p", run_command)
        self.assertNotIn("none", run_command)
        self.assertNotIn("--rm", run_command)
        self.assertNotIn("--cap-drop", run_command)
        self.assertNotIn("no-new-privileges", run_command)
        self.assertEqual(result["security"]["network_mode"], "internal-isolated-bridge")
        self.assertFalse(result["security"]["external_egress"])
        self.assertFalse(result["security"]["cap_drop_all"])
        self.assertFalse(result["security"]["no_new_privileges"])
        self.assertIn("oracle-entrypoint-requires-default-capabilities", result["gaps"])
        self.assertTrue(any(command[:3] == ["docker", "network", "rm"] for command, _ in calls))
        sqlplus_calls = [command for command, _ in calls if command[:3] == ["docker", "exec", "-i"]]
        self.assertTrue(all("/FREE" in command[-1] and "/FREEPDB1" not in command[-1] for command in sqlplus_calls))
        self.assertTrue(all("FREEPDB1" in str(kwargs.get("input", "")) for command, kwargs in calls if command in sqlplus_calls))
        self.assertFalse(result["security"]["credentials_persisted"])

    def test_oracle_runner_fails_immediately_when_container_exits(self) -> None:
        calls: list[list[str]] = []

        def fake(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            if command[:3] == ["docker", "exec", "-i"]:
                return subprocess.CompletedProcess(command, 1, "ORA-12541\n", "")
            if command[:3] == ["docker", "inspect", "--format"]:
                return subprocess.CompletedProcess(command, 0, "exited\n", "")
            if command[:3] == ["docker", "logs", "--tail"]:
                return subprocess.CompletedProcess(command, 0, "Password: su: Authentication failure\n", "")
            return subprocess.CompletedProcess(command, 0, "ok\n", "")

        with self.assertRaisesRegex(RuntimeError, "oracle-entrypoint-privilege-transition-failed"):
            DockerOracleRunner(fake, lambda _: None).verify(MODEL, FIXTURES)
        self.assertEqual(1, sum(command[:3] == ["docker", "exec", "-i"] for command in calls))

if __name__ == "__main__":
    unittest.main()
