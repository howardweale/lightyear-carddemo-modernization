"""CI-only original checkpoint relationships; mappings supply no origin authority."""
from copy import deepcopy
import os, unittest
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_terminal_preflight_join import match_terminal_failure_accounting


class TerminalFailureAccountingRelationships(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.checkpoint = dict(schema='factory-sanitized-accounting/1', calls=1,
            input_tokens=20, output_tokens=4, estimated_cost_usd=0.25, duration_ms=40,
            duration_basis='observed-through-checkpoint',
            call_hashes=[dict(request_sha256='a'*64, response_sha256='b'*64)],
            scanned_transports=[dict(role='builder',prompt_sha256='c'*64,response_sha256=None)],
            in_flight_final_usage='unknown', billing_final=False)
        self.events = [dict(kind='sanitized_accounting', payload={'accounting': deepcopy(self.checkpoint)})]
        self.receipt = dict(status='blocked', failure_accounting=deepcopy(self.checkpoint))
        self.receipt['failure_accounting']['duration_ms'] = 43

    def check(self):
        return match_terminal_failure_accounting(self.receipt, self.events)

    def test_elapsed_growth_or_equality_preserves_original_values(self):
        for duration in (40, 43):
            self.receipt['failure_accounting']['duration_ms'] = duration
            before = deepcopy((self.receipt,self.events))
            self.assertIsNone(self.check())
            self.assertEqual((self.receipt,self.events),before)
            self.assertEqual(self.receipt['failure_accounting']['in_flight_final_usage'],'unknown')
            self.assertNotIn('production_controller_receipt',self.receipt)

    def test_duration_regression_refuses(self):
        self.receipt['failure_accounting']['duration_ms'] = 39
        with self.assertRaisesRegex(ContractError,'failure-checkpoint-binding'): self.check()

    def test_tokens_cost_or_hash_substitution_refuses(self):
        for key,value in (('input_tokens',21),('output_tokens',5),('estimated_cost_usd',0.5),
                ('call_hashes',[dict(request_sha256='d'*64,response_sha256='b'*64)])):
            report=deepcopy(self.checkpoint);report[key]=value;self.receipt['failure_accounting']=report
            with self.assertRaisesRegex(ContractError,'failure-checkpoint-binding'): self.check()

    def test_unknown_usage_or_scan_substitution_refuses(self):
        for key,value in (('in_flight_final_usage','none'),('scanned_transports',[])):
            report=deepcopy(self.checkpoint);report[key]=value;self.receipt['failure_accounting']=report
            with self.assertRaisesRegex(ContractError,'failure-checkpoint-binding'): self.check()

    def test_latest_checkpoint_required_not_earlier_matching_one(self):
        later=deepcopy(self.checkpoint);later['input_tokens']=21
        self.events.append(dict(kind='sanitized_accounting',payload={'accounting':later}))
        with self.assertRaisesRegex(ContractError,'failure-checkpoint-binding'): self.check()

    def test_missing_or_malformed_original_checkpoint_refuses(self):
        self.events=[]
        with self.assertRaisesRegex(ContractError,'failure-checkpoint-missing'): self.check()
        self.events=[dict(kind='sanitized_accounting',payload={'accounting':{}})]
        with self.assertRaisesRegex(ContractError,'reconciliation-accounting-shape'): self.check()

    def test_native_shape_validation_and_numeric_representation(self):
        self.receipt['failure_accounting']['billing_final']=0
        with self.assertRaisesRegex(ContractError,'reconciliation-accounting-cost'): self.check()
        self.receipt['failure_accounting']=deepcopy(self.checkpoint)
        self.checkpoint['estimated_cost_usd']=0
        self.events[0]['payload']['accounting']=deepcopy(self.checkpoint)
        self.receipt['failure_accounting']['estimated_cost_usd']=0.0
        with self.assertRaisesRegex(ContractError,'failure-checkpoint-binding'): self.check()

    def test_absent_failure_snapshot_is_not_synthesized(self):
        for status in ('passed','blocked'):
            self.receipt={'status':status};before=deepcopy((self.receipt,self.events))
            self.assertIsNone(self.check())
            self.assertEqual((self.receipt,self.events),before)
            self.assertNotIn('failure_accounting',self.receipt)
        self.receipt['failure_accounting']=None
        with self.assertRaisesRegex(ContractError,'reconciliation-accounting-shape'): self.check()
