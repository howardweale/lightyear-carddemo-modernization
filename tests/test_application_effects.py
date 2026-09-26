"""Application rules do not suppress business values or unmeasured failures."""
import unittest
from lightyear_calibration.application_effects import audit_rule, decimal_text_equal


class ApplicationEffectTests(unittest.TestCase):
    def rule(self, table, column, oracle, postgresql, **overrides):
        options = {'new_row': True, 'unique_uuid': True,
                   'windows': {lane: {'started_at': '2026-09-26T12:00:00+00:00',
                                     'finished_at': '2026-09-26T12:01:00+00:00'} for lane in ('oracle','postgresql')},
                   'runtime_facts': {}, 'previous': {}}
        options.update(overrides)
        return audit_rule(table, column, {'oracle': oracle, 'postgresql': postgresql}, **options)

    def test_only_exact_numeric_rendering_in_workflow_text(self):
        self.assertTrue(decimal_text_equal('400001: Payment=20,Write-off=0', '400001: Payment=20.0,Write-off=0.0'))
        self.assertFalse(decimal_text_equal('400001: Payment=20', '400002: Payment=20.0'))
        self.assertFalse(decimal_text_equal('Payment=20', 'Refund=20.0'))
        self.assertFalse(decimal_text_equal('Payment=20', 'Payment=21.0'))
        self.assertIsNone(self.rule('c_invoice', 'description', 'Amount 20', 'Amount 20.0'))

    def test_duplicate_invalid_or_existing_uuids_are_not_admitted(self):
        a, b = '550e8400-e29b-41d4-a716-446655440000', '550e8400-e29b-41d4-a716-446655440001'
        self.assertIsNotNone(self.rule('c_order', 'c_order_uu', a, b))
        self.assertIsNone(self.rule('c_order', 'c_order_uu', a, 'invalid'))
        self.assertIsNone(self.rule('c_order', 'c_order_uu', a, b, new_row=False))
        self.assertIsNone(self.rule('c_order', 'c_order_uu', a, b, unique_uuid=False))

    def test_clock_window_and_original_creation_time_are_protected(self):
        a, b = '2026-09-26T12:00:05', '2026-09-26T12:00:06.123'
        self.assertIsNotNone(self.rule('c_order', 'created', a, b))
        self.assertIsNone(self.rule('c_order', 'created', a, b, new_row=False))
        self.assertIsNone(self.rule('c_order', 'dateordered', a, b))
        self.assertIsNone(self.rule('c_order', 'updated', a, '2026-09-26T13:00:00'))

    def test_elapsed_time_needs_a_nonnegative_bound(self):
        self.assertIsNotNone(self.rule('ad_wf_eventaudit', 'elapsedtimems', 24, 40))
        for value in (-1, 60001, True, '24'):
            self.assertIsNone(self.rule('ad_wf_eventaudit', 'elapsedtimems', value, 40))

    def test_business_values_and_new_issues_have_no_rule(self):
        self.assertIsNone(self.rule('c_invoice', 'grandtotal', 20, 21))
        self.assertIsNone(self.rule('ad_issue', 'issuesummary', 'failed', 'passed'))
        self.assertIsNone(self.rule('unknown_table', 'updated', '2026-09-26T12:00:05', '2026-09-26T12:00:06'))

    def test_database_identity_must_match_independent_runtime_facts(self):
        facts = {'oracle': {'expected_database_address': 'oracle-target', 'native_database_instance': 'native-name'},
                 'postgresql': {'expected_database_address': 'pg-target'}}
        self.assertIsNotNone(self.rule('ad_system', 'dbaddress', 'oracle-target', 'pg-target', runtime_facts=facts))
        self.assertIsNone(self.rule('ad_system', 'dbaddress', 'different-target', 'pg-target', runtime_facts=facts))
        self.assertIsNotNone(self.rule('ad_system', 'dbinstance', 'native-name', 'seed-name', runtime_facts=facts,
                                      previous={'postgresql': {'dbinstance': 'seed-name'}}))
        self.assertIsNone(self.rule('ad_system', 'dbinstance', 'native-name', 'changed-name', runtime_facts=facts,
                                   previous={'postgresql': {'dbinstance': 'seed-name'}}))


if __name__ == '__main__': unittest.main()
