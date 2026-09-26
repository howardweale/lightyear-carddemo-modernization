import unittest
from lightyear_calibration.native_execution import oracle_statements
from lightyear_calibration.contracts import CalibrationError

class ExactOracleDispatchTests(unittest.TestCase):
    def test_literal_spaces_newlines_and_semicolons_are_preserved(self):
        sql="SET DEFINE OFF\nSET SQLBLANKLINES ON\nINSERT INTO t VALUES ('a; \nb''c');\n"
        self.assertEqual(["INSERT INTO t VALUES ('a; \nb''c')"],oracle_statements(sql))
    def test_procedure_keeps_internal_terminators(self):
        self.assertEqual(['BEGIN NULL; END;'],oracle_statements('BEGIN NULL; END;\n/\n'))
    def test_type_and_function_are_separate_slash_terminated_units(self):
        sql="CREATE TYPE T AS TABLE OF VARCHAR2(40)\n/\nCREATE OR REPLACE FUNCTION f RETURN T AS v T:=T(); BEGIN RETURN v; END;\n/\n"
        self.assertEqual(['CREATE TYPE T AS TABLE OF VARCHAR2(40)','CREATE OR REPLACE FUNCTION f RETURN T AS v T:=T(); BEGIN RETURN v; END;'],oracle_statements(sql))
    def test_slash_literal_is_not_a_block_terminator(self):
        sql="BEGIN x :=\n'/'\n; END;\n/\n"
        self.assertEqual(["BEGIN x :=\n'/'\n; END;"],oracle_statements(sql))

    def test_known_display_settings_do_not_change_statement_bytes(self):
        sql="SET ECHO OFF\nSET SERVEROUTPUT ON SIZE 1000000\nSET PAGESIZE 999\nSET LINESIZE 32000\nSELECT 1 FROM dual;"
        self.assertEqual(['SELECT 1 FROM dual'],oracle_statements(sql))

    def test_empty_delimiters_and_display_terminator_do_not_repeat_sql(self):
        self.assertEqual(['SELECT 1 FROM dual','SELECT 2 FROM dual'],oracle_statements('SET SERVEROUTPUT on;\nSELECT 1 FROM dual;\n;\nSELECT 2 FROM dual;'))

    def test_ambiguous_or_client_commands_fail_closed(self):
        for sql in ['@other.sql\n', 'SET DEFINE ON\n', 'SELECT 1 FROM dual', 'BEGIN NULL; END;', 'SELECT 1 FROM dual;\n/\n']:
            with self.subTest(sql=sql),self.assertRaises(CalibrationError):oracle_statements(sql)
