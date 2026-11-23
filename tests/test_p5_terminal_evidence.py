"""CI-only synthetic relation fixtures: no proof, keys or execution grant."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import canonical_hash
from tools.ci.p5_terminal_evidence import retain, validate


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()


def chain(items):
    rows = []
    for state, kind, payload in items:
        event = dict(sequence=len(rows)+1, occurred_at='2026-01-01T00:00:00Z',
                     previous_sha256=rows[-1]['event_sha256'] if rows else None,
                     state=state, kind=kind, payload=payload)
        event['event_sha256'] = canonical_hash(event)
        rows.append(event)
    return rows


class TerminalEvidenceRelationTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.identity = dict(schema='factory-attempt-identity/1', attempt_id='synthetic-terminal',
            work_order_sha256='a'*64, consumed_nonce_sha256='b'*64, sealed_workspace_sha256='c'*64,
            admission_receipt_sha256='d'*64, workspace_inventory_sha256='e'*64)
        self.identity['content_sha256'] = canonical_hash(self.identity)
        self.events = chain([
            ('READY', 'work_order_accepted', {'work_order_sha256': 'a'*64}),
            ('READY', 'hardened_admission_bound', {'admission_receipt_sha256': 'd'*64}),
            ('READY', 'workspace_read_manifest', {'sha256': 'e'*64}),
            ('BLOCKED', 'controller_error', {'reason': 'factory-isolation-run-refused'})])
        self.accounting = chain([('READY', 'model_reservations',
            dict(attempt_identity_sha256=self.identity['content_sha256'], protocol=4))])
        self.receipt = dict(schema_version='1.0', receipt_type='lightyear-autonomous-factory-run',
            status='blocked', attempts=0, repair_loops=0, work_order_sha256='a'*64,
            ledger_head_sha256=self.events[-1]['event_sha256'], qualifies_for_factory_receipt=False,
            reason='factory-isolation-run-refused', failure_accounting={})
        self.receipt['content_sha256'] = canonical_hash(self.receipt)
        self.summary = dict(status='blocked', attempts=0,
            receipt_sha256=self.receipt['content_sha256'], reason='factory-isolation-run-refused')
        self.originals = {
            'receipt.json': encoded(self.receipt), 'summary.json': encoded(self.summary),
            'attempt-identity.json': encoded(self.identity),
            'events.jsonl': b''.join(encoded(row) for row in self.events),
            'attempt-accounting.jsonl': b''.join(encoded(row) for row in self.accounting)}

    def rehash(self, value):
        value['content_sha256'] = canonical_hash(value, {'content_sha256'})
        return value

    def replace_document(self, value, name, raw):
        value['documents'][name] = dict(base64=base64.b64encode(raw).decode('ascii'),
                                        bytes=len(raw), sha256=sha256(raw).hexdigest())
        return self.rehash(value)

    def test_original_bytes_survive_without_origin_accounting_or_refusal_acceptance(self):
        before = deepcopy(self.originals)
        value = retain(self.originals)
        self.assertTrue(validate(value))
        self.assertEqual(self.originals, before)
        for name, raw in before.items():
            self.assertEqual(base64.b64decode(value['documents'][name]['base64']), raw)
        for flag in ('controller_origin_verified', 'execution_authorized', 'production_qualified',
                     'qualifies_for_factory_receipt', 'resume_allowed',
                     'accounting_semantics_verified', 'expected_refusal_verified'):
            self.assertIs(value[flag], False)
            changed = deepcopy(value); changed[flag] = True; self.rehash(changed)
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                validate(changed)

    def test_rehashed_cross_run_receipt_summary_and_accounting_substitutions_refuse(self):
        original = retain(self.originals)
        wrong_summary = {**self.summary, 'receipt_sha256': '0'*64}
        wrong_receipt = {**self.receipt, 'work_order_sha256': '0'*64}
        wrong_receipt['content_sha256'] = canonical_hash(wrong_receipt, {'content_sha256'})
        wrong_accounting = chain([('READY', 'model_reservations',
            dict(attempt_identity_sha256='0'*64, protocol=4))])
        variants = [('summary.json', encoded(wrong_summary)),
                    ('receipt.json', encoded(wrong_receipt)),
                    ('attempt-accounting.jsonl', b''.join(encoded(row) for row in wrong_accounting))]
        for name, raw in variants:
            changed = self.replace_document(deepcopy(original), name, raw)
            if name == 'attempt-accounting.jsonl':
                changed['accounting_head_sha256'] = wrong_accounting[-1]['event_sha256']
                self.rehash(changed)
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(changed)
        changed = deepcopy(original); changed['run_id'] = 'different-run'; self.rehash(changed)
        with self.assertRaises(ValueError): validate(changed)

    def test_self_rehashed_wrong_boundary_and_duplicate_binding_remain_refused(self):
        original = retain(self.originals)
        original_items = [(r['state'], r['kind'], r['payload']) for r in self.events]
        variants = [original_items[:-1]+[('BLOCKED', 'other_error', {'reason':'other'})],
                    original_items[:1]+original_items,
                    [('PASSED', 'earlier_success', {})]+original_items]
        for items in variants:
            events = chain(items)
            receipt = {**self.receipt, 'ledger_head_sha256': events[-1]['event_sha256']}
            receipt['content_sha256'] = canonical_hash(receipt, {'content_sha256'})
            summary = {**self.summary, 'receipt_sha256': receipt['content_sha256']}
            changed = deepcopy(original)
            for name, raw in [('events.jsonl', b''.join(encoded(r) for r in events)),
                              ('receipt.json', encoded(receipt)), ('summary.json', encoded(summary))]:
                self.replace_document(changed, name, raw)
            changed['event_head_sha256'] = events[-1]['event_sha256']
            changed['receipt_sha256'] = receipt['content_sha256']; self.rehash(changed)
            with self.subTest(items=items), self.assertRaises(ValueError): validate(changed)

    def test_incomplete_journal_duplicate_json_boolean_size_and_extra_file_refuse(self):
        original = retain(self.originals)
        bad_events = self.originals['events.jsonl'].rstrip(b'\n')
        duplicate_summary = self.originals['summary.json'].replace(b'{', b'{"status":"blocked",', 1)
        for name, raw in [('events.jsonl', bad_events), ('summary.json', duplicate_summary)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(self.replace_document(deepcopy(original), name, raw))
        changed = deepcopy(original); changed['documents']['receipt.json']['bytes'] = True
        with self.assertRaises(ValueError): validate(self.rehash(changed))
        changed = deepcopy(original); changed['documents']['extra.json'] = changed['documents']['receipt.json']
        with self.assertRaises(ValueError): validate(self.rehash(changed))

    def test_jointly_rehashed_receipt_and_summary_cannot_change_work_order_or_attempt_shape(self):
        original = retain(self.originals)
        for field, replacement in (('work_order_sha256', '0'*64), ('attempts', True),
                                    ('repair_loops', 1)):
            with self.subTest(field=field):
                receipt = {**self.receipt, field: replacement}
                receipt['content_sha256'] = canonical_hash(receipt, {'content_sha256'})
                summary = {**self.summary, 'receipt_sha256': receipt['content_sha256']}
                if field == 'attempts': summary['attempts'] = replacement
                changed = deepcopy(original)
                self.replace_document(changed, 'receipt.json', encoded(receipt))
                self.replace_document(changed, 'summary.json', encoded(summary))
                changed['receipt_sha256'] = receipt['content_sha256']; self.rehash(changed)
                with self.assertRaises(ValueError): validate(changed)

    def test_native_failure_writer_format_retains_originals_without_admission_claim(self):
        from lightyear_factory.ledger import RunLedger
        from lightyear_factory.orchestrator import FactoryOrchestrator
        # Invoke only the native terminal writer. Synthetic accounting boundaries
        # do not create admission, run a controller, sign or execute a provider.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = RunLedger(root/'events.jsonl')
            for event in self.events[:-1]:
                ledger.append(event['state'], event['kind'], event['payload'])
            controller = object.__new__(FactoryOrchestrator)
            order = SimpleNamespace(content_sha256=self.identity['work_order_sha256'])
            failure_accounting = {'public_synthetic_fixture': True}
            with patch.object(controller, '_checkpoint_accounting') as checkpoint, \
                    patch.object(controller, '_failure_accounting', return_value=failure_accounting):
                controller._record_isolation_failure(root, order, 1, ledger)
            checkpoint.assert_called_once_with()
            originals = dict(self.originals)
            for name in ('receipt.json', 'summary.json', 'events.jsonl'):
                originals[name] = (root/name).read_bytes()
            before = deepcopy(originals)
            value = retain(originals)
            self.assertTrue(validate(value))
            self.assertEqual(originals, before)
            receipt = json.loads(originals['receipt.json'])
            self.assertEqual(receipt['attempts'], 1)
            self.assertEqual(receipt['failure_accounting'], failure_accounting)
            for name in before:
                self.assertEqual(base64.b64decode(value['documents'][name]['base64']), before[name])
            self.assertFalse(value['controller_origin_verified'])
            self.assertFalse(value['expected_refusal_verified'])
            self.assertFalse(value['accounting_semantics_verified'])
            self.assertFalse(value['qualifies_for_factory_receipt'])
if __name__ == '__main__':
    unittest.main()
