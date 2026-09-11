from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_data.contracts import seal
from lightyear_data.idempiere_comparison import (
    CATEGORIES, PILOT_PATH, POLICY_PATH, RECEIPT_PATH, REPORT_PATH, SCHEMA_PATH,
    build_receipt, compare_pair, policy, validate_stage2_artifacts,
)
from lightyear_data.idempiere_sql import Cursor, Unsupported, lex, literal, parse_script, split_units, type_spec
from lightyear_data.semantic_core import CompatibilityClass


ROOT = Path(__file__).resolve().parents[1]


class IdempiereSqlLexerTests(unittest.TestCase):
    def test_comment_markers_semicolons_and_commas_inside_strings_are_not_sql(self):
        sql = "-- ignored\nINSERT INTO x (a,b) VALUES (';','--,/* x */');\nUPDATE x SET a='it''s;ok';"
        units = parse_script(sql, "oracle")
        self.assertEqual(2, len(units))
        self.assertTrue(all(u.parsed for u in units))
        self.assertEqual(";", units[0].effects[0]["value"]["a"]["value"])
        self.assertEqual("it's;ok", units[1].effects[0]["value"]["assignments"]["a"]["value"])
        self.assertEqual([2, 3], [u.start_line for u in units])

    def test_quote_case_is_preserved_and_unquoted_identifiers_fold(self):
        values = [(t.kind, t.value) for t in lex('ALTER TABLE "Mixed" ADD COL NUMERIC(10);')]
        self.assertIn(("quoted", "Mixed"), values)
        self.assertIn(("word", "col"), values)

    def test_oracle_q_quote_and_postgres_dollar_body_do_not_split(self):
        ora = parse_script("INSERT INTO x(a) VALUES(q'[a'; -- b]');", "oracle")
        self.assertEqual(1, len(ora))
        self.assertTrue(ora[0].parsed)
        pg = parse_script("DO $body$ BEGIN PERFORM 1; PERFORM 2; END; $body$; SELECT unknown();", "postgresql")
        self.assertEqual(2, len(pg))
        self.assertFalse(any(u.parsed for u in pg))

    def test_nested_comments_are_dialect_specific(self):
        sql = "/* a /* b */ c */ ALTER TABLE x ADD y NUMERIC(10);"
        self.assertTrue(parse_script(sql, "postgresql")[0].parsed)
        self.assertEqual("nested-oracle-comment", parse_script(sql, "oracle")[0].lexical_error)

    def test_malformed_lexical_input_is_one_failed_file_unit(self):
        for sql in ("INSERT INTO x(a) VALUES('unterminated);", "/* broken", "DO $x$ broken"):
            with self.subTest(sql=sql):
                units = parse_script(sql, "postgresql")
                self.assertEqual(1, len(units))
                self.assertFalse(units[0].parsed)
                self.assertTrue(units[0].lexical_error)

    def test_procedural_oracle_block_is_opaque_not_inner_dml(self):
        sql = "BEGIN\nUPDATE x SET y=1;\nIF 1=1 THEN NULL; END IF;\nEND;\n/\nALTER TABLE x ADD z NUMBER(10);"
        units = parse_script(sql, "oracle")
        self.assertEqual(2, len(units))
        self.assertEqual("procedural-block", units[0].lexical_error)
        self.assertTrue(units[1].parsed)

    def test_unterminated_block_and_standalone_slash_fail_closed(self):
        self.assertEqual(1, len(parse_script("BEGIN NULL; END; ALTER TABLE x ADD y NUMBER(10);", "oracle")))
        self.assertFalse(parse_script("/\n", "oracle")[0].parsed)
        self.assertFalse(parse_script("ALTER TABLE x ADD y NUMBER(10)", "oracle")[0].parsed)

    def test_crlf_has_same_units_hashes_and_lines(self):
        sql = "-- comment\nALTER TABLE x ADD y NUMBER(10);\n"
        self.assertEqual(split_units(sql, "oracle"), split_units(sql.replace("\n", "\r\n"), "oracle"))

    def test_long_numeric_literals_are_not_rounded_by_decimal_context(self):
        number = "12345678901234567890123456789012345678.1200"
        self.assertEqual(number[:-2], literal(lex(number), "oracle")["value"])
        with self.assertRaises(Unsupported):
            literal(lex("1 2"), "oracle")


