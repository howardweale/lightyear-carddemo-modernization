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


    def test_cli_refusal_prints_only_code_and_suppresses_sensitive_errors(self):
        import contextlib
        import io
        from lightyear_factory.cli import main
        args=['reconcile-interrupted','--runs-root',str(self.root),'--run-id',self.run.name]
        for name,value in self.bindings.items():args.extend(['--'+name.replace('_','-'),value])
        for error,expected in ((ContractError('reconciliation-terminal-attempt-refused'),
                                'reconciliation-terminal-attempt-refused'),
                               (ContractError('private C:/secret/material'), 'reconciliation-refused'),
                               (OSError('private C:/secret/material'), 'reconciliation-refused')):
            with self.subTest(error_type=type(error).__name__, expected=expected):
                stdout=io.StringIO();stderr=io.StringIO()
                with patch.object(FactoryOrchestrator,'reconcile_interrupted',side_effect=error), \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(main(args),1)
                self.assertEqual(stdout.getvalue(),expected+'\n')
                self.assertEqual(stderr.getvalue(),'')

    def test_abort_parser_refuses_every_run_surface_option_before_reconciliation(self):
        import contextlib
        import io
        from lightyear_factory.cli import build_parser, main
        args=['reconcile-interrupted','--runs-root',str(self.root),'--run-id',self.run.name]
        for name,value in self.bindings.items():args.extend(['--'+name.replace('_','-'),value])
        parser=build_parser()
        sub=next(action for action in parser._actions if hasattr(action,'choices')
                 and isinstance(action.choices,dict) and 'run' in action.choices)
        run_options={option for action in sub.choices['run']._actions for option in action.option_strings
                     if any(word in option for word in ('graph','evidence','projection','memory'))}
        self.assertTrue(run_options)
        self.assertEqual({word for word in ('graph','evidence','projection','memory')
                          if any(word in option for option in run_options)},
                         {'graph','evidence','projection','memory'})
        options=run_options|{'--graph','--evidence','--projection','--memory','--runs-ro'}
        before=(self.run/'events.jsonl').read_bytes()
        for option in sorted(options):
            with self.subTest(option=option), \
                 patch.object(FactoryOrchestrator,'reconcile_interrupted') as reconcile, \
                 contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as refused:main(args+[option,'synthetic'])
                self.assertEqual(refused.exception.code,2)
                reconcile.assert_not_called()
        self.assertEqual(before,(self.run/'events.jsonl').read_bytes())


    def test_retained_abort_replays_original_bytes_without_authority(self):
        from tools.ci.p5_controller_probe import retain_abort_journals, validate_retained_abort
        event = self.reconcile()
        before = {p.name: p.read_bytes() for p in self.run.iterdir() if p.is_file()}
        # An unrelated file must never be swept into the retained evidence.
        (self.run/'unrelated-private-placeholder.txt').write_text('synthetic excluded content')
        value = retain_abort_journals(self.run, self.root/'admission-nonces.sha256', event)
        self.assertTrue(validate_retained_abort(value))
        self.assertEqual(set(value['documents']), {'attempt-identity.json', 'attempt-accounting.jsonl', 'events.jsonl'})
        self.assertFalse(value['production_controller_receipt'])
        self.assertFalse(value['human_attestation_verified'])
        self.assertEqual(value['interrupted_record']['payload']['accounting'], self.accounting)
        for name, raw in before.items():
            self.assertEqual((self.run/name).read_bytes(), raw)
        for name, row in value['documents'].items():
            self.assertEqual(row['utf8'].encode(), before[name])

    def test_retained_abort_missing_corrupt_or_cross_attempt_bytes_refuse(self):
        import copy
        from tools.ci.p5_controller_probe import retain_abort_journals, validate_retained_abort
        value = retain_abort_journals(self.run, self.root/'admission-nonces.sha256', self.reconcile())
        mutations = []
        for name in value['documents']:
            bad = copy.deepcopy(value); del bad['documents'][name]; mutations.append(bad)
            bad = copy.deepcopy(value); bad['documents'][name]['utf8'] += ' '; mutations.append(bad)
        bad = copy.deepcopy(value); bad['run_id'] = 'another-attempt'; mutations.append(bad)
        bad = copy.deepcopy(value)
        bad['nonce_store'] = dict(utf8='0'*64+'\n', sha256=hashlib.sha256(('0'*64+'\n').encode()).hexdigest())
        mutations.append(bad)
        for bad in mutations:
            with self.subTest(fields=list(bad['documents'])):
                with self.assertRaisesRegex(ValueError, 'p5-retained-abort-invalid'):
                    validate_retained_abort(bad)

    def test_retained_abort_self_rehashed_accounting_and_authority_claims_refuse(self):
        import copy
        from tools.ci.p5_controller_probe import retain_abort_journals, validate_retained_abort
        value = retain_abort_journals(self.run, self.root/'admission-nonces.sha256', self.reconcile())
        for field, replacement in (('calls', 2), ('input_tokens', 999), ('billing_final', True)):
            bad = copy.deepcopy(value)
            events = [json.loads(line) for line in bad['documents']['events.jsonl']['utf8'].splitlines()]
            events[-1]['payload']['accounting'][field] = replacement
            events[-1]['event_sha256'] = canonical_hash(events[-1], {'event_sha256'})
            raw = ''.join(json.dumps(event, sort_keys=True, separators=(',', ':'))+'\n' for event in events)
            bad['documents']['events.jsonl'] = dict(utf8=raw, sha256=hashlib.sha256(raw.encode()).hexdigest())
            bad['interrupted_record'] = events[-1]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'p5-retained-abort-invalid'):
                validate_retained_abort(bad)
        for field in ('production_controller_receipt', 'human_attestation_verified'):
            bad = copy.deepcopy(value); bad[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'p5-retained-abort-invalid'):
                validate_retained_abort(bad)

    def test_retained_abort_truncated_reordered_and_duplicate_key_journals_refuse(self):
        import copy
        from tools.ci.p5_controller_probe import retain_abort_journals, validate_retained_abort
        value = retain_abort_journals(self.run, self.root/'admission-nonces.sha256', self.reconcile())
        original = value['documents']['events.jsonl']['utf8']
        lines = original.splitlines(keepends=True)
        duplicate = lines[0].replace('{', '{"sequence":999,', 1) + ''.join(lines[1:])
        for raw in (original.rstrip('\n'), ''.join(reversed(lines)), duplicate):
            bad = copy.deepcopy(value)
            bad['documents']['events.jsonl'] = dict(utf8=raw, sha256=hashlib.sha256(raw.encode()).hexdigest())
            with self.assertRaisesRegex(ValueError, 'p5-retained-abort-invalid'):
                validate_retained_abort(bad)



if __name__=='__main__':
    unittest.main()
