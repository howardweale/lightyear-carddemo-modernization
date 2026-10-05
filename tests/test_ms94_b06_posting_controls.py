"""Synthetic Oracle/PG observer streams; zero native qualification credit."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from lightyear_calibration.contracts import canonical, digest, seal
from lightyear_calibration.b06_posting_probe import queries_for
from tools.ms94_b06_posting_replay import replay_stream, SUPPORT, CANDIDATE, TERMINAL, TERMINAL_SIGNATURE
from tools.ms94_b06_posting_cause import derive

PO, DOC, DB = 'org.compiere.model.PO', 'org.compiere.acct.Doc', 'org.compiere.util.DB'
SIG = {PO: ('lock', '()Z'), DOC: ('post', '(ZZZ)Ljava/lang/String;'),
       DB: ('executeUpdate', '(Ljava/lang/String;Ljava/lang/String;)I'),
       SUPPORT: ('postOnce', '(Lorg/compiere/model/PO;[Lorg/compiere/model/MAcctSchema;)V'),
       CANDIDATE: ('test', '()V'), TERMINAL: ('executionFinished', TERMINAL_SIGNATURE),
       'org.junit.platform.engine.support.hierarchical.NodeTestTask': ('call', '()V')}


def frame(name):
    method, signature = SIG.get(name, ('call', '()V'))
    return {'class': name, 'method': method, 'signature': signature, 'loader': '1',
            'constant_pool_sha256': 'a' * 64, 'method_sha256': 'b' * 64, 'code_index': 0}


def event(kind, sequence, name, key=(318, 123), callers=(), **fields):
    return {'kind': kind, 'sequence': sequence, 'checkpoint': True, 'thread': 1,
            'document': list(key), 'frames': [frame(n) for n in (name, *callers)], **fields}


def control(kind):
    caller = SUPPORT if kind == 'support-origin' else 'outside.Helper' if kind == 'outside-origin' else CANDIDATE
    key = (318, 999) if kind == 'wrong-document' else (318, 123)
    events = [{'kind': 'ready', 'checkpoint': False, 'sequence': 1},
              event('method-entry', 2, PO, key, (caller,)),
              event('method-exit', 3, PO, key, (caller,), call_sequence=2, return_value=True),
              event('method-entry', 4, SUPPORT, callers=(CANDIDATE,)),
              event('method-entry', 5, DOC, callers=(SUPPORT, CANDIDATE), force=False, repost=False),
              event('method-entry', 6, DB, callers=(DOC, SUPPORT, CANDIDATE), force=False, repost=False,
                    sql="UPDATE c_invoice SET Processing='Y' WHERE c_invoice_ID=123 AND Processed='Y' AND IsActive='Y' AND (Processing='N' OR Processing IS NULL) AND Posted IN ('N','d')"),
              event('method-exit', 7, DB, callers=(DOC, SUPPORT, CANDIDATE), call_sequence=6, return_value=0),
              event('method-exit', 8, DOC, callers=(SUPPORT, CANDIDATE), call_sequence=5, return_value='private localized reason'),
              {'kind': 'exception', 'sequence': 9, 'checkpoint': True, 'thread': 1,
               'exception_id': 99,
               'frames': [frame(SUPPORT), frame(CANDIDATE)], 'exception_class': 'java.lang.AssertionError',
               'exception_ancestry': ['java.lang.AssertionError', 'java.lang.Error', 'java.lang.Throwable', 'java.lang.Object'],
               'caught': True, 'catch_location': {'class': 'org.junit.Engine'}, 'unwound_calls': [4]},
              {'kind': 'test-terminal', 'sequence': 10, 'checkpoint': True, 'thread': 1,
               'frames': [frame(TERMINAL), frame('org.junit.platform.engine.support.hierarchical.NodeTestTask')],
               'descriptor_id': 1, 'test_class': CANDIDATE, 'test_method': 'test', 'status': 'FAILED', 'exception_id': 99},
              {'kind': 'vm-death', 'sequence': 11, 'checkpoint': False}]
    if kind == 'genuine-equipment-fault':
        events[8]['exception_class'] = 'java.sql.SQLException'
        events[8]['exception_ancestry'] = ['java.sql.SQLException', 'java.lang.Exception', 'java.lang.Throwable', 'java.lang.Object']
    if kind == 'prior-post':
        events = [events[0], event('method-entry', 2, DOC, callers=(CANDIDATE,), force=False, repost=False),
                  event('method-exit', 3, DOC, callers=(CANDIDATE,), call_sequence=2, return_value=None),
                  events[3], event('method-exit', 5, SUPPORT, callers=(CANDIDATE,), call_sequence=4, return_value=None),
                  {'kind': 'vm-death', 'sequence': 6, 'checkpoint': False}]
    return events


def write_stream(folder, lane, events, prior_post=False):
    lines, previous = [], None
    for e in events:
        capture = None
        if e.get('document'):
            n = e['sequence']; queries = queries_for(lane, e['document'])
            row = {'record_id': e['document'][1], 'processed': 'Y', 'isactive': 'Y',
                   'processing': 'N' if n == 2 or prior_post else 'Y',
                   'posted': 'Y' if prior_post and n > 2 else 'N'}
            capture = seal({'artifact_type': 'ms94-b06-posting-native-readback/1', 'lane': lane,
                'document': e['document'], 'event_sequence': n, 'read_only': True,
                'application_vm_suspended': True, 'query_set_sha256': digest(queries),
                'results': {k: {'sql': sql, 'rows': [row] if k == 'document' else [{'value': 1}] if k == 'health' else []}
                            for k, sql in queries.items()}})
            (folder / ('readback-%06d.json' % n)).write_bytes(canonical(capture))
        record = seal({'event': e, 'previous_sha256': previous,
                       'readback_sha256': capture['content_sha256'] if capture else None})
        previous = record['content_sha256']; lines.append(canonical(record))
    data = b'\n'.join(lines) + b'\n'; (folder / 'events.jsonl').write_bytes(data)
    return {'event_count': len(lines), 'event_file_sha256': hashlib.sha256(data).hexdigest(), 'last_event_sha256': previous}


class PostingControls(unittest.TestCase):
    def replay(self, lane, kind, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); events = control(kind)
            if mutate: mutate(events)
            receipt = write_stream(folder, lane, events, kind == 'prior-post')
            classes = {name: {'constant_pool_sha256': 'a' * 64, 'methods': {method + signature: 'b' * 64}}
                       for name, (method, signature) in SIG.items()}
            replayed = replay_stream(folder, receipt, classes, lane)
            from tools.ms94_b06_lock_sql import TEMPLATE
            return derive(replayed, seal({'artifact_type': 'ms94-b06-lock-sql-binding/1',
                                          'template': TEMPLATE, 'synthetic_unit_fixture': True}))

    def test_prior_lock_native_processing_flag_transition_derived_both_engines(self):
        for lane in ('oracle', 'postgresql'):
            result = self.replay(lane, 'prior-lock')
            self.assertEqual(result['cause'], 'candidate-prior-processing-flag')
            self.assertFalse(result['equipment_suspect'])
            self.assertEqual(len(result['capture_sha256']), 5)

    def test_prior_post_skip_is_not_fabricated_support_failure(self):
        for lane in ('oracle', 'postgresql'):
            self.assertEqual(self.replay(lane, 'prior-post')['cause'], 'no-posting-failure')

    def test_support_outside_wrong_document_and_equipment_remain_suspect(self):
        for lane in ('oracle', 'postgresql'):
            for kind in ('support-origin', 'outside-origin', 'wrong-document', 'genuine-equipment-fault'):
                with self.subTest(lane=lane, kind=kind):
                    result = self.replay(lane, kind)
                    self.assertTrue(result['equipment_suspect'])
                    self.assertNotIn('diagnostics', result)

    def test_similar_message_or_failed_lock_cannot_establish_cause(self):
        for lane in ('oracle', 'postgresql'):
            with self.assertRaisesRegex(ValueError, 'cause-lock-sql-template-differs'):
                self.replay(lane, 'prior-lock', lambda events: events[5].update(sql='UPDATE other SET Processing=1'))
            for index, field, value in ((2, 'return_value', False),
                                        (5, 'force', True), (6, 'return_value', 1),
                                        (8, 'catch_location', {'class': CANDIDATE}),
                                        (9, 'exception_id', 100), (9, 'thread', 2)):
                result = self.replay(lane, 'prior-lock', lambda events: events[index].update({field: value}))
                self.assertTrue(result['equipment_suspect'])


if __name__ == '__main__': unittest.main()
