import com.sun.jdi.*;
import com.sun.jdi.connect.*;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** External, read-only JDI experiment. No invokeMethod, agent, database or Docker. */
public final class HostGenerationObserver {
    static final String DEFINER="java.lang.invoke.MethodHandles$Lookup$ClassDefiner";
    static final String FACTORY="java.lang.invoke.InnerClassLambdaMetafactory";
    static final String INVOKER="java.lang.invoke.InvokerBytecodeGenerator";
    static final String LOADER="java.lang.ClassLoader";
    static final String DEFINE="(Ljava/lang/String;[BIILjava/security/ProtectionDomain;)Ljava/lang/Class;";
    static final Set<String> EMITTERS=Set.of("generateCustomizedCodeBytes","generateLambdaFormInterpreterEntryPointBytes","generateNamedFunctionInvokerImpl");
    static final Map<String,Object> definitions=new LinkedHashMap<>();
    static Object graph(Value seed) throws Exception {
        Map<String,Object> nodes=new LinkedHashMap<>();Deque<ObjectReference> queue=new ArrayDeque<>();
        if(!(seed instanceof ObjectReference initial))return value(seed,0);
        queue.add(initial);
        while(!queue.isEmpty()){
            ObjectReference o=queue.remove();String id=Long.toString(o.uniqueID());if(nodes.containsKey(id))continue;
            if(nodes.size()>=4096)throw new IllegalStateException("method-handle graph bound exceeded");
            Map<String,Object> node=new LinkedHashMap<>();node.put("class",o.referenceType().name());nodes.put(id,node);
            if(o instanceof ClassObjectReference || o instanceof StringReference){node.put("value",value(o,0));continue;}
            Map<String,Value> selected=new LinkedHashMap<>();
            if(o instanceof ArrayReference array){
                if(array.length()>4096)throw new IllegalStateException("method-handle array bound exceeded");
                for(int i=0;i<array.length();i++)selected.put(Integer.toString(i),array.getValue(i));
            }else{
                boolean handle=false;
                if(o.referenceType() instanceof ClassType ct)for(ClassType t=ct;t!=null;t=t.superclass())if(t.name().equals("java.lang.invoke.MethodHandle"))handle=true;
                Set<String> wanted=switch(o.referenceType().name()){
                    case "java.lang.invoke.LambdaForm" -> Set.of("arity","result","names","customized","vmentry","kind");
                    case "java.lang.invoke.LambdaForm$Name" -> Set.of("type","index","function","constraint","arguments");
                    case "java.lang.invoke.LambdaForm$NamedFunction" -> Set.of("member","resolvedHandle","type");
                    case "java.lang.invoke.MemberName" -> Set.of("clazz","name","type","flags","method","resolution");
                    case "java.lang.invoke.MethodType" -> Set.of("rtype","ptypes");
                    case "java.lang.invoke.ResolvedMethodName" -> Set.of("vmtarget","vmholder");
                    case "java.lang.Integer","java.lang.Long","java.lang.Short","java.lang.Byte","java.lang.Character","java.lang.Boolean","java.lang.Float","java.lang.Double" -> Set.of("value");
                    case "java.lang.invoke.LambdaForm$BasicType","java.lang.invoke.LambdaForm$Kind" -> Set.of("name","ordinal");
                    default -> Set.of();
                };
                for(Field f:o.referenceType().allFields()) {
                    boolean handleField=handle && (Set.of("type","form","member","initMethod","instanceClass").contains(f.name()) || f.name().startsWith("arg"));
                    if(!f.isStatic() && (wanted.contains(f.name()) || handleField))
                        selected.put(f.declaringType().name()+"."+f.name(),o.getValue(f));
                }
                if(selected.isEmpty())node.put("opaque",true);
            }
            Map<String,Object> fields=new LinkedHashMap<>();
            for(var entry:selected.entrySet()){
                Value v=entry.getValue();
                if(v instanceof ObjectReference ref){queue.add(ref);fields.put(entry.getKey(),Map.of("ref",Long.toString(ref.uniqueID())));}
                else fields.put(entry.getKey(),value(v,0));
            }node.put("fields",fields);
        }
        return Map.of("root",Long.toString(initial.uniqueID()),"nodes",nodes);
    }
    static Object value(Value v, int depth) throws Exception {
        if(v==null)return null;
        if(v instanceof StringReference s)return s.value();
        if(v instanceof ClassObjectReference c){ReferenceType t=c.reflectedType();remember(t);return Map.of("class_object_id",c.uniqueID(),"class",t.name(),"loader",loader(t),"signature",t.signature());}
        if(v instanceof PrimitiveValue)return v.toString();
        if(v instanceof ArrayReference a){
            if(a.length()>65536)throw new IllegalStateException("array capture bound exceeded");
            List<Object> items=new ArrayList<>();for(Value x:a.getValues())items.add(value(x,depth-1));return items;
        }
        if(v instanceof ObjectReference o){
            Map<String,Object> r=new LinkedHashMap<>();r.put("object_id",o.uniqueID());r.put("class",o.referenceType().name());
            if(depth>0){Map<String,Object> fields=new LinkedHashMap<>();for(Field f:o.referenceType().allFields())if(!f.isStatic())fields.put(f.declaringType().name()+"."+f.name(),value(o.getValue(f),depth-1));r.put("fields",fields);}
            return r;
        }
        throw new IllegalStateException("unhandled JDI value");
    }
    static String loader(ReferenceType t){return t.classLoader()==null?"bootstrap":Long.toString(t.classLoader().uniqueID());}
    static void remember(ReferenceType t) throws Exception {
        String id=Long.toString(t.classObject().uniqueID());
        Object prior=definitions.get(id);
        if(prior==null || (prior instanceof Map<?,?> p && Boolean.FALSE.equals(p.get("prepared")) && t.isPrepared())){
            // Insert first: metadata can recursively refer to the same class.
            definitions.put(id,Map.of("class",t.name(),"class_object_id",t.classObject().uniqueID(),"prepared",t.isPrepared(),"signature",t.signature(),"loader",loader(t)));
            if(!t.isPrepared() || t instanceof ArrayType)return;
            Map<String,Object> d=HostPoolObserver.read(t);
            List<Object> fields=new ArrayList<>();for(Field f:t.fields())fields.add(Map.of("name",f.name(),"signature",f.signature(),"modifiers",f.modifiers()));d.put("fields",fields);
            definitions.put(id,d);
        }
    }
    static List<Object> stack(ThreadReference thread) throws Exception {
        List<Object> frames=new ArrayList<>();for(StackFrame f:thread.frames()){
            Location l=f.location();ReferenceType t=l.declaringType();remember(t);
            frames.add(Map.of("class",t.name(),"class_object_id",t.classObject().uniqueID(),"loader",loader(t),"method",l.method().name(),"signature",l.method().signature(),"code_index",l.codeIndex()));
        }return frames;
    }
    static Map<String,Object> selected(ObjectReference o, List<String> names, int depth) throws Exception {
        Map<String,Object> fields=new LinkedHashMap<>();
        for(String name:names){Field f=o.referenceType().fieldByName(name);if(f==null)throw new IllegalStateException("missing JDK field: "+name);fields.put(name,value(o.getValue(f),depth));}return fields;
    }
    static void install(VirtualMachine vm, ReferenceType t) throws Exception {
        if(t.name().equals(LOADER)){
            for(Method m:t.methodsByName("defineClass",DEFINE)){
                BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(m.location());q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();
            }return;
        }
        if(t.name().equals(INVOKER)){
            for(Method m:t.methods())if(EMITTERS.contains(m.name())&&m.signature().endsWith(")[B")){
                BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(m.location());q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();
            }return;
        }
        String name=t.name().equals(DEFINER)?"defineClass":"spinInnerClass";
        String desc=t.name().equals(DEFINER)?"(ZLjava/lang/Object;)Ljava/lang/Class;":"()Ljava/lang/Class;";
        for(Method m:t.methodsByName(name,desc)){
            BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(m.location());q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();
        }
    }
    public static void main(String[] args) throws Exception {
        Path out=Path.of(args[1]);Files.createDirectory(out);
        LaunchingConnector connector=Bootstrap.virtualMachineManager().defaultConnector();var a=connector.defaultArguments();
        a.get("main").setValue(args.length>2?args[2]:"HostPoolTarget");a.get("options").setValue("-cp \""+args[0]+"\"");a.get("suspend").setValue("true");
        VirtualMachine vm=connector.launch(a);Process child=vm.process();
        Thread stdout=Thread.ofPlatform().start(()->{try{Files.copy(child.getInputStream(),out.resolve("target.stdout"));}catch(Exception e){throw new RuntimeException(e);}});
        Thread stderr=Thread.ofPlatform().start(()->{try{Files.copy(child.getErrorStream(),out.resolve("target.stderr"));}catch(Exception e){throw new RuntimeException(e);}});
        List<Object> records=new ArrayList<>();Map<Long,Deque<Map<String,Object>>> pending=new HashMap<>();
        Map<Long,List<MethodExitRequest>> exits=new HashMap<>();boolean death=false;String error=null;long started=System.nanoTime();int checkpoints=0;
        try {
            if(!vm.canGetMethodReturnValues()||!vm.canGetBytecodes()||!vm.canGetConstantPool())throw new IllegalStateException("missing required JDI capability");
            ClassPrepareRequest preparation=vm.eventRequestManager().createClassPrepareRequest();preparation.setSuspendPolicy(EventRequest.SUSPEND_ALL);preparation.enable();
            for(String name:List.of(DEFINER,FACTORY,INVOKER,LOADER))for(ReferenceType t:vm.classesByName(name))install(vm,t);
            vm.resume();
            while(!death && System.nanoTime()-started<TimeUnit.SECONDS.toNanos(120)){
                EventSet set=vm.eventQueue().remove(1000);if(set==null)continue;
                for(Event event:set){
                    if(event instanceof ClassPrepareEvent e){
                        if(definitions.containsKey(Long.toString(e.referenceType().classObject().uniqueID())))remember(e.referenceType());
                        if(Set.of("HostGenerationTarget$Candidate","HostGenerationTarget$Support","HostGenerationTarget$Outside").contains(e.referenceType().name())){BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(e.referenceType().methodsByName("target").get(0).location());q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();}
                        else if(Set.of(DEFINER,FACTORY,INVOKER,LOADER).contains(e.referenceType().name()))install(vm,e.referenceType());
                        else if(e.referenceType().name().equals("HostPoolTarget")){BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(e.referenceType().methodsByName("checkpoint").get(0).location());q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();}
                    }else if(event instanceof BreakpointEvent e){
                        ThreadReference thread=e.thread();StackFrame top=thread.frame(0);
                        if(e.location().declaringType().name().startsWith("HostGenerationTarget$")){
                            List<Object> handles=new ArrayList<>();
                            for(StackFrame frame:thread.frames())if(!frame.location().method().isNative()){
                                List<Value> values=new ArrayList<>(frame.getArgumentValues());if(frame.thisObject()!=null)values.add(frame.thisObject());
                                for(Value v:values)if(v instanceof ObjectReference o && o.referenceType() instanceof ClassType ct){
                                    boolean handle=false;for(ClassType t=ct;t!=null;t=t.superclass())if(t.name().equals("java.lang.invoke.MethodHandle"))handle=true;
                                    if(handle)handles.add(Map.of("frame_class",frame.location().declaringType().name(),"frame_method",frame.location().method().name(),"code_index",frame.location().codeIndex(),"handle_graph",graph(o)));
                                }
                            }
                            records.add(Map.of("kind","target-checkpoint","stack",stack(thread),"handles",handles));continue;
                        }
                        if(e.location().declaringType().name().equals("HostPoolTarget")){
                            checkpoints++;List<Object> seen=new ArrayList<>();
                            for(ReferenceType t:vm.allClasses())if(t.name().contains("/")){remember(t);seen.add(t.classObject().uniqueID());}
                            records.add(Map.of("kind","checkpoint","phase",value(top.getArgumentValues().get(0),0),"hidden_class_ids",seen));continue;
                        }
                        Map<String,Object> r=new LinkedHashMap<>();r.put("kind","generation");r.put("thread_id",thread.uniqueID());r.put("entry_depth",thread.frameCount());
                        r.put("entry_method",e.location().declaringType().name()+"."+e.location().method().name()+e.location().method().signature());
                        r.put("stack",stack(thread));
                        if(e.location().declaringType().name().equals(LOADER)){
                            r.put("kind","ordinary-definition");
                            List<Value> argv=top.getArgumentValues();ArrayReference bytes=(ArrayReference)argv.get(1);
                            int offset=((IntegerValue)argv.get(2)).value(),length=((IntegerValue)argv.get(3)).value();
                            if(length<0 || length>4*1024*1024 || offset<0 || offset+length>bytes.length())throw new IllegalStateException("class definition size");
                            byte[] raw=new byte[length];for(int i=0;i<length;i++)raw[i]=((ByteValue)bytes.getValue(offset+i)).value();
                            r.put("definition_input_hex",HexFormat.of().formatHex(raw));r.put("definition_input_sha256",HostPoolObserver.hash(raw));
                            r.put("requested_name",value(argv.get(0),0));r.put("defining_loader",Long.toString(top.thisObject().uniqueID()));
                            if(argv.get(4) instanceof ObjectReference pd){
                                Field cs=pd.referenceType().fieldByName("codesource");ObjectReference source=cs==null?null:(ObjectReference)pd.getValue(cs);
                                if(source!=null){ObjectReference url=(ObjectReference)source.getValue(source.referenceType().fieldByName("location"));
                                    if(url!=null)r.put("code_source",selected(url,List.of("protocol","host","port","file"),0));
                                }
                            }
                        }
                        if(e.location().declaringType().name().equals(INVOKER)){
                            r.put("kind","generator-bytecode");r.put("generator_object_id",top.thisObject().uniqueID());
                            r.put("lambda_form_graph",graph(top.thisObject().getValue(top.thisObject().referenceType().fieldByName("lambdaForm"))));
                        }
                        if(e.location().declaringType().name().equals(DEFINER)){
                        r.put("definer",selected(top.thisObject(),List.of("lookup","name","classFlags"),1));
                        // A byte array read is corroboration only. Runtime CP/method reads below remain the executable evidence.
                        ArrayReference bytes=(ArrayReference)top.thisObject().getValue(top.thisObject().referenceType().fieldByName("bytes"));
                        byte[] raw=new byte[bytes.length()];for(int i=0;i<raw.length;i++)raw[i]=((ByteValue)bytes.getValue(i)).value();
                        r.put("definition_input_hex",HexFormat.of().formatHex(raw));r.put("definition_input_sha256",HostPoolObserver.hash(raw));r.put("definition_input_object_id",bytes.uniqueID());
                        r.put("class_data_graph",graph(top.getArgumentValues().get(1)));
                        for(StackFrame f:thread.frames())if(f.location().declaringType().name().equals("java.lang.invoke.InvokerBytecodeGenerator")&&f.thisObject()!=null){
                            Field field=f.thisObject().referenceType().fieldByName("lambdaForm");
                            r.put("lambda_form_graph",graph(f.thisObject().getValue(field)));break;
                        }
                        }
                        for(StackFrame f:thread.frames())if(f.location().declaringType().name().equals(FACTORY)&&f.thisObject()!=null){
                            r.put("lambda_factory",selected(f.thisObject(),List.of("targetClass","factoryType","interfaceClass","interfaceMethodName","interfaceMethodType","implementation","implMethodType","implInfo","implKind","implIsInstanceMethod","implClass","dynamicMethodType","isSerializable","altInterfaces","altMethods","implMethodClassName","implMethodName","implMethodDesc","argNames","argDescs","useImplMethodHandle"),2));break;
                        }
                        pending.computeIfAbsent(thread.uniqueID(),k->new ArrayDeque<>()).push(r);
                        if(!exits.containsKey(thread.uniqueID())){List<MethodExitRequest> qs=new ArrayList<>();for(String cls:List.of(DEFINER,FACTORY,INVOKER,LOADER)){MethodExitRequest q=vm.eventRequestManager().createMethodExitRequest();q.addClassFilter(cls);q.addThreadFilter(thread);q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();qs.add(q);}exits.put(thread.uniqueID(),qs);}
                    }else if(event instanceof MethodExitEvent e && ((e.method().declaringType().name().equals(DEFINER)&&e.method().name().equals("defineClass") && e.method().signature().equals("(ZLjava/lang/Object;)Ljava/lang/Class;")) || (e.method().declaringType().name().equals(FACTORY)&&e.method().name().equals("spinInnerClass")&&e.method().signature().equals("()Ljava/lang/Class;")) || (e.method().declaringType().name().equals(INVOKER)&&EMITTERS.contains(e.method().name())&&e.method().signature().endsWith(")[B")) || (e.method().declaringType().name().equals(LOADER)&&e.method().name().equals("defineClass")&&e.method().signature().equals(DEFINE)))){
                        Deque<Map<String,Object>> q=pending.get(e.thread().uniqueID());if(q==null||q.isEmpty())throw new IllegalStateException("unmatched generator return");
                        Map<String,Object> r=q.pop();if(!r.get("entry_depth").equals(e.thread().frameCount()))throw new IllegalStateException("generator depth mismatch");
                        if(!r.get("entry_method").equals(e.method().declaringType().name()+"."+e.method().name()+e.method().signature()))throw new IllegalStateException("generator method mismatch");
                        if(e.returnValue() instanceof ClassObjectReference c){remember(c.reflectedType());r.put("returned_class",value(c,0));}
                        else if(e.returnValue() instanceof ArrayReference bytes && bytes.referenceType().signature().equals("[B")){
                            byte[] raw=new byte[bytes.length()];for(int i=0;i<raw.length;i++)raw[i]=((ByteValue)bytes.getValue(i)).value();
                            r.put("returned_bytes_object_id",bytes.uniqueID());r.put("returned_bytes_hex",HexFormat.of().formatHex(raw));r.put("returned_bytes_sha256",HostPoolObserver.hash(raw));
                        }else throw new IllegalStateException("unexpected generator return type");
                        records.add(r);
                        if(q.isEmpty()){vm.eventRequestManager().deleteEventRequests(exits.remove(e.thread().uniqueID()));pending.remove(e.thread().uniqueID());}
                    }else if(event instanceof VMDeathEvent)death=true;
                }if(!death)set.resume();
            }
            if(!death||checkpoints!=5||!pending.isEmpty())throw new IllegalStateException("incomplete generation lifecycle");
            if(!child.waitFor(10,TimeUnit.SECONDS)||child.exitValue()!=0)throw new IllegalStateException("target exit failed");
        }catch(Exception failure){error=failure.toString();throw failure;}
        finally{
            if(child.isAlive()){child.destroyForcibly();child.waitFor();}stdout.join(10000);stderr.join(10000);
            Map<String,Object> r=new LinkedHashMap<>();r.put("schema","b06-host-generation-observation/1");r.put("records",records);r.put("definitions",definitions);r.put("error",error);r.put("complete",death&&checkpoints==5&&pending.isEmpty()&&error==null);r.put("elapsed_seconds",(System.nanoTime()-started)/1e9);r.put("model_calls",0);r.put("docker_commands",0);r.put("target_method_invocations",0);
            Files.writeString(out.resolve("observations.json"),HostPoolObserver.json(r));
        }
        System.out.println("HOST_GENERATION_OBSERVATION_COMPLETE");
    }
}
