import com.sun.jdi.*;
import com.sun.jdi.connect.AttachingConnector;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;
import java.io.*;
import java.lang.management.ManagementFactory;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Host-only measurement/fault-injection driver for the unchanged production observer.
 * Delegates capture, matching, serialization and auditing to production methods.
 * Suppression drops only an outermost generation's ARETURN breakpoint, before
 * an exit request exists. Stale pending entries remain; they are never repaired.
 * The harness is NOT a native driver or a provenance/admission result.
 */
public final class MemoryObserverHarness {
    static final Class<?> OBS;
    static { try { OBS=Class.forName("lightyear.observer.PostingObserver"); }
             catch(Exception e) { throw new ExceptionInInitializerError(e); } }
    static Object observer, generation;
    static Path directory;
    static String jcmd;
    static long events, peak, generations, eligibleReturns, suppressed;
    static int suppressEvery;
    static final Map<Long,Integer> abandoned=new HashMap<>();
    static final Set<Long> stackClasses=new HashSet<>();
    static PrintWriter samples, injections;
    static byte[] emergency=new byte[1024*1024];

    static Object field(Object object,String name) throws Exception {
        var f=object.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(object);
    }
    static void set(Object object,String name,Object value) throws Exception {
        var f=object.getClass().getDeclaredField(name);f.setAccessible(true);f.set(object,value);
    }
    static Object call(String name,Class<?>[] types,Object... values) throws Throwable {
        var m=OBS.getDeclaredMethod(name,types);m.setAccessible(true);
        try { return m.invoke(observer,values); }
        catch(InvocationTargetException e) { throw e.getCause(); }
    }
    static void audit(String action,Map<String,Object> detail) throws Throwable {
        call("audit",new Class<?>[]{String.class,Map.class},action,detail);
    }
    static Map<?,?> pending() throws Exception { return (Map<?,?>)field(generation,"pending"); }
    static int pendingCount() throws Exception {
        int total=0;for(Object q:pending().values())total+=((Collection<?>)q).size();return total;
    }
    static void sample(boolean histogram) throws Exception {
        System.gc();
        var usage=ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        samples.printf(Locale.ROOT,"%d,%d,%d,%d,%d,%d,%d,%d,%d%n",events,generations,
            usage.getUsed(),usage.getMax(),pendingCount(),((Map<?,?>)field(generation,"completed")).size(),
            ((Map<?,?>)field(generation,"definitions")).size(),stackClasses.size(),suppressed);
        samples.flush();
        if(histogram && usage.getUsed()>peak) {
            peak=usage.getUsed();
            Path temp=directory.resolve("histogram-next.txt");
            Process process=new ProcessBuilder(jcmd,Long.toString(ProcessHandle.current().pid()),"GC.class_histogram")
                .redirectOutput(temp.toFile()).redirectError(directory.resolve("histogram.stderr").toFile()).start();
            if(!process.waitFor(30,java.util.concurrent.TimeUnit.SECONDS)) {
                process.destroyForcibly();throw new IOException("histogram timed out");
            }
            if(process.exitValue()!=0)throw new IOException("histogram failed");
            Files.move(temp,directory.resolve("peak-histogram.txt"),StandardCopyOption.REPLACE_EXISTING);
            Files.writeString(directory.resolve("peak-sample.txt"),events+","+peak+"\n");
        }
    }
    static boolean suppress(BreakpointEvent event) throws Exception {
        if(!Boolean.TRUE.equals(event.request().getProperty("generation-return")))return false;
        long thread=event.thread().uniqueID();
        Object q=pending().get(thread);
        if(!(q instanceof Deque<?> calls) || calls.size()!=abandoned.getOrDefault(thread,0)+1)return false;
        if(++eligibleReturns%suppressEvery!=0)return false;
        Map<?,?> entry=(Map<?,?>)calls.peek();
        // Only drop a real selected top-level return; no production state is changed.
        String method=event.location().declaringType().name()+"."+event.location().method().name()+event.location().method().signature();
        if(!method.equals(entry.get("entry_method")) || !entry.get("entry_depth").equals(event.thread().frameCount()))
            throw new IllegalStateException("fault injection does not match live entry");
        abandoned.merge(thread,1,Integer::sum);suppressed++;
        injections.printf("%d,%d,%s,%d%n",events,thread,entry.get("generation_id"),event.thread().frameCount());
        injections.flush();return true;
    }
    public static void main(String[] args) throws Throwable {
        directory=Path.of(args[2]);jcmd=args[3];suppressEvery=Integer.parseInt(args[4]);
        if(suppressEvery<100 || suppressEvery>1000)throw new IllegalArgumentException("suppression fraction outside 0.1–1 percent");
        var constructor=OBS.getDeclaredConstructor();constructor.setAccessible(true);observer=constructor.newInstance();
        generation=field(observer,"generation");set(observer,"bindingV2",true);set(generation,"v2",true);
        set(observer,"diagnosticUnmatchedReturn",true); // Same narrow policy as the failed r3 baseline.
        samples=new PrintWriter(Files.newBufferedWriter(directory.resolve("heap.csv"),StandardCharsets.UTF_8));
        samples.println("events,generation_calls,heap_used_after_gc,heap_max,pending,completed,definitions,distinct_stack_classes,suppressed_returns");
        injections=new PrintWriter(Files.newBufferedWriter(directory.resolve("suppressed-returns.csv"),StandardCharsets.UTF_8));
        injections.println("events,thread,generation_id,depth");
        PrintStream output=System.out;
        System.setOut(new PrintStream(output,true,StandardCharsets.UTF_8) {
            @Override public void println(String line) {
                super.println(line);events++;
                if(events%1000==0)try { sample(true); }catch(Exception e){throw new RuntimeException(e);}
            }
        });
        AttachingConnector connector=Bootstrap.virtualMachineManager().attachingConnectors().stream()
            .filter(c->c.name().equals("com.sun.jdi.SocketAttach")).findFirst().orElseThrow();
        var options=connector.defaultArguments();options.get("hostname").setValue(args[0]);options.get("port").setValue(args[1]);
        VirtualMachine vm=connector.attach(options);set(observer,"vm",vm);
        if(!vm.canGetBytecodes() || !vm.canGetConstantPool() || !vm.canGetMethodReturnValues())throw new IllegalStateException("JDI capability missing");
        Set<String> types=new HashSet<>();
        var tf=OBS.getDeclaredField("TYPES");tf.setAccessible(true);
        for(Object type:(Set<?>)tf.get(null))types.add(type.toString());
        types.addAll(List.of("java.lang.invoke.InnerClassLambdaMetafactory","java.lang.invoke.InvokerBytecodeGenerator",
            "java.lang.invoke.MethodHandles$Lookup$ClassDefiner","java.lang.ClassLoader"));
        for(String type:types){var request=vm.eventRequestManager().createClassPrepareRequest();request.addClassFilter(type);request.setSuspendPolicy(EventRequest.SUSPEND_ALL);request.enable();}
        for(ReferenceType type:vm.allClasses())call("configure",new Class<?>[]{ReferenceType.class},type);
        var exceptions=vm.eventRequestManager().createExceptionRequest(null,true,true);exceptions.setSuspendPolicy(EventRequest.SUSPEND_ALL);exceptions.enable();
        call("emit",new Class<?>[]{Map.class,boolean.class},new LinkedHashMap<>(Map.of("kind","host-memory-probe-ready","native_admission",false)),false);
        boolean running=true;long sets=0;
        try {
            sample(true);
            while(running) {
                EventSet batch=vm.eventQueue().remove(1000);if(batch==null)continue;
                set(observer,"auditSet",++sets);set(observer,"auditPosition",-1);
                audit("event-set-open",Map.of("size",batch.size(),"suspend_policy",batch.suspendPolicy()));
                int position=0;
                for(Event event:batch) {
                    set(observer,"auditPosition",position++);
                    call("auditEvent",new Class<?>[]{Event.class},event);
                    if(event instanceof ClassPrepareEvent e)call("configure",new Class<?>[]{ReferenceType.class},e.referenceType());
                    else if(event instanceof BreakpointEvent e) {
                        if(!suppress(e)) {
                            long before=((Number)field(generation,"generationSequence")).longValue();
                            call("entry",new Class<?>[]{BreakpointEvent.class},e);
                            long after=((Number)field(generation,"generationSequence")).longValue();
                            generations+=after-before;
                            if(after>before)for(StackFrame frame:e.thread().frames())stackClasses.add(frame.location().declaringType().classObject().uniqueID());
                        }
                    } else if(event instanceof MethodExitEvent e)call("exit",new Class<?>[]{MethodExitEvent.class},e);
                    else if(event instanceof ExceptionEvent e)call("failure",new Class<?>[]{ExceptionEvent.class},e);
                    else if(event instanceof VMDeathEvent || event instanceof VMDisconnectEvent)running=false;
                    call("auditState",new Class<?>[]{Event.class},event);
                }
                if(running){audit("resume-requested",Map.of("scope","event-set"));batch.resume();audit("resume-completed",Map.of("scope","event-set"));}
            }
            sample(true);
            // Deliberately suppressed returns remain incomplete, never a native pass.
            Files.writeString(directory.resolve("completed.txt"),"host-only workload ended; open_entries="+pendingCount()+"\n");
        } catch(OutOfMemoryError failure) {
            emergency=null;System.gc();
            Files.writeString(directory.resolve("oom.txt"),failure.toString()+"\nevents="+events+"\ngeneration_calls="+generations+"\n");
            throw failure;
        } finally { samples.close();injections.close(); }
    }
}
