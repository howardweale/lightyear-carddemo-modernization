"""Host-only JDI event tests. No Docker, application image or native pair."""
import json,os,subprocess,tempfile,time,unittest
from pathlib import Path

@unittest.skipUnless(os.environ.get('B06_HOST_JDK'),'host JDK probe explicitly enabled')
class HostObserverTests(unittest.TestCase):
 def test_real_generation_events_direct_hidden_and_failed_definition_unwind(self):
  java=Path(os.environ['B06_HOST_JDK'])/'bin'/('java.exe' if os.name=='nt' else 'java')
  javac=java.with_name('javac.exe' if os.name=='nt' else 'javac')
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);src=p/'fixture';src.mkdir()
   (src/'Probe.java').write_text("""package fixture;
import java.lang.invoke.*;import java.nio.file.*;
public class Probe {
 public static void run() {}
 public static void main(String[] args)throws Throwable {
  long start=System.nanoTime();var lookup=MethodHandles.lookup();
  for(int i=0;i<300;i++) {
   var site=LambdaMetafactory.metafactory(lookup,"run",MethodType.methodType(Runnable.class),MethodType.methodType(void.class),lookup.findStatic(Probe.class,"run",MethodType.methodType(void.class)),MethodType.methodType(void.class));
   ((Runnable)site.getTarget().invokeExact()).run();
  }
  try {lookup.defineHiddenClass(Files.readAllBytes(Path.of(args[1])),false);}catch(NoClassDefFoundError expected){}
  lookup.defineHiddenClass(Files.readAllBytes(Path.of(args[0])),false);
  System.out.println("elapsed_ns="+(System.nanoTime()-start));
 }
}
class Hidden { public void run() {} }
class MissingHidden extends MissingBase {}
class MissingBase {}
""")
   subprocess.run([str(javac),'--add-modules','jdk.jdi','-d',str(p),str(root/'factory/idempiere/b06-observer/PostingObserver.java'),str(src/'Probe.java')],check=True,capture_output=True,timeout=45)
   (p/'fixture/MissingBase.class').unlink()
   plain=subprocess.run([str(java),'-cp',str(p),'fixture.Probe',str(p/'fixture/Hidden.class'),str(p/'fixture/MissingHidden.class')],check=True,capture_output=True,text=True,timeout=30)
   target=subprocess.Popen([str(java),'-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:0','-cp',str(p),'fixture.Probe',str(p/'fixture/Hidden.class'),str(p/'fixture/MissingHidden.class')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   try:
    line=target.stdout.readline();port=line.strip().rsplit(':',1)[-1].strip();self.assertTrue(port.isdigit(),line)
    observed=subprocess.run([str(java),'--add-modules','jdk.jdi','-cp',str(p),'lightyear.observer.PostingObserver','127.0.0.1',port],input='',capture_output=True,text=True,timeout=90)
    self.assertEqual(observed.returncode,0,observed.stderr)
    output,error=target.communicate(timeout=15);self.assertEqual(target.returncode,0,error)
    events=[json.loads(line) for line in observed.stdout.splitlines()]
    entries=[e for e in events if e['kind']=='generation-entry'];returns=[e for e in events if e['kind']=='generation-return'];unwinds=[e for e in events if e['kind']=='generation-unwind']
    self.assertEqual(len(entries),len(returns)+len(unwinds));self.assertTrue(unwinds)
    self.assertGreaterEqual(sum('lambda_factory' in e['record'] for e in returns),300)
    self.assertTrue(any('lambda_factory' not in e['record'] for e in returns))
    self.assertEqual(events[-1]['kind'],'vm-death');self.assertEqual(events[-1]['generation_pending'],0)
    # Replay the actual external observer stream, including its unwind. This
    # tests collection only; it cannot substitute for native entry/admission.
    import hashlib
    from lightyear_calibration.contracts import seal,canonical
    from tools.ms94_b06_forwarding_stub import receipt_records,POLICY
    from tools.ms94_b06_posting_replay import replay_stream
    records=[];previous=None
    for event in events:
     record=seal(dict(previous_sha256=previous,event=event,readback_sha256=None));records.append(record);previous=record['content_sha256']
    raw=b''.join(canonical(row)+b'\n' for row in records);(p/'events.jsonl').write_bytes(raw)
    receipt=dict(event_file_sha256=hashlib.sha256(raw).hexdigest(),event_count=len(records),last_event_sha256=previous,frame_records=receipt_records(records))
    replayed=replay_stream(p,receipt,{},'postgresql',dict(policy=POLICY,adjacent_target='younger'),{})
    self.assertTrue(replayed['collection_complete']);self.assertEqual(replayed['event_count'],len(events))
    result=dict(schema='b06-host-observer-performance/1',host_only=True,native_admission=False,
        baseline_stdout=plain.stdout,observed_stdout=output,event_count=len(events),event_bytes=len(observed.stdout.encode()),
        generation_entries=len(entries),generation_returns=len(returns),generation_unwinds=len(unwinds),model_calls=0)
    if os.environ.get('B06_HOST_RECORD'):Path(os.environ['B06_HOST_RECORD']).write_text(json.dumps(result,indent=2))
   finally:
    if target.poll() is None:target.terminate();target.wait(timeout=10)

 def test_real_agent_records_installed_bundle_without_waiting_for_resolution(self):
  java=Path(os.environ['B06_HOST_JDK'])/'bin'/('java.exe' if os.name=='nt' else 'java');javac=java.with_name('javac.exe' if os.name=='nt' else 'javac')
  root=Path(__file__).resolve().parents[1]
  sources={
   'org/osgi/framework/Bundle.java':'package org.osgi.framework; public interface Bundle {long getBundleId(); int getState(); String getLocation(); String getSymbolicName(); String getVersion(); java.util.Dictionary<String,String> getHeaders(String locale); BundleContext getBundleContext();}',
   'org/osgi/framework/BundleContext.java':'package org.osgi.framework; public interface BundleContext {Bundle[] getBundles();}',
   'org/osgi/framework/FrameworkUtil.java':"""package org.osgi.framework;
public class FrameworkUtil {
 public static class B implements Bundle {int id;B(int n){id=n;}public long getBundleId(){return id;}public int getState(){return id==0?32:2;}public String getLocation(){return id==0?"System Bundle":"initial@reference:file:public-fixture-bundle/";}public String getSymbolicName(){return "fixture.bundle"+id;}public String getVersion(){return "1.0.0";}public java.util.Dictionary<String,String> getHeaders(String locale){return new java.util.Hashtable<>();}public BundleContext getBundleContext(){return new C();}}
 public static class C implements BundleContext {public Bundle[] getBundles(){return new Bundle[]{new B(0),new B(1)};}}
 public static Bundle getBundle(Class<?> c){return new B(0);}
}""",
   'org/junit/platform/engine/support/hierarchical/NodeTestTask.java':'package org.junit.platform.engine.support.hierarchical; public class NodeTestTask {}',
   'org/junit/platform/launcher/core/ExecutionListenerAdapter.java':'package org.junit.platform.launcher.core; public class ExecutionListenerAdapter {}',
   'ProbeAgent.java':"""import java.lang.instrument.*;import java.lang.reflect.*;import java.nio.file.*;
public class ProbeAgent {public static void main(String[] args)throws Exception {
 Class<?>[] loaded={org.osgi.framework.FrameworkUtil.class,org.junit.platform.engine.support.hierarchical.NodeTestTask.class,org.junit.platform.launcher.core.ExecutionListenerAdapter.class};
 Instrumentation i=(Instrumentation)Proxy.newProxyInstance(ProbeAgent.class.getClassLoader(),new Class<?>[]{Instrumentation.class},(p,m,a)->{if(m.getName().equals("getAllLoadedClasses"))return loaded;if(m.getName().equals("addTransformer") && a.length==1 && a[0] instanceof ClassFileTransformer)return null;throw new UnsupportedOperationException();});
 System.setProperty("osgi.install.area",Path.of(".").toAbsolutePath().toUri().toString());
 RuntimeClosureAgent.premain(args[0],i);long end=System.nanoTime()+5_000_000_000L;while(!Files.exists(Path.of(args[0]))&&System.nanoTime()<end)Thread.sleep(10);
 if(!Files.exists(Path.of(args[0])))throw new AssertionError("agent did not capture INSTALLED bundle");
 }}"""}
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);files=[]
   for name,code in sources.items():
    f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(code);files.append(str(f))
   subprocess.run([str(javac),'-d',str(p),str(root/'tools/b06_image_artifacts/RuntimeClosureAgent.java'),*files],check=True,capture_output=True,timeout=45)
   observed=subprocess.run([str(java),'-cp',str(p),'ProbeAgent',str(p/'observation.json')],capture_output=True,timeout=15)
   error_path=p/'closure-error.json'
   if os.name=='nt' and observed.returncode and error_path.exists():
    failure=json.loads(error_path.read_text())
    if failure['stage']=='process-metadata' and failure['exception_class']=='java.util.NoSuchElementException':
     self.skipTest('Host JDK omits ProcessHandle.Info command/arguments; Linux closure metadata not verified')
   self.assertEqual(observed.returncode,0,observed.stderr.decode(errors='replace'))
   row=json.loads((p/'observation.json').read_bytes());self.assertEqual([b['state'] for b in row['bundles']],[32,2])
   self.assertEqual(row['bundles'][1]['location'],'initial@reference:file:public-fixture-bundle/')
