"""Constraint controls must reject for the intended reason and roll back."""
from unittest.mock import Mock
import unittest

from lightyear_calibration.schema_constraint_probes import run_update


class Cursor:
    def __init__(self, fail_at=None, code=None, rowcount=1):
        self.statements = []
        self.fail_at = fail_at
        self.code = code
        self.rowcount = rowcount

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql):
        self.statements.append(sql)
        if sql == self.fail_at:
            error = RuntimeError('test driver failure')
            error.sqlstate = self.code
            raise error


class ConstraintProbeTests(unittest.TestCase):
    def run_case(self, cursor, expected):
        connection = Mock()
        connection.cursor.return_value = cursor
        result = run_update(connection, 'postgresql', 'UPDATE fixed_table', expected)
        self.assertIn('ROLLBACK TO SAVEPOINT ly_constraint_probe', cursor.statements)
        return result

    def test_arbitrary_error_is_never_a_successful_rejection(self):
        result = self.run_case(Cursor('UPDATE fixed_table', '08006'), 'foreign-key')
        self.assertEqual('probe-error', result['outcome']['status'])
        self.assertFalse(result['expectation_met'])

    def test_wrong_constraint_rejection_does_not_pass(self):
        result = self.run_case(Cursor('UPDATE fixed_table', '23502'), 'foreign-key')
        self.assertFalse(result['expectation_met'])

    def test_deferred_rejection_is_observed_before_rollback(self):
        result = self.run_case(Cursor('SET CONSTRAINTS ALL IMMEDIATE', '23503'), 'foreign-key')
        self.assertTrue(result['expectation_met'])

    def test_zero_row_update_is_not_a_positive_control(self):
        self.assertFalse(self.run_case(Cursor(rowcount=0), 'accept')['expectation_met'])
        self.assertTrue(self.run_case(Cursor(rowcount=1), 'accept')['expectation_met'])

    def test_acceptance_is_a_failed_negative_control(self):
        self.assertFalse(self.run_case(Cursor(), 'not-null')['expectation_met'])


if __name__ == '__main__': unittest.main()
