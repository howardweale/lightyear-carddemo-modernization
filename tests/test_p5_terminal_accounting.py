"""CI-only synthetic retained journals; no admission, keys or transport sends."""
import base64
from copy import deepcopy
import json
import os
import unittest

from lightyear_factory.contracts import ContractError, canonical_hash
from tools.ci.p5_terminal_accounting import replay, validate
from tools.ci.p5_terminal_evidence import retain, validate as validate_relations


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()


def chain(items):
    rows = []
    for state, kind, payload in items:
        event = dict(sequence=len(rows)+1, occurred_at='2026-01-01T00:00:00Z',
            previous_sha256=rows[-1]['event_sha256'] if rows else None,
            state=state, kind=kind, payload=payload)
        event['event_sha256'] = canonical_hash(event); rows.append(event)
    return b''.join(encoded(row) for row in rows)


class TerminalAccountingReplayTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def evidence(self, protocol=4, include_snapshot=True, sequence=1):
        identity = dict(schema='factory-attempt-identity/1', attempt_id='public-terminal-accounting',
            work_order_sha256='a'*64, consumed_nonce_sha256='b'*64, sealed_workspace_sha256='c'*64,
            admission_receipt_sha256='d'*64, workspace_inventory_sha256='e'*64)
        identity['content_sha256'] = canonical_hash(identity)
        events = chain([
            ('READY', 'work_order_accepted', {'work_order_sha256':'a'*64}),
            ('READY', 'hardened_admission_bound', {'admission_receipt_sha256':'d'*64}),
            ('READY', 'workspace_read_manifest', {'sha256':'e'*64}),
            ('BLOCKED', 'controller_error', {'reason':'factory-isolation-run-refused'})])
        receipt = dict(receipt_type='lightyear-autonomous-factory-run', status='blocked',
            attempts=0, repair_loops=0, work_order_sha256='a'*64,
            ledger_head_sha256=json.loads(events.splitlines()[-1])['event_sha256'],
            qualifies_for_factory_receipt=False, reason='factory-isolation-run-refused')
        receipt['content_sha256'] = canonical_hash(receipt)
        summary = dict(status='blocked', attempts=0, reason='factory-isolation-run-refused',
                       receipt_sha256=receipt['content_sha256'])
        bind = dict(attempt_identity_sha256=identity['content_sha256'])
        items = [('READY', 'model_reservations', dict(bind, protocol=protocol))]
        if include_snapshot:
            accounting = dict(schema='factory-sanitized-accounting/1', calls=0,
                input_tokens=0, output_tokens=0, estimated_cost_usd=0.0,
                duration_ms=10, duration_basis='observed-through-checkpoint', call_hashes=[],
                scanned_transports=[], in_flight_final_usage='none', billing_final=False)
            items.append(('OBSERVED', 'sanitized_accounting', dict(bind, accounting=accounting)))
        reservation = dict(call_sequence=sequence, role='planner', request_sha256='f'*64,
            invocation_sha256='f'*64, input_tokens=999, output_tokens=16, estimated_cost_usd=0.01)
        items.append(('RESERVED', 'reserved', dict(bind, reservation=reservation)))
        receipt['failure_accounting'] = dict(
            schema='factory-sanitized-accounting/1', calls=0, input_tokens=0, output_tokens=0,
            estimated_cost_usd=0.0, duration_ms=11, duration_basis='observed-through-checkpoint',
            call_hashes=[], scanned_transports=[], in_flight_final_usage='none', billing_final=False)
        receipt['content_sha256'] = canonical_hash(receipt, {'content_sha256'})
        summary['receipt_sha256'] = receipt['content_sha256']
        return retain({'receipt.json':encoded(receipt), 'summary.json':encoded(summary),
            'events.jsonl':events, 'attempt-identity.json':encoded(identity),
            'attempt-accounting.jsonl':chain(items)})

    def test_native_replay_keeps_unknown_logical_hold_without_authority(self):
        evidence = self.evidence(); before = deepcopy(evidence)
        result = replay(evidence)
        self.assertTrue(validate(result, evidence))
        self.assertEqual(evidence, before)
        accounting = result['replayed_accounting']
        self.assertEqual(accounting['calls'], 0)
        self.assertEqual(accounting['estimated_cost_usd'], 0)
        self.assertFalse(accounting['billing_final'])
        self.assertEqual(accounting['in_flight_final_usage'], 'unknown; reserved upper bound recorded')
        self.assertEqual(accounting['reserved_in_flight']['estimated_cost_usd'], 0.01)
        self.assertEqual(accounting['model_transport_accounting'], [])
        self.assertEqual(accounting['invoice_reconciliation'],
            "The actual cost will be reconciled by Howard from the provider's invoice.")
        for flag in ('controller_origin_verified', 'execution_authorized', 'resume_allowed',
                     'production_qualified', 'qualifies_for_factory_receipt',
                     'expected_refusal_verified', 'actual_provider_cost_verified'):
            self.assertIs(result[flag], False)

    def test_hash_valid_relations_do_not_replace_native_accounting_replay(self):
        for evidence in (self.evidence(include_snapshot=False), self.evidence(sequence=2)):
            self.assertTrue(validate_relations(evidence))
            with self.assertRaises(ContractError): replay(evidence)

    def test_rehashed_replay_changes_and_legacy_upgrade_refuse(self):
        evidence = self.evidence(protocol=2)
        result = replay(evidence)
        self.assertEqual(result['journal_protocol'], 2)
        self.assertEqual(result['replay_scope'], 'historical retained bytes only; no send or recovery execution')
        self.assertFalse(result['execution_authorized'])
        for field, value in (('journal_protocol', 5), ('execution_authorized', True),
                             ('actual_provider_cost_verified', True)):
            changed = deepcopy(result); changed[field] = value
            changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
            with self.subTest(field=field), self.assertRaises(ValueError): validate(changed, evidence)
        changed = deepcopy(result); changed['replayed_accounting']['reserved_in_flight']['estimated_cost_usd'] = 0
        changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
        with self.assertRaises(ValueError): validate(changed, evidence)
        self.assertTrue(validate(result, evidence))


    def test_python_equal_boolean_or_numeric_substitution_does_not_pass(self):
        evidence = self.evidence(); result = replay(evidence)
        for field, value in (('execution_authorized', 0), ('native_replay_completed', 1),
                             ('journal_protocol', 4.0)):
            changed = deepcopy(result); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate(changed, evidence)
        self.assertTrue(validate(result, evidence))



    def replace_receipt_accounting(self, evidence, updates):
        documents = {name: base64.b64decode(row['base64'], validate=True)
                     for name, row in evidence['documents'].items()}
        receipt = json.loads(documents['receipt.json'])
        receipt['failure_accounting'].update(updates)
        receipt['content_sha256'] = canonical_hash(receipt, {'content_sha256'})
        summary = json.loads(documents['summary.json'])
        summary['receipt_sha256'] = receipt['content_sha256']
        documents['receipt.json'] = encoded(receipt)
        documents['summary.json'] = encoded(summary)
        return retain(documents)

    def test_later_receipt_duration_matches_checkpoint_without_changing_bytes(self):
        evidence = self.evidence(); before = deepcopy(evidence)
        result = replay(evidence)
        self.assertTrue(result['receipt_checkpoint_fields_match'])
        self.assertEqual(result['checkpoint_duration_ms'], 10)
        self.assertEqual(result['receipt_duration_ms'], 11)
        self.assertTrue(validate(result, evidence))
        self.assertEqual(evidence, before)
        self.assertEqual(result['replayed_accounting']['reserved_in_flight']['estimated_cost_usd'], 0.01)
        self.assertEqual(result['replayed_accounting']['estimated_cost_usd'], 0)
        self.assertFalse(result['actual_provider_cost_verified'])
        self.assertFalse(result['replayed_accounting']['billing_final'])

    def test_rehashed_receipt_accounting_substitutions_refuse(self):
        evidence = self.evidence()
        changes = [dict(input_tokens=1), dict(output_tokens=1), dict(estimated_cost_usd=0.01),
            dict(estimated_cost_usd=0),
            dict(calls=1, call_hashes=[dict(request_sha256='a'*64, response_sha256='b'*64)]),
            dict(scanned_transports=[dict(role='planner', prompt_sha256='a'*64, response_sha256=None)]),
            dict(in_flight_final_usage='unknown')]
        for change in changes:
            changed = self.replace_receipt_accounting(evidence, change)
            self.assertTrue(validate_relations(changed))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError,
                    'terminal-accounting-receipt-checkpoint-mismatch'):
                replay(changed)

    def test_earlier_or_malformed_receipt_duration_refuses(self):
        evidence = self.evidence()
        earlier = self.replace_receipt_accounting(evidence, dict(duration_ms=9))
        self.assertTrue(validate_relations(earlier))
        with self.assertRaisesRegex(ValueError, 'terminal-accounting-receipt-checkpoint-mismatch'):
            replay(earlier)
        for duration in (False, -1, 11.0):
            changed = self.replace_receipt_accounting(evidence, dict(duration_ms=duration))
            with self.subTest(duration=duration), self.assertRaises(ContractError): replay(changed)


if __name__ == '__main__': unittest.main()
