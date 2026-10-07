import com.sun.jdi.*;
import com.sun.jdi.connect.*;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Host-only diagnosis: JDI reads are the evidence; target-written dumps are not. */
public final class HostPoolObserver {
    static final String ENGINE = "org.junit.platform.engine.support.hierarchical.HierarchicalTestEngine";
    static String hash(byte[] data) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data)); }
    static String json(Object v) {
        if (v == null) return "null";
        if (v instanceof Number || v instanceof Boolean) return v.toString();
        if (v instanceof Map<?,?> m) { List<String> s=new ArrayList<>(); for(var e:m.entrySet()) s.add(json(e.getKey().toString())+":"+json(e.getValue()));return "{"+String.join(",",s)+"}"; }
        if (v instanceof Iterable<?> a) { List<String> s=new ArrayList<>();for(var x:a)s.add(json(x));return "["+String.join(",",s)+"]"; }
        return "\""+v.toString().replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r")+"\"";
    }
    static Map<String,Object> read(ReferenceType type) throws Exception {
        Map<String,Object> r=new LinkedHashMap<>();byte[] cp=type.constantPool();
        r.put("class",type.name());r.put("signature",type.signature());r.put("loader",type.classLoader()==null?"bootstrap":Long.toString(type.classLoader().uniqueID()));
        r.put("module",type.module().name());r.put("class_object_id",type.classObject().uniqueID());r.put("modifiers",type.modifiers());
        r.put("constant_pool_count",type.constantPoolCount());r.put("constant_pool_hex",HexFormat.of().formatHex(cp));r.put("constant_pool_sha256",hash(cp));
        List<Object> methods=new ArrayList<>();
        for(Method m:type.methods()) { Map<String,Object> x=new LinkedHashMap<>();x.put("name",m.name());x.put("signature",m.signature());x.put("modifiers",m.modifiers());
            if(!m.isNative()&&!m.isAbstract()){byte[] b=m.bytecodes();x.put("bytecode_hex",HexFormat.of().formatHex(b));x.put("sha256",hash(b));}methods.add(x); }
        r.put("methods",methods);return r;
    }
    public static void main(String[] args) throws Exception {
        // args: exact classpath, output directory, dump property mode (none/new/old)
        Path out=Path.of(args[1]);Files.createDirectory(out);
        LaunchingConnector connector=Bootstrap.virtualMachineManager().defaultConnector();var a=connector.defaultArguments();
        a.get("main").setValue("HostPoolTarget");
        String options="-cp \""+args[0]+"\"";
        if(args[2].equals("new")) options+=" -Djdk.invoke.LambdaMetafactory.dumpProxyClassFiles=true";
        if(args[2].equals("old")) options+=" -Djdk.internal.lambda.dumpProxyClasses="+out.resolve("old-dumps");
        a.get("options").setValue(options);a.get("suspend").setValue("true");
        VirtualMachine vm=connector.launch(a);Process child=vm.process();
        Thread stdout=Thread.ofPlatform().start(()->{try{Files.copy(child.getInputStream(),out.resolve("target.stdout"));}catch(Exception e){throw new RuntimeException(e);}});
        Thread stderr=Thread.ofPlatform().start(()->{try{Files.copy(child.getErrorStream(),out.resolve("target.stderr"));}catch(Exception e){throw new RuntimeException(e);}});
        List<Object> samples=new ArrayList<>();Set<String> hidden=new HashSet<>();int snapshots=0;boolean death=false;
        long start=System.nanoTime();
        try {
            for(String name:List.of(ENGINE,"HostPoolTarget")){ClassPrepareRequest q=vm.eventRequestManager().createClassPrepareRequest();q.addClassFilter(name);q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();}
            vm.resume();
            while(!death && (System.nanoTime()-start)<TimeUnit.SECONDS.toNanos(90)) {
                EventSet set=vm.eventQueue().remove(1000);if(set==null)continue;
                for(Event event:set) {
                    if(event instanceof ClassPrepareEvent e) {
                        if(e.referenceType().name().equals(ENGINE)) samples.add(Map.of("stage","class-prepared","definition",read(e.referenceType())));
                        else {BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(e.referenceType().methodsByName("checkpoint").get(0).location());q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();}
                    } else if(event instanceof BreakpointEvent e) {
                        int phase=((IntegerValue)e.thread().frame(0).getArgumentValues().get(0)).value();snapshots++;
                        List<ReferenceType> types=vm.classesByName(ENGINE);if(types.size()!=1)throw new IllegalStateException("ambiguous engine");
                        samples.add(Map.of("stage","checkpoint-"+phase,"definition",read(types.get(0))));
                        for(ReferenceType type:vm.allClasses())if(type.name().contains("/")&&hidden.add(type.name())) {
                            try {samples.add(Map.of("stage","hidden-at-"+phase,"definition",read(type)));}
                            catch(Exception failure){samples.add(Map.of("stage","hidden-read-failed","class",type.name(),"error",failure.getClass().getName()));}
                        }
                    } else if(event instanceof VMDeathEvent) death=true;
                }
                if(!death)set.resume();
            }
            if(!death||snapshots!=5)throw new IllegalStateException("incomplete offline lifecycle");
            if(!child.waitFor(10,TimeUnit.SECONDS)||child.exitValue()!=0)throw new IllegalStateException("target failed");
        } finally {
            if(child.isAlive()) {child.destroyForcibly();child.waitFor();}
            stdout.join(10000);stderr.join(10000);
            Map<String,Object> report=new LinkedHashMap<>();report.put("samples",samples);report.put("complete",death&&snapshots==5);report.put("checkpoint_count",snapshots);
            report.put("target_options",options);report.put("elapsed_seconds",(System.nanoTime()-start)/1e9);report.put("model_calls",0);report.put("docker_commands",0);
            Files.writeString(out.resolve("observations.json"),json(report));
        }
        System.out.println("Host JDI probe complete: "+snapshots+" checkpoints; "+hidden.size()+" hidden definitions");
    }
}
