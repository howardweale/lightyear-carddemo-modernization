import base64
import copy
import unittest
from tools.ms94_b06_observer_format import normalize, FORMAT, diagnostic_wire
from tools.ms94_b06_observer_v2 import Replay
from tools.ms94_b06_observer_audit import Audit
from test_b06_observer_audit import record
from test_ms94_b06_observer_v2 import minimal

class BoundedFormatTests(unittest.TestCase):
    def test_lossless_diagnostic_detail_bounds_and_tampering(self):
        import hashlib,json,zlib
        from tools.ms94_b06_observer_format import audit_detail
        detail={'event_type':'breakpoint','thread_id':7,'location':{'method':'x'*2000},'pending':[]}
        raw=json.dumps(detail,separators=(',',':')).encode()
        packed={'encoding':'deflate-json-v1','base64':base64.b64encode(zlib.compress(raw)).decode(),
                'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        event={'observer_format':FORMAT,'kind':'observer-audit','action':'jdi-event','detail':packed}
        self.assertEqual(audit_detail(event)['detail'],detail)
        self.assertIs(event['detail'],packed)
        for update in ({'bytes':len(raw)-1},{'sha256':'0'*64},{'base64':packed['base64']+'==='},
                       {'base64':base64.b64encode(zlib.compress(raw)+b'extra').decode()},
                       {'base64':base64.b64encode(zlib.compress(b'x'*(256*1024+1))).decode()}):
            with self.subTest(update=list(update)),self.assertRaises(ValueError):
                audit_detail({**event,'detail':{**packed,**update}})

    def test_historical_shape_passes_unchanged(self):
        old={'kind':'generation-entry','record':{'definition_input_hex':'ff'}}
        self.assertIs(normalize(old),old)

    def test_versioned_definition_retains_exact_executable_bytes(self):
        row,d,f=minimal()
        d['constant_pool_base64']=base64.b64encode(bytes.fromhex(d.pop('constant_pool_hex'))).decode()
        d['methods'][0]['bytecode_base64']=base64.b64encode(bytes.fromhex(d['methods'][0].pop('bytecode_hex'))).decode()
        r=Replay([row]);r.event({'kind':'class-definition-v3','observer_format':FORMAT,'definition':d})
        self.assertEqual(r.frames([f]),[f])
        for bad in ('!','YQ','YQ==='):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                normalize({'kind':'generation-entry','observer_format':FORMAT,'record':{'definition_input_base64':bad}})

    def test_sparse_return_binds_original_entry_and_rejects_replacement(self):
        entry=dict(kind='generation',thread_id=3,generation_id=7,entry_depth=9,
                   entry_method='java.lang.invoke.InnerClassLambdaMetafactory.spinInnerClass()Ljava/lang/Class;',
                   entry_event_index=22,lambda_factory={'targetClass':{'class_object_id':1}},stack=[{'private':'fixture'}])
        tail={k:entry[k] for k in ('kind','thread_id','generation_id','entry_depth','entry_method','entry_event_index')}
        tail['returned_class']={'class_object_id':8}
        r=Replay([]);r.event({'kind':'generation-entry','observer_format':FORMAT,'record':entry})
        r.event({'kind':'generation-return','observer_format':FORMAT,'record':tail})
        self.assertEqual(r.factories['8']['stack'],entry['stack'])
        for changed in ({'generation_id':8},{'stack':[]},{'entry_event_index':23}):
            r=Replay([]);r.event({'kind':'generation-entry','observer_format':FORMAT,'record':entry})
            with self.assertRaisesRegex(ValueError,'observer-bounded'):
                r.event({'kind':'generation-return','observer_format':FORMAT,'record':{**tail,**changed}})

    def test_aggregated_resume_requires_exact_counters_and_policy_stability(self):
        def v2(*args,**kwargs):
            return {**record(*args,**kwargs),'policy':'structural-jdi-v2','observer_format':FORMAT}
        for count in (0,1,2):
            audit=Audit();audit.event(v2(1,'event-set-open',-1,dict(size=1,suspend_policy=2)))
            audit.event(v2(2,'jdi-event',0,dict(event_type='vm-start',request_id=0)))
            event=v2(3,'event-set-close',0,dict(dispatch_completed=count,resume_requested=1,resume_completed=1))
            if count==1:
                audit.event(event);self.assertTrue(audit.resumed)
            else:
                with self.assertRaises(ValueError):audit.event(event)
        with self.assertRaises(ValueError):audit.event(record(4,'event-set-open',-1,dict(size=1,suspend_policy=2),set_id=2))


import os
import tempfile
from pathlib import Path
from test_b06_observer_audit import host_capture

@unittest.skipUnless(os.environ.get('B06_HOST_JDK'), 'host JDK explicitly enabled')
class BoundedHostTests(unittest.TestCase):
    def test_actual_bounded_jdi_emission_and_ten_unmatched_cap(self):
        jdk=Path(os.environ['B06_HOST_JDK'])/'bin'
        java=jdk/('java.exe' if os.name=='nt' else 'java')
        javac=jdk/('javac.exe' if os.name=='nt' else 'javac')
        source=(Path(__file__).resolve().parents[1]/'factory/idempiere/b06-observer/PostingObserver.java').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            for diagnostic in (False,True):
                observed,events,_=host_capture(java,javac,source,Path(tmp)/str(diagnostic),bounded=True,diagnostic=diagnostic)
                self.assertEqual(events[0]['kind'],'ready')
                self.assertEqual(events[0]['observer_format'],FORMAT)
                audit=Audit()
                for event in events:
                    if event['kind']=='observer-audit':audit.event(event)
                    elif event['kind'] in ('breakpoint-lifecycle','watched-class-prepare','observer-heap-telemetry'):audit.metadata(event)
                if diagnostic:
                    self.assertNotEqual(observed.returncode,0)
                    self.assertEqual(sum(e['kind']=='diagnostic-unmatched-return' for e in events),10)
                    stop=next(e for e in events if e['kind']=='observer-resource-limit')
                    self.assertEqual(stop['reason'],'unmatched-return-cap-10')
                    self.assertTrue(stop['checkpoint'])
                else:
                    self.assertEqual(observed.returncode,0,observed.stderr)
                    audit.complete()
                    self.assertTrue(any(e['kind']=='class-definition-v3' for e in events))
                    self.assertTrue(any(e['kind']=='breakpoint-lifecycle' and diagnostic_wire(e)['action']=='deleted' for e in events))
                    self.assertTrue(all('stack' not in e['record'] for e in events if e['kind']=='generation-return'))
                    self.assertEqual(sum(e['kind']=='generation-entry' for e in events),sum(e['kind']=='generation-return' for e in events))
