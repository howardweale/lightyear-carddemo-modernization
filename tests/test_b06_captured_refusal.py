import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from tools.b06_host_probe.captured_refusal import reproduce

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/b06-generation-prefix/diagnostic-r1.json'
PIN='9c310442cd9f25dca92a37b25f7d79bbe6038306a91c71c97d622f6dc2add447'

class CapturedRefusalTests(unittest.TestCase):
    def fixture(self):
        raw=FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),PIN)
        return json.loads(raw)

    def test_recorded_thread_has_balanced_inner_call_but_no_outer_entry(self):
        f=self.fixture();pending=[]
        for e in f['thread_events']:
            if e['kind']=='generation-entry': pending.append((e['generation_id'],e['method'],e['depth']))
            elif e['kind']=='generation-return':
                self.assertEqual(pending.pop(),(e['generation_id'],e['method'],e['depth']))
        self.assertEqual(pending,[])
        self.assertEqual(f['event_sequence'],231089)
        self.assertEqual(f['refusal_sequence'],231090)
        d=f['thread_events'][-1]['detail']
        self.assertEqual(d['location']['method'],'spinInnerClass')
        self.assertEqual(d['depth'],25)
        self.assertEqual(d['pending'],[])
        self.assertFalse(f['tracker_fix_proven'])

    def test_invented_entry_or_changed_location_is_not_the_recorded_failure(self):
        for mutate in ('pending','top_location','return_breakpoint'):
            f=self.fixture();d=f['thread_events'][-1]['detail']
            if mutate=='pending': d['pending']=[{'generation_id':12395}]
            elif mutate=='top_location': d['top_location']['code_index']+=1
            else:d['return_breakpoint']=False
            with self.assertRaisesRegex(ValueError,'not the captured'):
                reproduce(f,Path('unused'),Path('unused'))

    @unittest.skipUnless(os.environ.get('B06_HOST_JDK'),'host JDK explicitly enabled')
    def test_exact_production_java_guard_reproduces_captured_refusal(self):
        r=reproduce(self.fixture(),ROOT/'factory/idempiere/b06-observer/PostingObserver.java',
                    Path(os.environ['B06_HOST_JDK']))
        self.assertTrue(r['exact_guard_exception_reproduced'])
        self.assertEqual(r['event_sequence'],231089)
        self.assertFalse(r['tracker_fix_proven'])
        self.assertFalse(r['target_jvm_executed'])

if __name__=='__main__':unittest.main()
