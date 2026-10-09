"""Bounded JDI transport regression: byte fidelity and real suspended-VM collection."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(os.environ.get('B06_HOST_JDK'), 'host JDK probe explicitly enabled')
class BulkReadTests(unittest.TestCase):
    def tools(self):
        java = Path(os.environ['B06_HOST_JDK']) / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
        return java, java.with_name('javac.exe' if os.name == 'nt' else 'javac')

    def test_exact_slices_bounded_packets_and_invalid_reads(self):
        java, javac = self.tools()
        source = r'''package lightyear.observer;
import com.sun.jdi.*; import java.lang.reflect.Proxy; import java.util.*;
public class BulkProbe {
 static int requests; static boolean shortRead;
 static Object proxy(Class<?> t, java.lang.reflect.InvocationHandler h) {
  return Proxy.newProxyInstance(BulkProbe.class.getClassLoader(),new Class<?>[]{t},h);
 }
 static ByteValue value(byte b) {return (ByteValue)proxy(ByteValue.class,(p,m,a)-> {
  if(m.getName().equals("value"))return b;throw new AssertionError(m.getName());});}
 static ArrayReference array(byte[] raw) {return (ArrayReference)proxy(ArrayReference.class,(p,m,a)-> {
  if(m.getName().equals("length"))return raw.length;
  if(!m.getName().equals("getValues") || a.length!=2)throw new AssertionError("single-byte transport");
  int start=(Integer)a[0],count=(Integer)a[1];
  if(count>16384 || count<=0)throw new AssertionError("packet bound");
  requests++; List<Value> result=new ArrayList<>();
  for(int i=0;i<count-(shortRead?1:0);i++)result.add(value(raw[start+i]));return result;
 });}
 static void refused(Runnable r) {try {r.run();throw new AssertionError("accepted bad slice");}
  catch(IllegalStateException expected) {}}
 public static void main(String[] ignored) {
  byte[] data=new byte[1048600];for(int i=0;i<data.length;i++)data[i]=(byte)(i*31);
  ArrayReference a=array(data);
  for(int size:new int[]{0,1,16383,16384,16385,65537,1048576}) {
   requests=0;byte[] got=PostingObserver.readBytes(a,7,size);
   if(!Arrays.equals(got,Arrays.copyOfRange(data,7,7+size)))throw new AssertionError("bytes changed");
   if(requests!=(size+16383)/16384)throw new AssertionError("request count");
  }
  refused(()->PostingObserver.readBytes(a,-1,1));refused(()->PostingObserver.readBytes(a,0,-1));
  refused(()->PostingObserver.readBytes(a,0,1048577));refused(()->PostingObserver.readBytes(a,Integer.MAX_VALUE,1));
  refused(()->PostingObserver.readBytes(a,data.length,1));
  shortRead=true;refused(()->PostingObserver.readBytes(a,0,10));
  System.out.println("exact bytes; 1 MiB in 64 requests; all invalid slices refused");
 }
}'''
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); (p/'BulkProbe.java').write_text(source)
            observer = Path(__file__).resolve().parents[1]/'factory/idempiere/b06-observer/PostingObserver.java'
            subprocess.run([str(javac),'--add-modules','jdk.jdi','-d',str(p),str(observer),str(p/'BulkProbe.java')],check=True,capture_output=True,timeout=45)
            result = subprocess.run([str(java),'--add-modules','jdk.jdi','-cp',str(p),'lightyear.observer.BulkProbe'],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('1 MiB in 64 requests',result.stdout)

    def test_real_jdi_large_offset_definitions_and_hidden_bytes(self):
        java, javac = self.tools()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'Payload.java').write_text('package fixture; public class Payload {public static final String TEXT="'+('z'*40000)+'"; public int value(){return 47;}}')
            (p/'LoadProbe.java').write_text(r'''package fixture;
import java.nio.file.*;import java.lang.invoke.*;
public class LoadProbe extends ClassLoader {
 Class<?> load(byte[] b,int size){return defineClass("fixture.Payload",b,7,size);}
 public static void main(String[] args)throws Throwable {
  byte[] bytes=Files.readAllBytes(Path.of(args[0])),padded=new byte[bytes.length+14];
  System.arraycopy(bytes,0,padded,7,bytes.length);
  for(int i=0;i<4;i++){Class<?> c=new LoadProbe().load(padded,bytes.length);
   if((int)c.getMethod("value").invoke(c.getConstructor().newInstance())!=47)throw new AssertionError();}
  MethodHandles.lookup().defineHiddenClass(bytes,false);
  System.out.println("application-completed");
 }
}''')
            observer=Path(os.environ.get('B06_BULK_OBSERVER_SOURCE',str(Path(__file__).resolve().parents[1]/'factory/idempiere/b06-observer/PostingObserver.java')))
            subprocess.run([str(javac),'--add-modules','jdk.jdi','-d',str(p),str(observer),str(p/'Payload.java'),str(p/'LoadProbe.java')],check=True,capture_output=True,timeout=45)
            raw=(p/'fixture/Payload.class').read_bytes(); expected=hashlib.sha256(raw).hexdigest()
            target=subprocess.Popen([str(java),'-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:0','-cp',str(p),'fixture.LoadProbe',str(p/'fixture/Payload.class')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                port=target.stdout.readline().strip().rsplit(':',1)[-1].strip(); self.assertTrue(port.isdigit())
                start=time.monotonic()
                observed=subprocess.run([str(java),'--add-modules','jdk.jdi','-cp',str(p),'lightyear.observer.PostingObserver','127.0.0.1',port,'observer-binding-v2'],input='',capture_output=True,text=True,timeout=120)
                elapsed=time.monotonic()-start
                self.assertEqual(observed.returncode,0,observed.stderr)
                stdout,stderr=target.communicate(timeout=15); self.assertEqual(target.returncode,0,stderr)
                self.assertIn('application-completed',stdout)
                events=[json.loads(line) for line in observed.stdout.splitlines()]
                entries=[e['record'] for e in events if e['kind']=='generation-entry']
                matches=[r for r in entries if r.get('definition_input_sha256')==expected]
                self.assertEqual(len(matches),5)  # four offset definitions plus one hidden class
                for r in matches:self.assertEqual(bytes.fromhex(r['definition_input_hex']),raw)
                self.assertEqual(events[-1]['kind'],'vm-death'); self.assertEqual(events[-1]['generation_pending'],0)
                counts={kind:sum(e['kind']==kind for e in events) for kind in ('generation-entry','generation-return','generation-unwind')}
                self.assertEqual(counts['generation-entry'],counts['generation-return']+counts['generation-unwind'])
                record=dict(schema='b06-jdi-bulk-read-host-rehearsal/1',elapsed_seconds=round(elapsed,3),event_count=len(events),
                    byte_exact_definitions=len(matches),class_bytes=len(raw),definition_sha256=expected,counts=counts,
                    observer_sha256=hashlib.sha256(observer.read_bytes()).hexdigest(),native_admission=False,model_calls=0)
                if os.environ.get('B06_BULK_RECORD'):Path(os.environ['B06_BULK_RECORD']).write_text(json.dumps(record,indent=2))
            finally:
                if target.poll() is None:target.terminate();target.wait(timeout=10)
