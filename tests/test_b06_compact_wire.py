"""Small real-Java codec probe: no target JVM, JDI attachment or native application."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zlib

from tools.ms94_b06_observer_format import (FORMAT, DIAGNOSTIC_DICTIONARY,
    diagnostic_wire, audit_detail, java_json)
from tools.ms94_b06_observer_audit import Audit


def encode(event, body=None):
    body=body if body is not None else {k:v for k,v in event.items() if k not in ('kind','sequence','checkpoint')}
    raw=java_json(body).encode('utf-8'); compressor=zlib.compressobj(zdict=DIAGNOSTIC_DICTIONARY)
    packed=compressor.compress(raw)+compressor.flush()
    return {**{k:event[k] for k in ('kind','sequence','checkpoint')},'d3':base64.b64encode(packed).decode()}


def example():
    return dict(kind='observer-audit',policy='structural-jdi-v2',audit_index=1,event_set_id=1,event_position=0,
                action='jdi-event',detail=dict(event_type='vm-start',request_id=0,set_size=1,suspend_policy=2),
                observer_format=FORMAT,sequence=1,checkpoint=False)


class CompactWireTests(unittest.TestCase):
    def test_logical_round_trip_and_original_wire_quota(self):
        event=example(); wire=encode(event); original=copy.deepcopy(wire)
        self.assertEqual(event,diagnostic_wire(wire));self.assertEqual(event,audit_detail(wire))
        audit=Audit();audit.event(wire)
        self.assertEqual(len(java_json(wire).encode()),audit.bytes)
        metadata=dict(kind='breakpoint-lifecycle',action='created',request_id=72,thread_filter=None,
                      location=None,request_kind='class-prepare',monotonic_ns=9007199254740993,audit_index=1,
                      sequence=2,checkpoint=False,observer_format=FORMAT)
        compact=encode(metadata);audit.metadata(compact)
        self.assertEqual(metadata,diagnostic_wire(compact))
        self.assertEqual(sum(len(java_json(e).encode()) for e in (wire,compact)),audit.bytes)
        self.assertEqual(2,audit.diagnostic_count);self.assertEqual(original,wire)
        self.assertIs(event,diagnostic_wire(event))

    def test_all_metadata_fields_survive_without_fixed_schema_loss(self):
        for kind in ('breakpoint-lifecycle','watched-class-prepare','observer-heap-telemetry'):
            event=dict(kind=kind,sequence=1,checkpoint=False,observer_format=FORMAT,
                       future_field={'unicode':'\u2603\n','values':[None,False,7]},monotonic_ns=9223372036854775807)
            self.assertEqual(event,diagnostic_wire(encode(event)))

    def test_offline_consumers_keep_original_sealed_wire(self):
        import io
        from lightyear_calibration.contracts import seal
        from tools.b06_host_probe.stream_supplement import scan
        from tools.ms94_b06_engineering import refusal_context
        logical=example();logical['detail'].update(thread_id=42,depth=123,location={'method':'spinInnerClass'})
        first=seal(dict(event=encode(logical),previous_sha256=None))
        refusal=dict(kind='observer-audit',action='dispatch-refused',sequence=2,
                     audit_index=2,event_set_id=1,event_position=0,detail={'exception_class':'fixture.Refusal'})
        second=seal(dict(event=refusal,previous_sha256=first['content_sha256']))
        raw=b''.join((json.dumps(row)+'\n').encode() for row in (first,second))
        result=scan(io.BytesIO(raw))
        self.assertEqual(42,result['last_jdi_event']['thread_id'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),result['stream_sha256'])
        self.assertEqual(second['content_sha256'],result['last_event_sha256'])
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'posting-observer/oracle';folder.mkdir(parents=True)
            (folder/'events.jsonl').write_bytes(raw)
            context=refusal_context(Path(temp))
            self.assertEqual(logical,context['preceding_event'])
            self.assertEqual(refusal,context['refusal'])

    def test_shape_corruption_and_collisions_fail_closed(self):
        original=encode(example())
        for changes in ({'kind':'generation-entry'},{'checkpoint':True},{'sequence':True},{'extra':1},
                        {'d3':original['d3']+'='},{'d3':'!'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):diagnostic_wire({**original,**changes})
        body={k:v for k,v in example().items() if k not in ('kind','sequence','checkpoint')}
        for changes in ({'kind':'generation-entry'},{'sequence':99},{'checkpoint':True},{'d3':'nested'},
                        {'observer_format':'unknown'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):diagnostic_wire(encode(example(),{**body,**changes}))
        for raw in (b'{"observer_format":"bounded-observer-v1","x":1,"x":2}',
                    b'{"observer_format":"bounded-observer-v1","x":NaN}',
                    b'x'*(256*1024+1)):
            compressor=zlib.compressobj(zdict=DIAGNOSTIC_DICTIONARY);value=compressor.compress(raw)+compressor.flush()
            with self.assertRaises(ValueError):diagnostic_wire({**original,'d3':base64.b64encode(value).decode()})
        compressed=base64.b64decode(original['d3'])
        for value in (compressed+b'trailing',compressed[:-1],zlib.compress(b'{}')):
            with self.assertRaises(ValueError):diagnostic_wire({**original,'d3':base64.b64encode(value).decode()})

    @unittest.skipUnless(os.environ.get('B06_HOST_JDK'),'host JDK explicitly enabled')
    def test_real_java_encoder_matches_python_dictionary_and_decoder(self):
        root=Path(__file__).resolve().parents[1];jdk=Path(os.environ['B06_HOST_JDK'])/'bin'
        suffix='.exe' if os.name=='nt' else ''
        probe=r'''import java.util.*;import java.io.*;import java.lang.reflect.*;import java.security.*;
public class DiagnosticCodecProbe {
 public static void main(String[] args)throws Exception {
  Class<?> type=Class.forName("lightyear.observer.PostingObserver");
  Class<?> dictionary=Class.forName("lightyear.observer.PostingObserver$DiagnosticDictionary");
  Field bytes=dictionary.getDeclaredField("BYTES");bytes.setAccessible(true);
  System.err.println(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest((byte[])bytes.get(null))));
  Method emit=type.getDeclaredMethod("emitDiagnostic",Map.class);emit.setAccessible(true);
  Constructor<?> constructor=type.getDeclaredConstructor();constructor.setAccessible(true);Object observer=constructor.newInstance();
  Method write=type.getDeclaredMethod("writeJson",Writer.class,Object.class,boolean.class);write.setAccessible(true);
  Map<String,Object> event=new LinkedHashMap<>();event.put("kind","breakpoint-lifecycle");event.put("action","deleted");
  event.put("request_id",42);event.put("thread_filter",null);event.put("location",null);event.put("request_kind","breakpoint");
  event.put("monotonic_ns",9007199254740993L);event.put("audit_index",17);event.put("observer_format","bounded-observer-v1");
  event.put("sequence",23);event.put("checkpoint",false);event.put("future_field","snowman \u2603\n");
  emit.invoke(observer,event);
  Map<String,Object> refusal=new LinkedHashMap<>();refusal.put("kind","observer-audit");refusal.put("action","dispatch-refused");
  refusal.put("detail",Map.of("exception_class","java.lang.IllegalStateException","context",Map.of("full","preserved")));
  emit.invoke(observer,refusal);Field count=type.getDeclaredField("auditBytes");count.setAccessible(true);System.err.println(count.getLong(observer));
 }
}'''
        with tempfile.TemporaryDirectory(prefix='b06-codec-') as directory:
            out=Path(directory);(out/'DiagnosticCodecProbe.java').write_text(probe,encoding='utf-8')
            subprocess.run([str(jdk/('javac'+suffix)),'--add-modules','jdk.jdi','-d',str(out),
                            str(root/'factory/idempiere/b06-observer/PostingObserver.java'),str(out/'DiagnosticCodecProbe.java')],
                           check=True,capture_output=True,timeout=60)
            result=subprocess.run([str(jdk/('java'+suffix)),'-Xmx192m','--add-modules','jdk.jdi','-cp',str(out),
                                   'DiagnosticCodecProbe'],check=True,capture_output=True,timeout=30)
        lines=result.stdout.splitlines();stderr=result.stderr.decode().splitlines()
        self.assertEqual(hashlib.sha256(DIAGNOSTIC_DICTIONARY).hexdigest(),stderr[0])
        self.assertEqual(sum(map(len,lines)),int(stderr[1]))
        self.assertEqual(2,len(lines));self.assertIn('d3',json.loads(lines[0]))
        refusal=json.loads(lines[1]);self.assertNotIn('d3',refusal)
        self.assertEqual({'full':'preserved'},refusal['detail']['context'])
        event=diagnostic_wire(json.loads(lines[0]))
        self.assertEqual(9007199254740993,event['monotonic_ns']);self.assertIsNone(event['thread_filter'])
        self.assertEqual('snowman \u2603\n',event['future_field']);self.assertEqual('deleted',event['action'])


if __name__=='__main__':unittest.main()
