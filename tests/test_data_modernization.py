from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from lightyear_data.builder import build_assets
from lightyear_data.contracts import content_hash, verify_signature
from lightyear_data.equivalence import DockerPostgresRunner, offline_equivalence
from lightyear_data.fixtures import ebcdic, fixture_catalog, packed_decimal, zoned_decimal
from lightyear_data.parser import parse_db2_ddl, parse_dcl, parse_embedded_sql
from lightyear_data.postgres import PostgreSQLAdapter, fixture_sql
from lightyear_data.validation import DEVELOPMENT_KEY, validate_assets
from lightyear_knowledge_graph.builder import build_graph
from lightyear_knowledge_graph.validation import validate_graph


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PROJECT_ROOT.parent / "carddemo-upstream"
AUTH_ROOT = LEGACY_ROOT / "app/app-authorization-ims-db2-mq"
ALLOW_MISSING_UPSTREAM = os.environ.get("LIGHTYEAR_ALLOW_MISSING_UPSTREAM") == "1"


class DataModernizationFixtureTests(unittest.TestCase):
    def test_pinned_upstream_fixture_is_required_for_a_complete_suite(self) -> None:
        if not AUTH_ROOT.is_dir() and ALLOW_MISSING_UPSTREAM:
            self.skipTest("Explicitly incomplete unit-only run accepted missing upstream fixture")
        self.assertTrue(
            AUTH_ROOT.is_dir(),
            "Required ../carddemo-upstream fixture is missing; a green suite would omit the "
            "data-modernization integration tests. Clone the pinned AWS CardDemo source, or set "
            "LIGHTYEAR_ALLOW_MISSING_UPSTREAM=1 only for an explicitly incomplete unit-only run.",
        )


