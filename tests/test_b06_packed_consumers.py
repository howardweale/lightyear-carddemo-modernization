"""Analysis views decode packed details without changing authenticated wire data."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from lightyear_calibration.contracts import seal
from tools.b06_host_probe.captured_refusal import derive
from tools.b06_host_probe.stream_supplement import scan
from tools.ms94_b06_observer_format import FORMAT


def packed(detail):
    raw = json.dumps(detail, separators=(',', ':')).encode()
    return dict(encoding='deflate-json-v1', base64=base64.b64encode(zlib.compress(raw)).decode(),
                bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def chain(events):
    rows = []; previous = None
    for sequence, event in enumerate(events, 1):
        row = seal(dict(event=dict(event, sequence=sequence), previous_sha256=previous))
        previous = row['content_sha256']; rows.append(row)
    return b''.join((json.dumps(row)+'\n').encode() for row in rows), previous


class PackedConsumerTests(unittest.TestCase):
    def test_supplement_expands_analysis_but_hashes_original_wire_and_counts_binary(self):
        detail = dict(event_type='breakpoint', thread_id=42, depth=120,
                      location=dict(method='spinInnerClass'))
        audit = dict(kind='observer-audit', observer_format=FORMAT, audit_index=1,
                     event_set_id=1,event_position=0,action='jdi-event',detail=packed(detail))
        entry = dict(kind='generation-entry',observer_format=FORMAT,
                     record=dict(entry_depth=120,definition_input_base64=base64.b64encode(b'ABC\x00').decode()))
        raw, last = chain([audit, entry]); result = scan(io.BytesIO(raw))
        self.assertEqual(detail, result['last_jdi_event'])
        self.assertEqual(4, result['payload_sizes']['definition_input_bytes']['max'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result['stream_sha256'])
        self.assertEqual(last, result['last_event_sha256'])
        self.assertEqual({'observer-audit':1,'generation-entry':1}, result['event_counts'])
        self.assertNotIn('definition_input_base64', json.dumps(result))
        bad = copy.deepcopy(audit); bad['detail']['sha256'] = '0'*64
        with self.assertRaises(ValueError): scan(io.BytesIO(chain([bad])[0]))

    def refusal(self, mutate=None, packed_mode=True):
        calls = [dict(generation_id=i, method='java.lang.invoke.LambdaForm.compileToBytecode', depth=120+i)
                 for i in (1, 2)]
        events = [dict(kind='generation-entry', record=dict(thread_id=42,generation_id=c['generation_id'],
                    entry_method=c['method'],entry_depth=c['depth'])) for c in calls]
        detail = dict(event_type='breakpoint',thread_id=42,depth=122,
                      location=dict(**{'class':'java.lang.invoke.LambdaForm'},method='compileToBytecode'),
                      pending=[calls[-1]['generation_id']] if packed_mode else list(reversed(calls)))
        if packed_mode: detail['pending_count'] = 2
        if mutate: mutate(detail)
        event = dict(kind='observer-audit',action='jdi-event',event_set_id=1,event_position=0,
                     detail=packed(detail) if packed_mode else detail)
        if packed_mode:event['observer_format']=FORMAT
        events.extend([event,dict(kind='observer-audit',action='dispatch-refused',
                                 detail={'exception_class':'java.lang.IllegalStateException'})])
        raw,last=chain(events)
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'events.jsonl').write_bytes(raw)
            common=dict(complete=False,event_count=4,last_event_sha256=last,plan_sha256='p',content_sha256='s')
            (folder/'frame-census.json').write_text(json.dumps(dict(common,event_file_sha256=hashlib.sha256(raw).hexdigest())))
            (folder/'failure.json').write_text(json.dumps(common))
            with patch('tools.b06_host_probe.captured_refusal.signed'), patch('tools.b06_host_probe.captured_refusal.Audit') as factory:
                audit=factory.return_value;audit.refused=True;audit.count=2
                result=derive(folder,b'unused')
                # The validator sees packed wire; expansion is confined to the exported view.
                observed=audit.event.call_args_list[0].args[0]['detail']
                self.assertEqual(packed_mode, 'encoding' in observed)
        return result

    def test_refusal_keeps_bounded_pending_limit_explicit(self):
        result=self.refusal()
        self.assertEqual(42,result['thread'])
        self.assertEqual(2,result['remaining_open_calls'])
        self.assertIn('omitted pending entries are not witnessed',result['pending_proof'])
        detail=result['thread_events'][-1]['detail']
        self.assertEqual(2,detail['pending_count']);self.assertEqual(1,len(detail['pending']))
        self.assertNotIn('encoding',detail)

    def test_refusal_rejects_changed_count_or_top(self):
        for mutate in (lambda d:d.update(pending_count=3),
                       lambda d:d.update(pending=[99])):
            with self.assertRaisesRegex(ValueError,'pending.*differs'):self.refusal(mutate)

    def test_historical_full_pending_behavior_is_unchanged(self):
        result=self.refusal(packed_mode=False)
        self.assertNotIn('pending_proof',result)
        self.assertEqual(2,len(result['thread_events'][-1]['detail']['pending']))


if __name__=='__main__':unittest.main()
