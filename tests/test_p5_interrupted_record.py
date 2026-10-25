"""Synthetic CI only: unsigned abort records do not constitute human attestation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator, _ControllerAttemptLease
from lightyear_control_tower.factory_policy import validate_contract


class InterruptedRecordTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.temp = tempfile.TemporaryDirectory(prefix='p5-unsigned-abort-ci-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root/'attempt-001'
        self.run.mkdir()
        self.bindings = dict(work_order_sha256='1'*64,
            consumed_nonce_sha256=hashlib.sha256(b'synthetic-consumed-nonce').hexdigest(),
            sealed_workspace_sha256='2'*64)
        identity = dict(schema='factory-attempt-identity/1', attempt_id=self.run.name,
            **self.bindings, admission_receipt_sha256='3'*64, workspace_inventory_sha256='4'*64)
        identity['content_sha256'] = canonical_hash(identity)
        (self.run/'attempt-identity.json').write_text(json.dumps(identity), encoding='utf-8')
        (self.root/'admission-nonces.sha256').write_text(self.bindings['consumed_nonce_sha256']+'\n', encoding='ascii')
        ledger = RunLedger(self.run/'events.jsonl')
        ledger.append('ACCEPTED','hardened_admission_bound',dict(admission_receipt_sha256='3'*64))
        ledger.append('ACCEPTED','workspace_read_manifest',dict(sha256='4'*64))
        ledger.append('ACCEPTED','work_order_accepted',dict(work_order_sha256='1'*64))
        self.accounting = dict(schema='factory-sanitized-accounting/1', calls=1,
            input_tokens=12, output_tokens=3, estimated_cost_usd=.01,
            duration_ms=25, duration_basis='observed-through-checkpoint',
            call_hashes=[dict(request_sha256='5'*64,response_sha256='6'*64)],
            scanned_transports=[dict(role='builder',prompt_sha256='7'*64,response_sha256=None)],
            in_flight_final_usage='unknown',billing_final=False)
        RunLedger(self.run/'attempt-accounting.jsonl').append('OBSERVED','sanitized_accounting',
            dict(attempt_identity_sha256=identity['content_sha256'],accounting=self.accounting))
        with _ControllerAttemptLease(self.root,self.run.name,create=True):
            pass

    def reconcile(self):
        return FactoryOrchestrator.reconcile_interrupted(self.root,self.run.name,**self.bindings)

    def test_abort_appends_once_and_preserves_consumed_nonce_and_original_prefix(self):
        before=(self.run/'events.jsonl').read_bytes()
        nonce=(self.root/'admission-nonces.sha256').read_bytes()
        event=self.reconcile()
        self.assertEqual(event['state'],'INTERRUPTED')
        self.assertEqual(event['payload']['status'],'interrupted; awaiting human attestation')
        self.assertEqual(event['payload']['accounting'],self.accounting)
        self.assertTrue(event['payload']['unsigned'])
        self.assertIsNone(event['payload']['human_attestation'])
        self.assertTrue((self.run/'events.jsonl').read_bytes().startswith(before))
        after=(self.run/'events.jsonl').read_bytes()
        self.assertTrue(RunLedger(self.run/'events.jsonl').verify())
        with self.assertRaisesRegex(ContractError,'terminal-attempt-refused'):
            self.reconcile()
        self.assertEqual(after,(self.run/'events.jsonl').read_bytes())
        self.assertEqual(nonce,(self.root/'admission-nonces.sha256').read_bytes())

    def test_live_controller_missing_nonce_and_corruption_refuse(self):
        before=(self.run/'events.jsonl').read_bytes()
        with _ControllerAttemptLease(self.root,self.run.name,create=False):
            with self.assertRaises(ContractError):self.reconcile()
        (self.root/'admission-nonces.sha256').write_text('8'*64+'\n',encoding='ascii')
        with self.assertRaisesRegex(ContractError,'consumed-nonce-required'):self.reconcile()
        (self.root/'admission-nonces.sha256').write_text(self.bindings['consumed_nonce_sha256']+'\n',encoding='ascii')
        with (self.run/'attempt-accounting.jsonl').open('ab') as stream:stream.write(b'{')
        with self.assertRaisesRegex(ContractError,'incomplete-ledger'):self.reconcile()
        self.assertEqual(before,(self.run/'events.jsonl').read_bytes())

    def test_terminal_receipt_and_wrong_binding_refuse(self):
        (self.run/'receipt.json').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ContractError,'terminal-attempt-refused'):self.reconcile()
        wrong=dict(self.bindings,work_order_sha256='9'*64)
        with self.assertRaisesRegex(ContractError,'identity-binding'):
            FactoryOrchestrator.reconcile_interrupted(self.root,self.run.name,**wrong)

    def test_cli_abort_does_not_admit_or_construct_models(self):
        from lightyear_factory.cli import main
        args=['reconcile-interrupted','--runs-root',str(self.root),'--run-id',self.run.name]
        for name,value in self.bindings.items():args.extend(['--'+name.replace('_','-'),value])
        with patch('lightyear_factory.cli.verify_work_order',side_effect=AssertionError('new admission')), \
             patch('lightyear_factory.cli.AdmissionNonceStore',side_effect=AssertionError('nonce mutation')), \
             patch('lightyear_factory.cli.OpenAIAgentSet',side_effect=AssertionError('model construction')), \
             patch('builtins.print'):
            self.assertEqual(main(args),0)

    def test_real_controller_kill_abort_and_duplicate(self):
        from tools.ci.p5_fixture import Fixture
        from tools.ci.p5_controller_probe import observe
        repository=Path(__file__).resolve().parents[1]
        parent=self.root/'controller-integration';parent.mkdir()
        fixture=Fixture(parent,repository)
        try:
            observed,passed,gaps=observe(fixture,repository)
            self.assertTrue(passed)
            self.assertTrue(observed['consumed_nonce_unchanged'])
            self.assertTrue(observed['terminal_abort_refused'])
            self.assertTrue(observed['reentry_refused'])
            self.assertFalse(observed['human_attestation_verified'])
            self.assertTrue(gaps)  # Never qualify the unresolved human attestation.
        finally:
            fixture.close()

    def test_existing_tower_has_no_interruption_attestation_kind(self):
        contract=dict(schema='factory-contract/1',kind='factory-interruption-attestation',
            program='factory',sources=[dict(path='docs/factory/interrupted.json',sha256='1'*64,commit='2'*40)],
            details=dict(record_sha256='3'*64))
        with self.assertRaises(ValueError):validate_contract(contract,check_evidence=False)
        # Refusal is a measured gap, not an accepted attestation or a passing P5 qualification.


if __name__=='__main__':
    unittest.main()