class IdempiereSqlProjectionTests(unittest.TestCase):
    def test_finite_decimal_mapping_and_precision_difference(self):
        ora = "ALTER TABLE C_Order ADD Amount NUMBER(10,2);"
        result = compare_pair("test", ora, "ALTER TABLE c_order ADD amount NUMERIC(10,2);")
        self.assertEqual("equivalent", result["verdict"])
        self.assertEqual(CompatibilityClass.NORMALIZED_EQUIVALENT.value, result["compatibility_class"])
        result = compare_pair("test", ora, "ALTER TABLE c_order ADD amount NUMERIC(9,2);")
        self.assertEqual("divergent", result["verdict"])
        self.assertEqual(["declared-type-mismatch"], result["declared_differences"][0]["reason_codes"])

    def test_unbounded_negative_scale_and_nan_domains_not_equated(self):
        for a, b in (("NUMBER", "NUMERIC"), ("NUMBER(10,-2)", "NUMERIC(10,-2)"), ("NUMBER(2,3)", "NUMERIC(2,3)")):
            result = compare_pair("x", f"ALTER TABLE x ADD y {a};", f"ALTER TABLE x ADD y {b};")
            self.assertEqual("indeterminate", result["verdict"])
        self.assertIn("NaN", policy()["finite_numeric_projection"])

    def test_character_and_date_domains_are_policy_not_equivalence(self):
        for a, b in (("VARCHAR2(10)", "VARCHAR(10)"), ("CHAR(1 CHAR)", "CHAR(1)"), ("DATE", "DATE"), ("DATE", "TIMESTAMP"), ("TIMESTAMP(6)", "TIMESTAMP(6)"), ("CLOB", "TEXT")):
            with self.subTest(a=a, b=b):
                result = compare_pair("x", f"ALTER TABLE x ADD y {a};", f"ALTER TABLE x ADD y {b};")
                self.assertEqual("indeterminate", result["verdict"])

    def test_date_projection_preserves_time_and_precision(self):
        ora = type_spec(Cursor(lex("DATE")), "oracle")
        pg = type_spec(Cursor(lex("DATE")), "postgresql")
        self.assertEqual("timestamp", ora["canonical_type"])
        self.assertEqual("date", pg["canonical_type"])

    def test_empty_string_and_null_never_normalize_to_cross_dialect_equivalence(self):
        sql = "ALTER TABLE x MODIFY y DEFAULT '';"
        result = compare_pair("x", sql, "ALTER TABLE x ALTER COLUMN y SET DEFAULT '';")
        self.assertEqual("indeterminate", result["verdict"])
        self.assertEqual({"kind": "null"}, result["declared_differences"][0]["oracle_value"])
        self.assertEqual({"kind": "string", "value": ""}, result["declared_differences"][0]["postgresql_value"])

    def test_default_and_nullability_compare_and_detect_changes(self):
        ora = "ALTER TABLE x MODIFY y DEFAULT 2; ALTER TABLE x MODIFY y NOT NULL;"
        pg = "ALTER TABLE x ALTER COLUMN y SET DEFAULT 2.0; ALTER TABLE x ALTER COLUMN y SET NOT NULL;"
        self.assertEqual("equivalent", compare_pair("x", ora, pg)["verdict"])
        self.assertEqual("divergent", compare_pair("x", ora, pg.replace("SET NOT NULL", "DROP NOT NULL"))["verdict"])

    def test_helper_expands_effects_without_inflating_statement_coverage(self):
        ora = "ALTER TABLE x MODIFY y NUMBER(10) DEFAULT NULL; ALTER TABLE x MODIFY y NULL;"
        pg = "INSERT INTO t_alter_column VALUES('x','y','NUMERIC(10)',NULL,'NULL'); INSERT INTO t_alter_column VALUES('x','y',NULL,'NULL',NULL);"
        result = compare_pair("x", ora, pg)
        self.assertTrue(result["ordered_effects_aligned"])
        self.assertEqual(3, result["compared_effect_count"])
        self.assertEqual(2, result["coverage"]["postgresql"]["sql_units"])
        self.assertEqual("indeterminate", result["verdict"])
        self.assertIn("helper-catalog-and-dependent-view-effects", result["segments"]["postgresql"][0]["reason_codes"])

    def test_helper_default_is_quoted_and_null_slots_are_distinct(self):
        units = parse_script("INSERT INTO t_alter_column VALUES('X','Y',NULL,NULL,'0');", "postgresql")
        self.assertEqual({"kind": "string", "value": "0"}, units[0].effects[0]["value"])
        self.assertEqual("x.y", units[0].effects[0]["target"])
        bad = "INSERT INTO t_alter_column VALUES('X','Y',NULL,'garbage',NULL);"
        self.assertFalse(parse_script(bad, "postgresql")[0].parsed)

    def test_full_consumption_rejects_trailing_options_and_multiple_rows(self):
        cases = ("ALTER TABLE x ADD y NUMERIC(10) GARBAGE;", "CREATE INDEX a ON x(y) WHERE y>1;", "INSERT INTO x(a) VALUES(1),(2);", "ALTER TABLE x ADD y NUMERIC(10) DEFAULT 1 NOT NULL NOT NULL;", "CREATE TABLE x (a NUMERIC(10),a NUMERIC(10));")
        for sql in cases:
            with self.subTest(sql=sql):
                self.assertFalse(parse_script(sql, "postgresql")[0].parsed)

    def test_dialect_specific_syntax_cannot_be_cross_admitted(self):
        self.assertFalse(parse_script("ALTER TABLE x ADD (a NUMERIC(10));", "postgresql")[0].parsed)
        self.assertFalse(parse_script("ALTER TABLE x ADD COLUMN a NUMBER(10);", "oracle")[0].parsed)
        self.assertFalse(parse_script("CREATE INDEX x ON y(a DESC ASC);", "postgresql")[0].parsed)

    def test_grouped_column_modification_aligns_with_multiple_pg_statements(self):
        ora = "ALTER TABLE x MODIFY (a NUMBER(10),b NUMBER(8));"
        pg = "ALTER TABLE x ALTER COLUMN a TYPE NUMERIC(10); ALTER TABLE x ALTER COLUMN b TYPE NUMERIC(8);"
        result = compare_pair("x", ora, pg)
        self.assertEqual("equivalent", result["verdict"])
        self.assertEqual(1, result["coverage"]["oracle"]["sql_units"])
        self.assertEqual(2, result["coverage"]["postgresql"]["sql_units"])

    def test_constraints_indexes_and_drops_retain_catalog_obligations(self):
        cases = ("ALTER TABLE x ADD CONSTRAINT pk PRIMARY KEY(y);", "ALTER TABLE x ADD CONSTRAINT fk FOREIGN KEY(y) REFERENCES z(id) ON DELETE CASCADE;", "CREATE UNIQUE INDEX ix ON x(y DESC);", "DROP TABLE x;")
        for sql in cases:
            with self.subTest(sql=sql):
                self.assertTrue(parse_script(sql, "postgresql")[0].parsed)
                self.assertEqual("indeterminate", compare_pair("x", sql, sql)["verdict"])

    def test_identical_dml_and_unknown_functions_are_not_equivalence(self):
        for sql in ("INSERT INTO x(a) VALUES(1);", "UPDATE x SET a=1 WHERE id=2;", "DELETE FROM x WHERE id=1;", "UPDATE x SET a=SYSDATE;", "UPDATE x SET a=TO_DATE('2026-01-01','YYYY-MM-DD');"):
            with self.subTest(sql=sql):
                result = compare_pair("x", sql, sql)
                self.assertEqual("indeterminate", result["verdict"])
                self.assertEqual(1, result["coverage"]["oracle"]["parsed-but-indeterminate"])

    def test_predicate_and_missing_where_are_distinct_and_not_dropped(self):
        with_where = parse_script("UPDATE x SET y=1 WHERE id=7;", "oracle")[0]
        without = parse_script("UPDATE x SET y=1;", "oracle")[0]
        self.assertEqual("opaque", with_where.effects[0]["value"]["predicate"]["kind"])
        self.assertEqual("all-rows", without.effects[0]["value"]["predicate"]["kind"])
        self.assertFalse(parse_script("UPDATE x SET y=1 WHERE;", "oracle")[0].parsed)
        self.assertFalse(parse_script("UPDATE x SET y=1,y=2;", "oracle")[0].parsed)

    def test_order_missing_effects_and_duplicate_writes_are_not_collapsed(self):
        ora = "ALTER TABLE x MODIFY y DEFAULT 1; ALTER TABLE x MODIFY y DEFAULT 2;"
        pg = "ALTER TABLE x ALTER COLUMN y SET DEFAULT 2; ALTER TABLE x ALTER COLUMN y SET DEFAULT 1;"
        self.assertEqual("divergent", compare_pair("x", ora, pg)["verdict"])
        self.assertEqual("indeterminate", compare_pair("x", ora, pg.split(";")[0] + ";")["verdict"])

    def test_quoted_identifier_and_literal_content_are_not_casefolded(self):
        self.assertEqual("indeterminate", compare_pair("x", 'ALTER TABLE "X" ADD y NUMBER(10);', 'ALTER TABLE "x" ADD y NUMERIC(10);')["verdict"])
        self.assertEqual("divergent", compare_pair("x", "ALTER TABLE x MODIFY y DEFAULT 'ABC';", "ALTER TABLE x ALTER COLUMN y SET DEFAULT 'abc';")["verdict"])

    def test_known_administration_excluded_but_unknown_session_command_retained(self):
        ora = "SET DEFINE OFF\nSET SQLBLANKLINES ON\nSELECT register_migration_script('one.sql') FROM dual;\nALTER TABLE x ADD y NUMBER(10);"
        pg = "SELECT register_migration_script('two.sql') FROM dual;\nALTER TABLE x ADD y NUMERIC(10);"
        result = compare_pair("x", ora, pg)
        self.assertEqual("equivalent", result["verdict"])
        self.assertEqual(3, result["coverage"]["oracle"]["administrative_units_excluded"])
        self.assertEqual(1, result["coverage"]["oracle"]["sql_units"])
        self.assertEqual("indeterminate", compare_pair("x", "SET DEFINE ON\n" + ora, pg)["verdict"])

    def test_comment_or_admin_only_cannot_claim_equivalence(self):
        self.assertEqual("indeterminate", compare_pair("x", "-- x", "-- x")["verdict"])
        sql = "SELECT register_migration_script('x.sql') FROM dual;"
        self.assertEqual("indeterminate", compare_pair("x", sql, sql)["verdict"])

    def test_parser_and_comparator_never_enter_model_workcell(self):
        with patch("lightyear_factory.agents.ModelAgentSet.plan", side_effect=AssertionError("model called")), patch("lightyear_factory.agents.ModelAgentSet.analyze_failure", side_effect=AssertionError("model called")), patch("lightyear_factory.agents.ModelAgentSet.build", side_effect=AssertionError("builder called")):
            self.assertEqual("equivalent", compare_pair("x", "ALTER TABLE x ADD y NUMBER(10);", "ALTER TABLE x ADD y NUMERIC(10);")["verdict"])


class IdempiereComparisonEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = {p.name: json.loads((ROOT / p).read_text(encoding="utf-8")) for p in (POLICY_PATH, PILOT_PATH, REPORT_PATH, RECEIPT_PATH)}

    def test_committed_reports_verify(self):
        self.assertEqual([], validate_stage2_artifacts(ROOT))

    def test_policy_uses_portable_semantic_core_path(self):
        self.assertEqual(
            "data-modernization/semantic-core/database-semantic-core.json",
            policy()["semantic_core"],
        )

    def test_pilot_is_first_and_full_denominator_is_preserved(self):
        pilot, report = self.artifacts[PILOT_PATH.name], self.artifacts[REPORT_PATH.name]
        self.assertEqual(93, len(pilot["results"]))
        self.assertEqual(1078, len(report["results"]))
        self.assertEqual(pilot["results"], report["results"][:93])
        self.assertEqual(pilot["content_sha256"], report["pilot_content_sha256"])

    def test_sql_denominator_excludes_admin_and_is_not_token_occurrences(self):
        report = self.artifacts[REPORT_PATH.name]
        for c in report["statistics"]["coverage_by_dialect"].values():
            self.assertEqual(c["sql_units"], sum(c[k] for k in CATEGORIES))
            self.assertEqual(c["input_units"], c["sql_units"] + c["administrative_units_excluded"])
        self.assertIn("NOT token occurrences", policy()["coverage_unit"])

    def test_no_runtime_agent_or_completion_claims(self):
        report = self.artifacts[REPORT_PATH.name]
        self.assertEqual(0, report["model_calls"])
        self.assertTrue(report["claims"]["deterministic_sweep_complete"])
        self.assertFalse(any(v for k, v in report["claims"].items() if k != "deterministic_sweep_complete"))
        receipt = self.artifacts[RECEIPT_PATH.name]
        self.assertFalse(receipt["ms70_handoff"]["ready_for_unattended_model_sweep"])
        self.assertEqual(0, receipt["ms70_handoff"]["work_orders_created"])

    def test_hash_binding_denominator_and_claim_tampering_rejected(self):
        mutations = (
            lambda r: r.update(model_calls=1),
            lambda r: r["claims"].update(production_ready=True),
            lambda r: r["results"].pop(),
            lambda r: r["bindings"].update(source_commit="0" * 40),
            lambda r: r["statistics"].update(pairs=1),
        )
        for mutate in mutations:
            docs = copy.deepcopy(self.artifacts)
            mutate(docs[REPORT_PATH.name])
            docs[REPORT_PATH.name] = seal(docs[REPORT_PATH.name])
            self.assertTrue(validate_stage2_artifacts(ROOT, artifacts=docs))

    def test_resealed_unknown_to_equivalent_promotion_rejected(self):
        docs = copy.deepcopy(self.artifacts)
        report = docs[REPORT_PATH.name]
        result = next(r for r in report["results"] if r["verdict"] == "indeterminate")
        result["verdict"] = "equivalent"
        result.update(seal(result))
        report.update(seal(report))
        docs[RECEIPT_PATH.name] = build_receipt(docs[PILOT_PATH.name], report)
        self.assertIn("stage2-verdict-promotion-invalid", validate_stage2_artifacts(ROOT, artifacts=docs))

    def test_receipt_or_policy_changes_rejected(self):
        for name in (RECEIPT_PATH.name, POLICY_PATH.name):
            docs = copy.deepcopy(self.artifacts)
            docs[name]["milestone"] = 70
            docs[name] = seal(docs[name])
            self.assertTrue(validate_stage2_artifacts(ROOT, artifacts=docs))

    def test_schema_required_fields_are_declared(self):
        schema = json.loads((ROOT / SCHEMA_PATH).read_text())
        def walk(value):
            if isinstance(value, dict):
                if "required" in value:
                    self.assertLessEqual(set(value["required"]), set(value["properties"]))
                for sub in value.values():
                    walk(sub)
            elif isinstance(value, list):
                for sub in value:
                    walk(sub)
        walk(schema)


if __name__ == "__main__":
    unittest.main()
