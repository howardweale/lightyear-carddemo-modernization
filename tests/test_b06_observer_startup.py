"""Host-only regression for the queued VMStart suspension and exact return arms."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('B06_HOST_JDK'), 'host JDK probe explicitly enabled')
class ObserverStartupTests(unittest.TestCase):
    def tools(self):
        java = Path(os.environ['B06_HOST_JDK'])/'bin'/('java.exe' if os.name == 'nt' else 'java')
        return java, java.with_name('javac.exe' if os.name == 'nt' else 'javac')

    def test_queued_start_resume_with_delayed_dispatch_and_concurrent_generation(self):
        java, javac = self.tools()
        root = Path(__file__).resolve().parents[1]
        source = Path(os.environ.get('B06_STARTUP_OBSERVER_SOURCE', str(root/'factory/idempiere/b06-observer/PostingObserver.java')))
        # Hold the collector after setup, before processing the queued VMStart.
        # With the old premature vm.resume(), the target reaches a breakpoint
        # during this hold; processing VMStart then resumes that breakpoint too.
        text = source.read_text()
        self.assertEqual(text.count('boolean running = true;'), 1)
        delayed = text.replace('boolean running = true;', 'Thread.sleep(1000); boolean running = true;')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/'PostingObserver.java').write_text(delayed)
            (p/'ConcurrentProbe.java').write_text('''package fixture;
import java.lang.invoke.*;import java.nio.file.*;import java.util.concurrent.*;
public class ConcurrentProbe {
 public static void target() {}
 public static void main(String[] args)throws Throwable {
  byte[] bytes=Files.readAllBytes(Path.of(args[0]));
  CountDownLatch ready=new CountDownLatch(1);Thread[] threads=new Thread[4];
  for(int n=0;n<threads.length;n++) {
   threads[n]=new Thread(()->{try {
    ready.await();var lookup=MethodHandles.lookup();
    var target=lookup.findStatic(ConcurrentProbe.class,"target",MethodType.methodType(void.class));
    for(int i=0;i<40;i++) {
     var site=LambdaMetafactory.metafactory(lookup,"run",MethodType.methodType(Runnable.class),MethodType.methodType(void.class),target,MethodType.methodType(void.class));
     ((Runnable)site.getTarget().invokeExact()).run();
     lookup.defineHiddenClass(bytes,false);
    }
   }catch(Throwable e){e.printStackTrace();System.exit(2);}},"generation-"+n);
   threads[n].start();
  }
  ready.countDown();for(Thread thread:threads)thread.join();System.out.println("complete");
 }
}
class Hidden {public void run(){}}
''')
            subprocess.run([str(javac),'--add-modules','jdk.jdi','-g','-d',str(p),str(p/'PostingObserver.java'),str(p/'ConcurrentProbe.java')],check=True,capture_output=True,timeout=45)
            target = subprocess.Popen([str(java),'-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:0','-cp',str(p),'fixture.ConcurrentProbe',str(p/'fixture/Hidden.class')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                port = target.stdout.readline().strip().rsplit(':',1)[-1].strip()
                self.assertTrue(port.isdigit())
                observed = subprocess.run([str(java),'--add-modules','jdk.jdi','-cp',str(p),'lightyear.observer.PostingObserver','127.0.0.1',port,'observer-binding-v2'],input='',capture_output=True,text=True,timeout=90)
                if os.environ.get('B06_STARTUP_RECORD'):
                    Path(os.environ['B06_STARTUP_RECORD']).write_text(json.dumps(dict(
                        observer_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                        returncode=observed.returncode,stderr=observed.stderr,
                        event_sha256=hashlib.sha256(observed.stdout.encode()).hexdigest(),
                        event_count=len(observed.stdout.splitlines()),host_only=True,native_admission=False,model_calls=0),indent=2))
                self.assertEqual(observed.returncode,0,observed.stderr)
                stdout, stderr = target.communicate(timeout=10)
                self.assertEqual(target.returncode,0,stderr); self.assertIn('complete',stdout)
                events = [json.loads(line) for line in observed.stdout.splitlines()]
                from tools.ms94_b06_observer_v2 import Replay
                replay = Replay([])
                threads=set(); definitions=0
                for event in events:
                    replay.event(event)
                    if event['kind']=='generation-return':
                        r=event['record']; threads.add(r['thread_id'])
                        if r.get('definition_input_sha256')==hashlib.sha256((p/'fixture/Hidden.class').read_bytes()).hexdigest():
                            definitions+=1
                self.assertGreaterEqual(len(threads),5)  # main plus four generators
                self.assertEqual(definitions,160)
                self.assertFalse(any(replay.pending.values()))
                self.assertEqual(events[-1]['kind'],'vm-death')
                self.assertEqual(events[-1]['generation_pending'],0)
            finally:
                if target.poll() is None: target.terminate()
                target.communicate(timeout=10)

    def test_return_arm_rejects_missing_or_changed_activation(self):
        java, javac = self.tools()
        source = Path(__file__).resolve().parents[1]/'factory/idempiere/b06-observer/PostingObserver.java'
        probe = r'''import com.sun.jdi.*;import com.sun.jdi.event.*;import com.sun.jdi.request.*;
import java.lang.reflect.*;import java.util.*;
public class ArmProbe {
 static int depth=3,created=0;static Object exitRequest;
 static Object proxy(Class<?> c,java.util.function.BiFunction<String,Object[],Object> f) {
  return Proxy.newProxyInstance(ArmProbe.class.getClassLoader(),new Class<?>[]{c},(o,m,a)->{
   if(m.getName().equals("equals"))return o==a[0];if(m.getName().equals("hashCode"))return System.identityHashCode(o);
   if(m.getName().equals("toString"))return c.getSimpleName();return f.apply(m.getName(),a);
  });
 }
 static void refused(java.lang.reflect.Method m,Object g,Object... args)throws Exception {
  try{m.invoke(g,args);throw new AssertionError("bad activation accepted");}
  catch(InvocationTargetException e){if(!(e.getCause() instanceof IllegalStateException))throw e;}
 }
 public static void main(String[] args)throws Exception {
  ReferenceType type=(ReferenceType)proxy(ReferenceType.class,(n,a)->n.equals("name")?"java.lang.invoke.InvokerBytecodeGenerator":null);
  com.sun.jdi.Method method=(com.sun.jdi.Method)proxy(com.sun.jdi.Method.class,(n,a)->switch(n){case "declaringType"->type;case "name"->"generateCustomizedCodeBytes";case "signature"->"()[B";default->null;});
  Location loc=(Location)proxy(Location.class,(n,a)->switch(n){case "method"->method;case "declaringType"->type;case "codeIndex"->36L;default->null;});
  StackFrame frame=(StackFrame)proxy(StackFrame.class,(n,a)->loc);
  ThreadReference thread=(ThreadReference)proxy(ThreadReference.class,(n,a)->switch(n){case "uniqueID"->7L;case "frameCount"->depth;case "frame"->frame;default->null;});
  BreakpointEvent bp=(BreakpointEvent)proxy(BreakpointEvent.class,(n,a)->n.equals("thread")?thread:loc);
  EventRequestManager manager=(EventRequestManager)proxy(EventRequestManager.class,(n,a)->{
   if(n.equals("createMethodExitRequest")){created++;exitRequest=proxy(MethodExitRequest.class,(x,y)->null);return exitRequest;}
   return null;
  });
  VirtualMachine vm=(VirtualMachine)proxy(VirtualMachine.class,(n,a)->manager);
  Class<?> c=Class.forName("lightyear.observer.PostingObserver$Generation");var constructor=c.getDeclaredConstructor();constructor.setAccessible(true);Object g=constructor.newInstance();
  var v=c.getDeclaredField("v2");v.setAccessible(true);v.set(g,true);
  var f=c.getDeclaredField("pending");f.setAccessible(true);Map<Long,Deque<Map<String,Object>>> pending=(Map)f.get(g);
  var arm=c.getDeclaredMethod("atReturn",VirtualMachine.class,BreakpointEvent.class);arm.setAccessible(true);
  var returned=c.getDeclaredMethod("returned",VirtualMachine.class,MethodExitEvent.class);returned.setAccessible(true);
  refused(arm,g,vm,bp);if(created!=0)throw new AssertionError("request created without entry");
  Map<String,Object> entry=new HashMap<>(Map.of("entry_method","java.lang.invoke.InvokerBytecodeGenerator.generateCustomizedCodeBytes()[B","entry_depth",3));
  Deque<Map<String,Object>> stack=new ArrayDeque<>();stack.push(entry);pending.put(7L,stack);
  depth=4;refused(arm,g,vm,bp);depth=3;arm.invoke(g,vm,bp);
  if(created!=1)throw new AssertionError("wrong request count");refused(arm,g,vm,bp);
  MethodExitEvent badRequest=(MethodExitEvent)proxy(MethodExitEvent.class,(n,a)->switch(n){case "thread"->thread;case "method"->method;case "request"->null;default->null;});
  refused(returned,g,vm,badRequest);
  MethodExitEvent exit=(MethodExitEvent)proxy(MethodExitEvent.class,(n,a)->switch(n){case "thread"->thread;case "method"->method;case "request"->exitRequest;default->null;});
  depth=4;refused(returned,g,vm,exit);depth=3;
  stack.pop();stack.push(new HashMap<>(entry));refused(returned,g,vm,exit);
  stack.pop();stack.push(entry);
  MethodExitEvent wrongMethod=(MethodExitEvent)proxy(MethodExitEvent.class,(n,a)->switch(n){case "thread"->thread;case "method"->null;case "request"->exitRequest;default->null;});
  refused(returned,g,vm,wrongMethod);
  if(stack.peek()!=entry || created!=1)throw new AssertionError("failed check consumed evidence");
  System.out.println("missing entry, wrong depth/request/method, replaced activation and duplicate arm refused");
 }
}'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'ArmProbe.java').write_text(probe)
            subprocess.run([str(javac),'--add-modules','jdk.jdi','-d',str(p),str(source),str(p/'ArmProbe.java')],check=True,capture_output=True,timeout=45)
            observed=subprocess.run([str(java),'--add-modules','jdk.jdi','-cp',str(p),'ArmProbe'],capture_output=True,text=True,timeout=20)
            self.assertEqual(observed.returncode,0,observed.stderr)
            self.assertIn('duplicate arm refused',observed.stdout)
