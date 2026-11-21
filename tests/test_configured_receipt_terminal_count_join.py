"""CI-only count-report relationships over untrusted mappings; not admitted evidence."""
from copy import deepcopy
import os, unittest
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_execution.configured_terminal_preflight_join import match_terminal_count_accounting


def sealed(value):
    value['content_sha256'] = canonical_hash(value, {'content_sha256'})
    return value


class TerminalCountAccountingRelationships(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        # Deliberately untrusted stand-ins for the result of the original replay.
        # The public reader must run that native replay itself, never accept this
        # mapping or a caller-supplied report as evidence of controller origin.
        self.report = sealed(dict(schema='factory-conservative-financial-accounting/1',
            generation_logical_cost_usd='0', count_account={'count_exposure_usd': '0.25'},
            pending_generation_reserve_usd='0.5', combined_conservative_cost_usd='0.75',
            billing_final=False, actual_provider_cost_usd=None,
            pending_count_before_send=False))
        self.replay = {'count_financial_accounting': deepcopy(self.report)}
        self.receipt = {'status': 'blocked', 'run_id': 'drill-'+'a'*32,
            'count_financial_accounting': deepcopy(self.report)}

    def check(self):
        return match_terminal_count_accounting(self.receipt, self.replay)

    def special(self):
        return dict(status='blocked', reason='factory-isolation-run-refused',
            qualifies_for_factory_receipt=False,
            failure_accounting=dict(schema='factory-sanitized-accounting/1', calls=0,
                input_tokens=0, output_tokens=0, estimated_cost_usd=0, duration_ms=23,
                duration_basis='observed-through-checkpoint', call_hashes=[], scanned_transports=[],
                in_flight_final_usage='unknown', billing_final=False))

    def test_equal_reports_are_read_only_for_passed_or_blocked_receipt(self):
        for status in ('passed', 'blocked'):
            self.receipt['status'] = status
            before = deepcopy((self.receipt, self.replay))
            self.assertIsNone(self.check())
            self.assertEqual((self.receipt, self.replay), before)
            self.assertNotIn('production_controller_receipt', self.receipt)

    def test_resealed_cost_or_pending_report_substitution_refuses(self):
        for key, value in (('combined_conservative_cost_usd', '0'),
                ('pending_generation_reserve_usd', '0'), ('pending_count_before_send', True),
                ('count_account', {'count_exposure_usd': '0'})):
            report = deepcopy(self.report);report[key] = value
            self.receipt['count_financial_accounting'] = sealed(report)
            with self.assertRaisesRegex(ContractError, 'count-report-binding'): self.check()

    def test_boolean_integer_substitution_is_not_mapping_equality(self):
        report = deepcopy(self.report);report['billing_final'] = 0
        self.receipt['count_financial_accounting'] = sealed(report)
        with self.assertRaisesRegex(ContractError, 'count-report-binding'): self.check()

    def test_missing_full_receipt_report_refuses(self):
        self.receipt.pop('count_financial_accounting')
        for status in ('passed', 'blocked'):
            self.receipt['status'] = status
            with self.assertRaisesRegex(ContractError, 'count-report-missing'): self.check()

    def test_native_special_absence_stays_absent_and_unknown(self):
        self.receipt = self.special();before = deepcopy((self.receipt, self.replay))
        self.assertIsNone(self.check())
        self.assertEqual((self.receipt, self.replay), before)
        self.assertNotIn('count_financial_accounting', self.receipt)
        self.assertEqual(self.receipt['failure_accounting']['in_flight_final_usage'], 'unknown')

    def test_special_exception_requires_native_shape(self):
        for key, value in (('status', 'passed'), ('reason', 'other'),
                ('qualifies_for_factory_receipt', 0), ('run_id', 'drill-'+'a'*32),
                ('execution_security', {}), ('intelligence', {})):
            self.receipt = self.special();self.receipt[key] = value
            with self.assertRaisesRegex(ContractError, 'count-report-missing'): self.check()
        self.receipt = self.special();self.receipt['failure_accounting'] = {}
        with self.assertRaisesRegex(ContractError, 'reconciliation-accounting-shape'): self.check()

    def test_present_null_or_corrupt_report_cannot_use_absence_exception(self):
        for report in (None, [], dict(self.report, content_sha256='f'*64)):
            self.receipt = self.special();self.receipt['count_financial_accounting'] = report
            with self.assertRaisesRegex(ContractError, 'count-report-digest'): self.check()

    def test_missing_or_changed_native_replay_report_refuses(self):
        for replay in ({}, {'count_financial_accounting': None},
                {'count_financial_accounting': dict(self.report, content_sha256='f'*64)}):
            self.replay = replay
            with self.assertRaisesRegex(ContractError, 'count-replay'): self.check()
