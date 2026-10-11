import com.sun.jdi.*;
import com.sun.jdi.connect.*;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;
import java.nio.file.*;
import java.util.*;

/** Bounded entry-only counter, deliberately not the provenance observer. */
public final class AlternativesCounter {
    static final Map<String,Set<String>> WATCH=Map.of(
        "java.lang.invoke.MethodHandles$Lookup$ClassDefiner",Set.of("defineClass"),
        "java.lang.invoke.InnerClassLambdaMetafactory",Set.of("spinInnerClass"),
        "java.lang.invoke.InvokerBytecodeGenerator",Set.of("generateCustomizedCodeBytes","generateLambdaFormInterpreterEntryPointBytes","generateNamedFunctionInvokerImpl"));
    static final Set<String> installed=new HashSet<>();
    static void install(VirtualMachine vm, ReferenceType type) {
        for(Method method:type.methods()) if(WATCH.getOrDefault(type.name(),Set.of()).contains(method.name())) {
            String key=type.name()+method.name()+method.signature();
            if(installed.add(key)) {
                BreakpointRequest request=vm.eventRequestManager().createBreakpointRequest(method.location());
                request.setSuspendPolicy(EventRequest.SUSPEND_ALL);request.enable();
            }
        }
    }
    public static void main(String[] args) throws Exception {
        var connector=Bootstrap.virtualMachineManager().defaultConnector();var options=connector.defaultArguments();
        options.get("home").setValue(args[0]); options.get("options").setValue(args[1]);
        options.get("main").setValue(args[2]); options.get("suspend").setValue("true");
        VirtualMachine vm=connector.launch(options); Process child=vm.process();
        Thread out=Thread.ofPlatform().start(()->{try { child.getInputStream().transferTo(System.err); }catch(Exception e){throw new RuntimeException(e);}});
        Thread err=Thread.ofPlatform().start(()->{try { child.getErrorStream().transferTo(System.err); }catch(Exception e){throw new RuntimeException(e);}});
        for(String name:WATCH.keySet()) {
            ClassPrepareRequest request=vm.eventRequestManager().createClassPrepareRequest();request.addClassFilter(name);
            request.setSuspendPolicy(EventRequest.SUSPEND_ALL);request.enable();
            for(ReferenceType type:vm.classesByName(name)) install(vm,type);
        }
        Map<String,Integer> counts=new TreeMap<>(); boolean complete=false; long deadline=System.nanoTime()+120_000_000_000L;
        try {
            while(!complete && System.nanoTime()<deadline) {
                EventSet set=vm.eventQueue().remove(1000); if(set==null)continue;
                for(Event event:set) {
                    if(event instanceof ClassPrepareEvent e)install(vm,e.referenceType());
                    if(event instanceof BreakpointEvent e)counts.merge(e.location().declaringType().name()+"."+e.location().method().name(),1,Integer::sum);
                    if(event instanceof VMDeathEvent)complete=true;
                }
                set.resume();
            }
        } catch(VMDisconnectedException e) { if(!complete)throw e; }
        if(!complete) { vm.dispose();child.destroyForcibly();throw new IllegalStateException("counter-timeout"); }
        int code=child.waitFor();out.join();err.join();
        System.out.print("{\"complete\":"+(complete && code==0)+",\"exit_code\":"+code+",\"counts\":{");
        boolean first=true;for(var item:counts.entrySet()) {if(!first)System.out.print(",");first=false;System.out.print("\""+item.getKey()+"\":"+item.getValue());}
        System.out.println("}}");
        if(code!=0)System.exit(code);
    }
}
