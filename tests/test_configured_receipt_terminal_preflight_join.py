"""CI-only terminal mapping relationships; no fabricated passed context or outcome."""
from copy import deepcopy
import os, unittest
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_execution.configured_terminal_preflight_join import match_terminal_records


def seal(value):
    value['content_sha256'] = canonical_hash(value, {'content_sha256'})
    return value


class TerminalPreflightRelationships(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.admission = seal(dict(schema='factory-human-drill-context-admission/1',
            status='passed', stub_only=False, output_qualified=False, resume_allowed=False,
            nonce_sha256='a'*64, work_order_sha256='b'*64))
        self.identity = seal(dict(schema='factory-attempt-identity/1', attempt_id='drill-'+'a'*32,
            consumed_nonce_sha256='a'*64, admission_receipt_sha256=self.admission['content_sha256'],
            work_order_sha256='b'*64, workspace_inventory_sha256='c'*64))
        self.events = []
        for kind, payload in (
            ('work_order_accepted', dict(work_order_sha256='b'*64)),
            ('hardened_admission_bound', dict(admission_receipt_sha256=self.admission['content_sha256'])),
            ('workspace_read_manifest', dict(sha256='c'*64)),
            ('controller_error', dict(reason='public unsigned fixture'))):
            row = dict(sequence=len(self.events)+1, state='BLOCKED', kind=kind, payload=payload,
                previous_sha256=self.events[-1]['event_sha256'] if self.events else None)
            row['event_sha256'] = canonical_hash(row); self.events.append(row)
        self.receipt = seal(dict(receipt_type='lightyear-autonomous-factory-run', status='blocked',
            work_order_sha256='b'*64, ledger_head_sha256=self.events[-1]['event_sha256']))
        self.summary = dict(status='blocked', receipt_sha256=self.receipt['content_sha256'])

    def check(self):
        return match_terminal_records(self.admission, self.identity, self.receipt, self.summary, self.events)

    def reseal_receipt(self):
        seal(self.receipt); self.summary['receipt_sha256'] = self.receipt['content_sha256']

    def test_native_isolation_receipt_shape_needs_no_invented_run_id(self):
        before = deepcopy((self.admission, self.identity, self.receipt, self.summary, self.events))
        self.assertIsNone(self.check())
        self.assertEqual((self.admission, self.identity, self.receipt, self.summary, self.events), before)
        self.assertNotIn('run_id', self.receipt)
        self.assertNotIn('production_controller_receipt', self.receipt)

    def test_present_wrong_run_id_and_work_order_refuse(self):
        for key, value in (('run_id', 'drill-'+'d'*32), ('work_order_sha256', 'd'*64)):
            original = deepcopy(self.receipt); self.receipt[key] = value; self.reseal_receipt()
            with self.assertRaisesRegex(ContractError, 'receipt-binding'): self.check()
            self.receipt = original; self.reseal_receipt()

    def test_changed_unsealed_receipt_refuses(self):
        self.receipt['status'] = 'passed'
        with self.assertRaisesRegex(ContractError, 'record-digest'): self.check()

    def test_summary_status_or_digest_substitution_refuses(self):
        for key, value in (('status', 'passed'), ('receipt_sha256', 'd'*64)):
            before = deepcopy(self.summary); self.summary[key] = value
            with self.assertRaisesRegex(ContractError, 'receipt-binding'): self.check()
            self.summary = before

    def test_identity_admission_nonce_or_attempt_substitution_refuses(self):
        for key, value in (('admission_receipt_sha256', 'd'*64), ('consumed_nonce_sha256', 'd'*64),
                ('attempt_id', 'drill-'+'d'*32)):
            before = deepcopy(self.identity); self.identity[key] = value; seal(self.identity)
            with self.assertRaisesRegex(ContractError, 'identity-binding'): self.check()
            self.identity = before

    def test_duplicate_or_missing_original_ledger_join_refuses(self):
        self.events.append(deepcopy(self.events[0]))
        with self.assertRaisesRegex(ContractError, 'ledger-binding'): self.check()
        self.events.pop(); self.events.pop(0)
        with self.assertRaisesRegex(ContractError, 'ledger-binding'): self.check()

    def test_original_native_receipt_snapshot_required(self):
        self.receipt['ledger_head_sha256'] = 'd'*64; self.reseal_receipt()
        with self.assertRaisesRegex(ContractError, 'public-drill-receipt-snapshot-missing'): self.check()

    def test_passed_receipt_does_not_turn_failed_wrapper_into_authority(self):
        self.receipt['status'] = 'passed'; self.reseal_receipt(); self.summary['status'] = 'passed'
        self.assertIsNone(self.check())
        self.assertNotIn('expectation_met', self.receipt)
