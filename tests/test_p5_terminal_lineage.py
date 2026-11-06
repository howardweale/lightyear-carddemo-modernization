"""CI-only registry unit tests; mocked admission is never a genuine case proof."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_execution.tower_drill_context import HumanDrillExecutionContext
from lightyear_execution.contracts import ExecutionContractError
from lightyear_execution.public_drill_runtime import (
    PublicDrillProvider, _capture_terminal_lineage, _require_terminal_lineage,
    _TERMINAL_LINEAGE)


class FixtureNode:
    """Weak-reference-compatible public unit fixture, not an authority object."""
    def __init__(self, **values): self.__dict__.update(values)
    def to_dict(self): return {'public_policy_fixture': True}


class PublicTerminalLineageRegistryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        context = object.__new__(HumanDrillExecutionContext)
        context.admission_receipt = {'public_synthetic_admission': True}
        context._runtime = {'public_synthetic_runtime': True}
        context._review = {'public_synthetic_review': True}
        context._workflow = {'public_synthetic_workflow': True}
        context._public_outputs = {'public_synthetic_outputs': True}
        context._public_values = ('public-synthetic-isolation-text',)
        context.policy = FixtureNode()
        context.backend = FixtureNode(policy=context.policy, runtime='docker',
                                      execute_enabled=True, backend_id='oci-docker')
        context._root = self.root; context._inputs = {'public': self.root/'public.json'}
        context._manifest = {'public.py': 'a'*64}
        context._admission = FixtureNode(); context._order = FixtureNode(content_sha256='b'*64)
        context._controller_bound = True; context._closed = False
        provider = object.__new__(PublicDrillProvider)
        provider.context = context; provider.script = {'public_synthetic_script': True, 'model':'public-unit'}
        provider.model = 'public-unit'
        provider.run_dir = self.root; provider.ledger = RunLedger(self.root/'events.jsonl')
        controller = object.__new__(FactoryOrchestrator)
        controller.execution_context = context
        controller.agents = FixtureNode(provider=provider,
            bounded_provider=FixtureNode(provider=provider, order=context._order))
        provider.controller = controller
        self.provider = provider; self.context = context; self.controller = controller
        self.addCleanup(lambda: _TERMINAL_LINEAGE.pop(provider, None))

    def capture_unit_fixture(self):
        # This patch tests registry mechanics only. It cannot be used to claim
        # real admission, signature validity, execution or strict qualification.
        with patch.object(HumanDrillExecutionContext, '_live') as live:
            _capture_terminal_lineage(self.provider)
        live.assert_called_once_with()

    def test_closing_context_does_not_renew_authorization_during_historical_read(self):
        self.capture_unit_fixture()
        self.context.close()
        with patch.object(HumanDrillExecutionContext, '_live',
                          side_effect=AssertionError('historical reader called authorization')):
            saved = _require_terminal_lineage(self.provider)
        self.assertIs(saved['controller'](), self.controller)
        self.assertTrue(self.context._closed)
        # The actual authorization method still rejects this closed unit context.
        with self.assertRaisesRegex(ExecutionContractError, 'fresh-process-context-required'):
            self.context.authorize('planner', 'factory:plan', None)
        self.assertTrue(self.context._closed)

    def test_missing_registry_copy_cross_process_and_second_capture_refuse(self):
        with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
            _require_terminal_lineage(self.provider)
        self.capture_unit_fixture()
        with patch.object(HumanDrillExecutionContext, '_live'):
            with self.assertRaisesRegex(ContractError, 'terminal-lineage-rebind'):
                _capture_terminal_lineage(self.provider)
        copied = object.__new__(PublicDrillProvider); copied.__dict__.update(self.provider.__dict__)
        with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
            _require_terminal_lineage(copied)
        current = os.getpid()
        with patch('lightyear_execution.public_drill_runtime.os.getpid', return_value=current+1):
            with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
                _require_terminal_lineage(self.provider)
        with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
            _require_terminal_lineage({'receipt': 'not a native provider'})

    def test_changed_admission_script_backend_and_ci_identity_refuse(self):
        self.capture_unit_fixture()
        for name in ('admission_receipt', '_runtime', '_review', '_workflow', '_public_outputs', '_manifest'):
            before = deepcopy(getattr(self.context, name))
            try:
                setattr(self.context, name, {'changed_public_fixture': name})
                with self.subTest(name=name), self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
                    _require_terminal_lineage(self.provider)
            finally: setattr(self.context, name, before)
        before = self.provider.script
        self.provider.script = {'changed': True}
        with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
            _require_terminal_lineage(self.provider)
        self.provider.script = before
        self.context.backend.execute_enabled = False
        with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
            _require_terminal_lineage(self.provider)
        self.context.backend.execute_enabled = True
        with patch.dict(os.environ, {'GITHUB_RUN_ID': 'different-public-run'}):
            with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
                _require_terminal_lineage(self.provider)
        self.assertIs(_require_terminal_lineage(self.provider)['controller'](), self.controller)

    def test_malformed_script_refuses_without_reopening_closed_context(self):
        self.capture_unit_fixture()
        self.context.close()
        original = self.provider.script
        saved = _TERMINAL_LINEAGE[self.provider]
        for changed in (None, [], 'public malformed script', {},
                        {'model': None}, {'model': 'different-public-model'}):
            try:
                self.provider.script = changed
                with self.subTest(script=changed):
                    with patch.object(HumanDrillExecutionContext, '_live',
                                      side_effect=AssertionError('historical read reopened context')):
                        with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
                            _require_terminal_lineage(self.provider)
                self.assertTrue(self.context._closed)
                self.assertIs(_TERMINAL_LINEAGE[self.provider], saved)
            finally:
                self.provider.script = original
        self.assertIs(_require_terminal_lineage(self.provider), saved)
        self.assertTrue(self.context._closed)

    def test_non_native_context_or_wrong_controller_cannot_capture_lineage(self):
        original = self.provider.context
        self.provider.context = FixtureNode(_controller_bound=True)
        with self.assertRaisesRegex(ContractError, 'terminal-lineage-bind'):
            _capture_terminal_lineage(self.provider)
        self.provider.context = original
        self.controller.agents.bounded_provider.provider = object()
        with self.assertRaisesRegex(ContractError, 'terminal-lineage-bind'):
            _capture_terminal_lineage(self.provider)
        self.assertNotIn(self.provider, _TERMINAL_LINEAGE)

    def write_public_record(self, name, value):
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()
        (self.root/name).write_bytes(raw)
        return raw

    def prepare_terminal_unit_records(self):
        """Native journal/file formats with synthetic admission, zero provider calls."""
        admission = dict(work_order_sha256='b'*64, nonce_sha256='c'*64,
                         execution_policy_sha256='d'*64, plan_sha256='e'*64,
                         decision_sha256='f'*64, trusted_journal_head='1'*64)
        admission['content_sha256'] = canonical_hash(admission)
        self.context.admission_receipt = admission
        request = dict(instruction='Public fixture', payload={}, schema={'type':'object'})
        step = dict(sequence=1, role='planner', invocation_sha256=canonical_hash(request),
                    schema_sha256=canonical_hash(request['schema']), response_content={},
                    response_sha256=canonical_hash({'content':{}}))
        script = dict(model='p5-public-unit-fixture', steps=[step])
        script['content_sha256'] = canonical_hash(script)
        self.provider.script = script
        self.provider.model = script['model']
        self.context._public_outputs = {'output_plan_sha256': script['content_sha256']}
        self.context.authorization_receipts = []
        self.controller.agents.bounded_provider.calls = []
        self.provider.observed = []
        identity = dict(schema='factory-attempt-identity/1', attempt_id=self.root.name,
            work_order_sha256='b'*64, consumed_nonce_sha256='c'*64,
            admission_receipt_sha256=admission['content_sha256'],
            sealed_workspace_sha256='2'*64, workspace_inventory_sha256='3'*64)
        identity['content_sha256'] = canonical_hash(identity)
        self.write_public_record('attempt-identity.json', identity)
        accounting = RunLedger(self.root/'attempt-accounting.jsonl')
        accounting.append('READY', 'model_reservations', dict(protocol=5,
            count_bound_profile='request-bytes-v1', attempt_identity_sha256=identity['content_sha256']))
        self.controller._live_journal_events = lambda: RunLedger(accounting.path).events
        self.provider.ledger.append('RUNNING', 'public_drill_controller_bound',
            dict(output_plan_sha256=script['content_sha256'],
                 admission_receipt_sha256=admission['content_sha256'],
                 work_order_sha256='b'*64, provider='p5-scripted', model=script['model']))
        self.capture_unit_fixture()
        self.provider.ledger.append('BLOCKED', 'controller_error',
                                    {'reason':'factory-isolation-run-refused'})
        receipt = dict(receipt_type='lightyear-autonomous-factory-run', status='blocked',
            work_order_sha256='b'*64, ledger_head_sha256=self.provider.ledger.head_sha256,
            qualifies_for_factory_receipt=False, reason='factory-isolation-run-refused')
        receipt['content_sha256'] = canonical_hash(receipt)
        self.write_public_record('receipt.json', receipt)
        self.write_public_record('summary.json', dict(status='blocked', receipt_sha256=receipt['content_sha256']))
        self.context.close()
        return receipt

    def test_terminal_record_is_read_only_incomplete_and_grants_no_current_authority(self):
        receipt = self.prepare_terminal_unit_records()
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(HumanDrillExecutionContext, '_live',
                          side_effect=AssertionError('terminal reader invoked authorization')):
            result = self.provider.retained_terminal_lineage(receipt)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertTrue(result['same_process_controller_lineage_verified'])
        self.assertFalse(result['output_plan_complete'])
        self.assertEqual(result['completed_public_calls'], 0)
        self.assertEqual(result['receipt_file_sha256'], sha256(before['receipt.json']).hexdigest())
        self.assertEqual(result['content_sha256'], canonical_hash(result, {'content_sha256'}))
        for name in ('controller_origin_verified', 'execution_authorized', 'resume_allowed',
                     'retry_allowed', 'production_qualified', 'qualifies_for_factory_receipt',
                     'accounting_semantics_verified', 'expected_refusal_verified'):
            self.assertIs(result[name], False)
        self.assertEqual(result['gaps'], ['full-production-build-receipt-route-not-integrated',
                                         'terminal-drill-outcome-not-qualified'])
        self.assertTrue(self.context._closed)
        with self.assertRaisesRegex(ExecutionContractError, 'fresh-process-context-required'):
            self.context.authorize('planner', 'factory:plan', None)

    def test_terminal_receipt_summary_and_identity_substitution_refuse(self):
        receipt = self.prepare_terminal_unit_records()
        with self.assertRaisesRegex(ContractError, 'terminal-blocked-only'):
            self.provider.retained_terminal_lineage({**receipt, 'status':'passed'})
        for name, field in (('summary.json','receipt_sha256'),
                            ('attempt-identity.json','consumed_nonce_sha256'),
                            ('attempt-identity.json','admission_receipt_sha256')):
            original = (self.root/name).read_bytes()
            changed = json.loads(original); changed[field] = '0'*64
            if 'content_sha256' in changed:
                changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
            self.write_public_record(name, changed)
            try:
                with self.subTest(name=name, field=field), self.assertRaisesRegex(ContractError, 'terminal-receipt-binding'):
                    self.provider.retained_terminal_lineage(receipt)
            finally: (self.root/name).write_bytes(original)
        self.assertTrue(self.provider.retained_terminal_lineage(receipt)['same_process_controller_lineage_verified'])

    def test_terminal_extra_event_and_rehashed_accounting_identity_refuse(self):
        receipt = self.prepare_terminal_unit_records()
        original_events = (self.root/'events.jsonl').read_bytes()
        RunLedger(self.root/'events.jsonl').append('RUNNING', 'unexpected_extra_event', {})
        with self.assertRaisesRegex(ContractError, 'terminal-ledger'):
            self.provider.retained_terminal_lineage(receipt)
        (self.root/'events.jsonl').write_bytes(original_events)
        accounting = self.root/'attempt-accounting.jsonl'
        original_accounting = accounting.read_bytes()
        event = json.loads(original_accounting)
        event['payload']['attempt_identity_sha256'] = '0'*64
        event['event_sha256'] = canonical_hash(event, {'event_sha256'})
        self.write_public_record('attempt-accounting.jsonl', event)
        with self.assertRaisesRegex(ContractError, 'terminal-accounting-identity'):
            self.provider.retained_terminal_lineage(receipt)
        accounting.write_bytes(original_accounting)
        self.assertFalse(self.provider.retained_terminal_lineage(receipt)['output_plan_complete'])

    def test_model_or_ledger_path_replacement_cannot_reuse_historical_lineage(self):
        receipt = self.prepare_terminal_unit_records()
        model = self.provider.model; path = self.provider.ledger.path
        try:
            self.provider.model = 'different-public-model'
            with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
                self.provider.retained_terminal_lineage(receipt)
            self.provider.model = model
            self.provider.ledger.path = self.root/'different-events.jsonl'
            with self.assertRaisesRegex(ContractError, 'terminal-lineage-refused'):
                self.provider.retained_terminal_lineage(receipt)
            self.assertFalse(self.provider.ledger.path.exists())
        finally:
            self.provider.model = model; self.provider.ledger.path = path
        self.assertTrue(self.provider.retained_terminal_lineage(receipt)['same_process_controller_lineage_verified'])


    def prepare_completed_terminal_unit_records(self):
        """Synthetic completed-call relations only; no admission or provider execution."""
        admission = dict(work_order_sha256='b'*64, nonce_sha256='c'*64,
                         execution_policy_sha256='d'*64, plan_sha256='e'*64,
                         decision_sha256='f'*64, trusted_journal_head='1'*64)
        admission['content_sha256'] = canonical_hash(admission)
        self.context.admission_receipt = admission
        request = dict(instruction='Public fixture', payload={}, schema={'type':'object'})
        step = dict(sequence=1, role='planner', invocation_sha256=canonical_hash(request),
                    schema_sha256=canonical_hash(request['schema']), response_content={},
                    response_sha256=canonical_hash({'content':{}}))
        script = dict(model='p5-public-unit-fixture', steps=[step])
        script['content_sha256'] = canonical_hash(script)
        self.provider.script = script
        self.provider.model = script['model']
        self.context._public_outputs = {'output_plan_sha256': script['content_sha256']}
        self.context.authorization_receipts = []
        self.controller.agents.bounded_provider.calls = []
        self.provider.observed = []
        identity = dict(schema='factory-attempt-identity/1', attempt_id=self.root.name,
            work_order_sha256='b'*64, consumed_nonce_sha256='c'*64,
            admission_receipt_sha256=admission['content_sha256'],
            sealed_workspace_sha256='2'*64, workspace_inventory_sha256='3'*64)
        identity['content_sha256'] = canonical_hash(identity)
        self.write_public_record('attempt-identity.json', identity)
        accounting = RunLedger(self.root/'attempt-accounting.jsonl')
        accounting.append('READY', 'model_reservations', dict(protocol=5,
            count_bound_profile='request-bytes-v1', attempt_identity_sha256=identity['content_sha256']))
        self.controller._live_journal_events = lambda: RunLedger(accounting.path).events
        self.provider.ledger.append('RUNNING', 'public_drill_controller_bound',
            dict(output_plan_sha256=script['content_sha256'],
                 admission_receipt_sha256=admission['content_sha256'],
                 work_order_sha256='b'*64, provider='p5-scripted', model=script['model']))
        # Construct public recorded data, not an execution or authorization grant.
        scope = {k:v for k,v in admission.items() if k != 'content_sha256'}
        scope.update(role='planner', action='factory:plan',
                     status='verified-scope-only', execution_authorized=False)
        scope['content_sha256'] = canonical_hash(scope)
        self.context.authorization_receipts = [scope]
        reserved = accounting.append('RUNNING', 'reserved', dict(
            attempt_identity_sha256=identity['content_sha256'], reservation=dict(
                role='planner', call_sequence=1, request_sha256=step['invocation_sha256'],
                invocation_sha256=step['invocation_sha256'])))
        (self.root/'public-drill').mkdir()
        def artifact(kind, value):
            relative = 'public-drill/0001-'+kind+'.json'
            raw = self.write_public_record(relative, value)
            return dict(path=relative, sha256=sha256(raw).hexdigest(), bytes=len(raw))
        start = self.provider.ledger.append('RUNNING', 'public_drill_call_started', dict(
            sequence=1, role='planner', invocation_sha256=step['invocation_sha256'],
            schema_sha256=step['schema_sha256'], request=artifact('request', request),
            authorization_sha256=scope['content_sha256'],
            logical_reservation_event_sha256=reserved['event_sha256'],
            output_plan_sha256=script['content_sha256']))
        end = self.provider.ledger.append('RUNNING', 'public_drill_call_finished', dict(
            sequence=1, role='planner', start_event_sha256=start['event_sha256'],
            response=artifact('response', {}), response_sha256=step['response_sha256']))
        call = dict(provider='p5-scripted', model=script['model'], role='planner', call_sequence=1,
            request_sha256=step['invocation_sha256'], response_sha256=step['response_sha256'],
            public_drill_record=dict(start_event_sha256=start['event_sha256'],
                end_event_sha256=end['event_sha256'], output_plan_sha256=script['content_sha256']))
        call['content_sha256'] = canonical_hash(call)
        self.controller.agents.bounded_provider.calls = [call]
        self.provider.observed = [deepcopy(step)]
        self.capture_unit_fixture()
        self.provider.ledger.append('BLOCKED', 'controller_error',
                                    {'reason':'factory-isolation-run-refused'})
        receipt = dict(receipt_type='lightyear-autonomous-factory-run', status='blocked',
            work_order_sha256='b'*64, ledger_head_sha256=self.provider.ledger.head_sha256,
            qualifies_for_factory_receipt=False, reason='factory-isolation-run-refused')
        receipt['content_sha256'] = canonical_hash(receipt)
        self.write_public_record('receipt.json', receipt)
        self.write_public_record('summary.json', dict(status='blocked', receipt_sha256=receipt['content_sha256']))
        self.context.close()
        return receipt


    def test_completed_call_terminal_relations_never_grant_build_or_execution(self):
        receipt = self.prepare_completed_terminal_unit_records()
        before = {str(p.relative_to(self.root)):p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        with patch.object(HumanDrillExecutionContext, '_live',
                          side_effect=AssertionError('terminal read retried authorization')):
            result = self.provider.retained_terminal_lineage(receipt)
        self.assertTrue(result['output_plan_complete'])
        self.assertEqual(result['completed_public_calls'], 1)
        self.assertEqual(result['unfinished_public_calls'], 0)
        self.assertEqual(result['accounted_calls'], 1)
        self.assertTrue(result['same_process_controller_lineage_verified'])
        for key in ('controller_origin_verified', 'execution_authorized', 'resume_allowed',
                    'retry_allowed', 'production_qualified', 'qualifies_for_factory_receipt',
                    'accounting_semantics_verified', 'expected_refusal_verified'):
            self.assertIs(result[key], False)
        self.assertEqual(result['gaps'], ['full-production-build-receipt-route-not-integrated',
                                         'terminal-drill-outcome-not-qualified'])
        self.assertEqual(before, {str(p.relative_to(self.root)):p.read_bytes()
                                 for p in self.root.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(ExecutionContractError, 'fresh-process-context-required'):
            self.context.authorize('planner', 'factory:plan', None)

    def test_completed_terminal_response_accounting_and_observation_substitution_refuse(self):
        receipt = self.prepare_completed_terminal_unit_records()
        response = self.root/'public-drill/0001-response.json'
        original = response.read_bytes()
        response.write_bytes(b'{"different":"public fixture"}')
        try:
            with self.assertRaisesRegex(ContractError, 'artifact-digest'):
                self.provider.retained_terminal_lineage(receipt)
        finally: response.write_bytes(original)
        call = self.controller.agents.bounded_provider.calls[0]
        original_call = deepcopy(call)
        call['response_sha256'] = '0'*64
        call['content_sha256'] = canonical_hash(call, {'content_sha256'})
        try:
            with self.assertRaisesRegex(ContractError, 'content-or-accounting'):
                self.provider.retained_terminal_lineage(receipt)
        finally: self.controller.agents.bounded_provider.calls[0] = original_call
        observed = self.provider.observed
        self.provider.observed = []
        try:
            with self.assertRaisesRegex(ContractError, 'terminal-observed-count'):
                self.provider.retained_terminal_lineage(receipt)
        finally: self.provider.observed = observed
        self.assertEqual(self.provider.retained_terminal_lineage(receipt)['completed_public_calls'], 1)


if __name__ == '__main__':
    unittest.main()