@unittest.skipUnless(AUTH_ROOT.is_dir(), "AWS CardDemo upstream fixture is not available")
class DataModernizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ddl = (AUTH_ROOT / "ddl/AUTHFRDS.ddl").read_text(encoding="utf-8")
        cls.index = (AUTH_ROOT / "ddl/XAUTHFRD.ddl").read_text(encoding="utf-8")
        cls.dcl = (AUTH_ROOT / "dcl/AUTHFRDS.dcl").read_text(encoding="utf-8")
        cls.program = (AUTH_ROOT / "cbl/COPAUS2C.cbl").read_text(encoding="utf-8")
        cls.model = parse_db2_ddl(cls.ddl + "\n" + cls.index)
        cls.fixtures = fixture_catalog()
        cls.adapter = PostgreSQLAdapter()
        cls.mapping = cls.adapter.mapping(cls.model)

    def test_db2_ddl_has_complete_authfrds_contract(self) -> None:
        self.assertEqual((self.model["schema"], self.model["name"]), ("CARDDEMO", "AUTHFRDS"))
        self.assertEqual(len(self.model["columns"]), 26)
        self.assertEqual(self.model["constraints"][0]["columns"], ["CARD_NUM", "AUTH_TS"])
        self.assertEqual(self.model["indexes"][0]["columns"][1], {"name": "AUTH_TS", "order": "DESC"})

    def test_empty_ddl_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "no CREATE TABLE"):
            parse_db2_ddl("-- no schema")

    def test_dcl_columns_match_ddl_exactly(self) -> None:
        dcl = parse_dcl(self.dcl)
        self.assertEqual(dcl["declared_columns"], [column["name"] for column in self.model["columns"]])
        self.assertIn("TRANSACTION-AMT", dcl["host_fields"])

    def test_embedded_sql_links_insert_and_fraud_update_to_paragraphs(self) -> None:
        statements = parse_embedded_sql(self.program)["statements"]
        writes = [(item["operation"], item["paragraph"], item["line_start"]) for item in statements if item["operation"] in {"INSERT", "UPDATE"}]
        self.assertEqual(writes, [("INSERT", "MAIN-PARA", 141), ("UPDATE", "FRAUD-UPDATE", 222)])
        self.assertEqual(len(next(item for item in statements if item["operation"] == "INSERT")["columns"]), 26)

    def test_postgresql_adapter_preserves_precision_nullability_and_index_order(self) -> None:
        sql = self.adapter.schema_sql(self.model)
        self.assertIn('"transaction_amt" NUMERIC(12,2)', sql)
        self.assertIn('"card_num" CHAR(16) NOT NULL', sql)
        self.assertIn('PRIMARY KEY ("card_num", "auth_ts")', sql)
        self.assertIn('("card_num" ASC, "auth_ts" DESC)', sql)

    def test_boundary_fixture_encodings_are_explicit(self) -> None:
        self.assertEqual(bytes.fromhex(ebcdic("A", 1)).decode("cp037"), "A")
        self.assertTrue(packed_decimal("-9.99", 12, 2).endswith("9D"))
        self.assertTrue(zoned_decimal("-9.99", 12, 2).endswith("D9"))
        self.assertEqual(set(self.fixtures["coverage"]), {"ebcdic-cp037", "packed-decimal", "zoned-decimal", "date", "null", "fixed-width"})

    def test_empty_fixtures_cannot_pass(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        fixtures["rows"] = []
        result = offline_equivalence(self.model, self.mapping, fixtures)
        self.assertEqual(result["status"], "failed")
        self.assertIn("fixture-set-empty", result["errors"])

    def test_duplicate_primary_key_cannot_pass(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        fixtures["rows"].append(copy.deepcopy(fixtures["rows"][0]))
        result = offline_equivalence(self.model, self.mapping, fixtures)
        self.assertEqual(result["status"], "failed")
        self.assertIn("duplicate-primary-key", result["errors"])

    def test_extra_unique_row_cannot_silently_change_expected_results(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        extra = copy.deepcopy(fixtures["rows"][0])
        extra["CARD_NUM"] = "4000000000000099"
        fixtures["rows"].append(extra)
        result = offline_equivalence(self.model, self.mapping, fixtures)
        self.assertEqual(result["status"], "failed")
        self.assertIn("row-count-mismatch", result["errors"])
        self.assertIn("row-checksum-mismatch", result["errors"])

    def test_missing_or_extra_columns_cannot_pass(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        fixtures["rows"][0].pop("AUTH_FRAUD")
        result = offline_equivalence(self.model, self.mapping, fixtures)
        self.assertEqual(result["status"], "failed")
        self.assertIn("row-1-column-mismatch", result["errors"])

    def test_fixture_sql_refuses_empty_and_incomplete_catalogs(self) -> None:
        with self.assertRaisesRegex(ValueError, "no rows"):
            fixture_sql({"rows": []}, self.model)
        fixtures = copy.deepcopy(self.fixtures)
        fixtures["rows"][0].pop("CARD_NUM")
        with self.assertRaisesRegex(ValueError, "exactly match"):
            fixture_sql(fixtures, self.model)

    def test_offline_receipt_is_signed_and_tamper_evident(self) -> None:
        receipt = json.loads((PROJECT_ROOT / "data-modernization/receipts/authfrds.offline.receipt.json").read_text())
        self.assertTrue(verify_signature(receipt, DEVELOPMENT_KEY))
        self.assertEqual(self.fixtures["content_sha256"], receipt["bindings"]["fixture_catalog_sha256"])
        receipt["checks"]["transaction_rollback"] = False
        self.assertFalse(verify_signature(receipt, DEVELOPMENT_KEY))

    def test_content_hash_excludes_signature_but_not_evidence(self) -> None:
        receipt = json.loads((PROJECT_ROOT / "data-modernization/receipts/authfrds.offline.receipt.json").read_text())
        self.assertEqual(content_hash(receipt), receipt["content_sha256"])
        receipt["statistics"]["rows"] = 0
        self.assertNotEqual(content_hash(receipt), receipt["content_sha256"])

    def test_assets_rebuild_byte_for_byte_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_assets(LEGACY_ROOT, root)
            self.assertEqual(validate_assets(root)["status"], "passed")
            generated = [
                "canonical/authfrds.model.json", "source/authfrds.dcl-contract.json",
                "source/authfrds.embedded-sql.json", "mappings/authfrds-postgresql.json",
                "mappings/authfrds-oracle.json", "fixtures/authfrds.fixtures.json",
                "postgres/authfrds.sql", "oracle/authfrds.sql",
                "receipts/authfrds.offline.receipt.json",
                "receipts/authfrds.oracle-offline.receipt.json",
                "receipts/authfrds.target-plan.json",
                "semantic-core/database-semantic-core.json",
                "semantic-core/authfrds.canonical-schema.json",
                "semantic-core/authfrds.profile-contract.json",
                "semantic-core/authfrds.schema-transformation-plan.json",
                "semantic-core/authfrds.compatibility-ledger.json",
                "semantic-core/authfrds.adapter-conformance.receipt.json",
            ]
            for relative in generated:
                self.assertEqual(
                    (PROJECT_ROOT / "data-modernization" / relative).read_bytes(),
                    (root / "data-modernization" / relative).read_bytes(), relative,
                )

    def test_docker_runner_uses_isolation_and_requires_all_markers(self) -> None:
        calls: list[list[str]] = []
        def fake(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            if command[:3] == ["docker", "exec", "-i"]:
                return subprocess.CompletedProcess(command, 0, "FD_ROWS=2\nFD_FRAUD=1\nFD_APPROVED=125.50\nFD_COLUMNS=26\nFD_PK=1\nFD_INDEX=1\nFD_ROLLBACK_ROWS=2\n", "")
            if "psql" in command:
                return subprocess.CompletedProcess(command, 0, "1\n", "")
            return subprocess.CompletedProcess(command, 0, "ok", "")
        receipt = DockerPostgresRunner(fake).verify("SELECT 1;", "SELECT 1;")
        self.assertEqual(receipt["status"], "passed")
        run = calls[0]
        self.assertIn("none", run)
        self.assertIn("--read-only", run)
        self.assertIn("ALL", run)
        self.assertIn("no-new-privileges", run)
        self.assertIn("70:70", run)
        self.assertFalse(any("PASSWORD" in item for item in run))
        probes = [command for command in calls if command[:2] == ["docker", "exec"] and "-i" not in command]
        self.assertEqual(len(probes), 1)
        self.assertIn("factorydark", probes[0])
        self.assertIn("SELECT 1", probes[0])
        self.assertNotIn("pg_isready", probes[0])

    def test_docker_waits_for_the_requested_database_not_just_the_server(self) -> None:
        attempts = 0
        pauses: list[float] = []
        def fake(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal attempts
            if command[:3] == ["docker", "exec", "-i"]:
                output = "FD_ROWS=2\nFD_FRAUD=1\nFD_APPROVED=125.50\nFD_COLUMNS=26\nFD_PK=1\nFD_INDEX=1\nFD_ROLLBACK_ROWS=2\n"
                return subprocess.CompletedProcess(command, 0, output, "")
            if "psql" in command:
                attempts += 1
                if attempts == 1:
                    return subprocess.CompletedProcess(command, 2, "", 'database "factorydark" does not exist')
                return subprocess.CompletedProcess(command, 0, "1\n", "")
            return subprocess.CompletedProcess(command, 0, "ok", "")
        receipt = DockerPostgresRunner(fake, pauses.append).verify("", "")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(attempts, 2)
        self.assertEqual(pauses, [0.5])

    def test_docker_missing_result_marker_fails(self) -> None:
        def fake(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            output = "FD_ROWS=2\nFD_FRAUD=1\n" if command[:3] == ["docker", "exec", "-i"] else "ok"
            if "psql" in command and command[:3] != ["docker", "exec", "-i"]:
                output = "1\n"
            return subprocess.CompletedProcess(command, 0, output, "")
        receipt = DockerPostgresRunner(fake).verify("", "")
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["reason_code"], "verification-marker-mismatch")

    def test_graph_contains_db2_schema_and_sql_lineage(self) -> None:
        graph = build_graph(
            LEGACY_ROOT, PROJECT_ROOT, PROJECT_ROOT / "knowledge/mappings/carddemo-db2-authfrds.json",
            "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e", "repository-content",
        )
        payload = graph.to_dict()
        self.assertEqual(validate_graph(payload), [])
        kinds = {node["id"]: node["kind"] for node in payload["nodes"]}
        self.assertEqual(kinds["legacy:db2-table:CARDDEMO.AUTHFRDS"], "db2_table")
        self.assertEqual(kinds["legacy:db2-column:CARDDEMO.AUTHFRDS.CARD_NUM"], "db2_column")
        relations = {(edge["source"], edge["relation"], edge["target"]) for edge in payload["edges"]}
        self.assertIn(("legacy:cobol-paragraph:COPAUS2C:MAIN-PARA", "ISSUES_SQL", "legacy:db2-sql:COPAUS2C:141:3"), relations)
        self.assertIn(("legacy:db2-sql:COPAUS2C:222:4", "REFERENCES_COLUMN", "legacy:db2-column:CARDDEMO.AUTHFRDS.AUTH_FRAUD"), relations)

    def test_control_tower_contains_data_projection(self) -> None:
        html = (PROJECT_ROOT / "knowledge/viewer/index.html").read_text(encoding="utf-8")
        javascript = (PROJECT_ROOT / "knowledge/viewer/app.js").read_text(encoding="utf-8")
        self.assertIn('id="data-tab"', html)
        self.assertIn('id="data-targets"', html)
        self.assertIn('/api/data/summary', javascript)


if __name__ == "__main__":
    unittest.main()
