"""Synthetic integrity tests, never substitutes for native qualification."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import canonical, digest, seal
from lightyear_calibration.b06_posting_probe import queries_for
from tools.ms94_b06_admission import EvidenceFailure
from tools.ms94_b06_native_gate import evaluate
from lightyear_calibration.ms94_v3_errors import BusinessViolation
from tools.ms94_b06_posting_replay import replay_stream, origin, SUPPORT, CANDIDATE


class PostingReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.classes = {name: {'constant_pool_sha256': 'a'*64, 'methods': methods} for name, methods in {
            'org.compiere.model.PO': {'lock()Z': 'b'*64},
            CANDIDATE: {'test()V': 'c'*64}, SUPPORT: {'postOnce()V': 'd'*64}}.items()}
        self.frames = [self.frame('org.compiere.model.PO', 'lock', '()Z', 'b'*64),
                       self.frame(CANDIDATE, 'test', '()V', 'c'*64)]
        self.events = [{'kind': 'ready', 'checkpoint': False},
            {'kind': 'method-entry', 'checkpoint': True, 'thread': 1, 'document': [318, 123], 'frames': self.frames},
            {'kind': 'method-exit', 'checkpoint': True, 'thread': 1, 'document': [318, 123],
             'frames': self.frames, 'call_sequence': 2, 'return_value': True},
            {'kind': 'vm-death', 'checkpoint': False}]

    @staticmethod
    def frame(name, method, signature, code):
        return {'class': name, 'method': method, 'signature': signature,
                'constant_pool_sha256': 'a'*64, 'method_sha256': code, 'loader': '1', 'code_index': 0}

    def write(self, events=None):
        previous, rows = None, []
        for sequence, event in enumerate(copy.deepcopy(events or self.events), 1):
            event['sequence'] = sequence
            readback = None
            if 'document' in event:
                queries = queries_for('oracle', event['document'])
                capture = seal({'artifact_type': 'ms94-b06-posting-native-readback/1', 'lane': 'oracle',
                    'document': event['document'], 'event_sequence': sequence, 'read_only': True,
                    'application_vm_suspended': True, 'query_set_sha256': digest(queries),
                    'results': {k: {'sql': sql, 'rows': [{'value': 1}] if k == 'health' else []}
                                for k, sql in queries.items()}})
                (self.folder / ('readback-%06d.json' % sequence)).write_bytes(canonical(capture))
                readback = capture['content_sha256']
            item = seal({'event': event, 'previous_sha256': previous, 'readback_sha256': readback})
            rows.append(canonical(item)); previous = item['content_sha256']
        data = b'\n'.join(rows) + b'\n'
        (self.folder / 'events.jsonl').write_bytes(data)
        return {'event_file_sha256': hashlib.sha256(data).hexdigest(),
                'event_count': len(rows), 'last_event_sha256': previous}

    def call(self, receipt):
        return replay_stream(self.folder, receipt, self.classes, 'oracle')

    def test_reads_bound_bytes_chain_call_and_sql_capture(self):
        result = self.call(self.write())
        self.assertTrue(result['collection_complete'])
        self.assertEqual(result['observations'][0]['origin'], 'candidate')
        self.assertEqual(len(result['verified_capture_hashes']), 2)
        self.assertNotIn('attribution_qualified', result)

    def test_exception_unwind_is_not_a_successful_action(self):
        events = copy.deepcopy(self.events)
        events[2] = {'kind': 'exception', 'checkpoint': True, 'thread': 1, 'frames': self.frames,
                     'exception_class': 'java.sql.SQLException',
                     'exception_ancestry': ['java.sql.SQLException', 'java.lang.Exception', 'java.lang.Throwable', 'java.lang.Object'],
                     'caught': False, 'catch_location': None, 'unwound_calls': [2]}
        result = self.call(self.write(events))
        self.assertEqual(result['observations'], [])
        self.assertEqual(result['exceptions'][0]['exception_class'], 'java.sql.SQLException')

    def test_signed_shape_cannot_hide_wrong_bytecode_loader_return_or_lifecycle(self):
        for change in ('code', 'pool', 'loader', 'return', 'document', 'suspend', 'missing-return', 'unknown-kind'):
            with self.subTest(change=change):
                events = copy.deepcopy(self.events)
                # Break fixture aliasing to change just one observation.
                events[2]['frames'] = copy.deepcopy(events[2]['frames'])
                if change == 'code': events[2]['frames'][0]['method_sha256'] = 'e'*64
                elif change == 'pool': events[2]['frames'][0]['constant_pool_sha256'] = 'e'*64
                elif change == 'loader': events[2]['frames'][0]['loader'] = '2'
                elif change == 'return': events[2]['call_sequence'] = 1
                elif change == 'document': events[2]['document'] = [318, 124]
                elif change == 'suspend': events[1]['checkpoint'] = False
                elif change == 'missing-return': del events[2]
                else: events[2]['kind'] = 'asserted-candidate-action'
                with self.assertRaises(EvidenceFailure): self.call(self.write(events))

    def test_tampered_and_missing_readback_fail(self):
        receipt = self.write()
        path = self.folder / 'readback-000002.json'
        path.write_bytes(b'{}')
        with self.assertRaises(ValueError): self.call(receipt)
        path.unlink()
        with self.assertRaises(ValueError): self.call(receipt)

    def test_trailing_events_and_partial_stream_fail_even_with_recomputed_hash(self):
        for events in (self.events[:-1], self.events + [self.events[0]]):
            with self.assertRaises(EvidenceFailure): self.call(self.write(events))

    def test_unknown_helper_nearest_to_action_remains_outside(self):
        helper = self.frame('outside.Helper', 'run', '()V', 'd'*64)
        self.assertEqual(origin([self.frames[0], helper, self.frames[1]]), 'outside')
        self.assertEqual(origin([self.frames[0], self.frame(SUPPORT, 'postOnce', '()V', 'd'*64), self.frames[1]]), 'support')

    def test_closed_probe_rejects_identifier_injection_and_noninteger_key(self):
        for key in ([318, '123 OR 1=1'], [318, True], [1, 123], [318, -1]):
            with self.assertRaises(ValueError): queries_for('oracle', key)
        self.assertIn('clock_timestamp()', queries_for('postgresql', [318, 123])['clock'])

    def test_early_rejection_cannot_fabricate_full_entry_replay(self):
        with patch('tools.ms94_b06_native_gate.verify_run', side_effect=BusinessViolation('early')):
            with self.assertRaisesRegex(EvidenceFailure, 'before-entry-replay'):
                evaluate(self.folder, b'unused')


if __name__ == '__main__': unittest.main()
