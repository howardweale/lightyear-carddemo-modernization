import tempfile
import unittest
import io
import json
from pathlib import Path

from tools.b06_host_probe.native_memory import run, stacks_source
from tools.check_source_lf import check_paths
from tools.b06_host_probe.stream_supplement import scan
from tools.b06_host_probe.memory_report import linear_fit, histogram
from lightyear_calibration.contracts import seal


class MemoryProfileTests(unittest.TestCase):
    def test_projection_uses_event_count_and_histogram_is_shallow(self):
        rows = [dict(events=n,heap_used_after_gc=4000000+600*n) for n in (1000,100000,236000)]
        fit = linear_fit(rows,1000)
        self.assertEqual(600,fit['bytes_per_event'])
        self.assertEqual(142694800,fit['fitted_bytes'])
        self.assertLess(fit['fitted_bytes'],192*1024**2)
        self.assertEqual([dict(instances=10,shallow_bytes=240,class_name='java.lang.String')],
                         histogram(' 1: 10 240 java.lang.String\nTotal 10 240'))

    def test_supplement_checks_chain_and_exports_no_payload(self):
        first=seal(dict(event={'kind':'ready','sequence':1},previous_sha256=None))
        second=seal(dict(event={'kind':'diagnostic-unmatched-return','sequence':2,'private_payload':'DO-NOT-EXPORT'},previous_sha256=first['content_sha256']))
        raw=b''.join((json.dumps(row)+'\n').encode() for row in (first,second))
        result=scan(io.BytesIO(raw))
        self.assertEqual([2],result['accepted_unmatched_return_sequences'])
        self.assertNotIn('DO-NOT-EXPORT',json.dumps(result))
        second['previous_sha256']='wrong';second=seal({k:v for k,v in second.items() if k!='content_sha256'})
        raw=b''.join((json.dumps(row)+'\n').encode() for row in (first,second))
        with self.assertRaisesRegex(ValueError,'supplement-event-chain'):
            scan(io.BytesIO(raw))
    def test_volume_fixture_has_3000_classes_on_30_deep_paths(self):
        source = stacks_source()
        self.assertEqual(source.count('class MemoryStack'), 3001)  # facade plus real stack classes
        for group in range(30):
            self.assertIn(f'MemoryStack{group*100}.walk(work)', source)
            self.assertIn(f'class MemoryStack{group*100+99}', source)
        self.assertEqual(source.count('{work.run();}'), 30)

    def test_baseline_refuses_wrong_heap_or_reduced_volume_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'result'
            for kwargs in ({'heap':193}, {'iterations':1399}, {'suppress_every':99}):
                with self.assertRaisesRegex(ValueError, 'native-volume-baseline-scope'):
                    run(Path(tmp),out,**kwargs)
            self.assertFalse(out.exists())

    def test_changed_markdown_utf8_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'change.md'
            p.write_text('# Review 291\u2013302\n', encoding='utf-8')
            check_paths(tmp,['change.md'])
            p.write_bytes(b'# invalid \x96')
            with self.assertRaisesRegex(ValueError,'markdown-not-utf8'):
                check_paths(tmp,['change.md'])
            p.write_text('# 291\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u0153302',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'markdown-mojibake'):
                check_paths(tmp,['change.md'])
