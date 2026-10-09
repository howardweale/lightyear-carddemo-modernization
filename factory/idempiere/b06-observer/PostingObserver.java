package lightyear.observer;

import com.sun.jdi.*;
import com.sun.jdi.connect.AttachingConnector;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** External JDI collector. Never invokes a target method or consumes candidate trace text. */
public final class PostingObserver {
    private static final String SUPPORT = "org.idempiere.test.JourneySupport";
    private static final String CANDIDATE = "org.idempiere.test.LightyearOperationsTest";
    private static final String TERMINAL = "org.junit.platform.launcher.core.ExecutionListenerAdapter";
    private static final Set<String> TYPES = Set.of(SUPPORT, "org.compiere.model.PO",
        "org.compiere.acct.Doc", "org.compiere.acct.DocManager", "org.compiere.util.DB", TERMINAL);
    private final BufferedReader acknowledgements = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    private final Map<Long, Deque<Call>> active = new HashMap<>();
    private final Set<String> definitions = new HashSet<>();
    private final Set<String> configured = new HashSet<>();
    private VirtualMachine vm;
    private boolean bindingV2;
    private final Map<String,String> emittedV2Definitions=new HashMap<>();
    private long sequence = 0;
    /** Read the exact suspended-VM slice in bounded packets, never one JDWP request per byte. */
    static byte[] readBytes(ArrayReference array, int offset, int length) {
        int available=array.length();
        if(offset<0 || length<0 || length>1024*1024 || offset>available || length>available-offset)
            throw new IllegalStateException("byte array slice bound exceeded");
        byte[] result=new byte[length];
        for(int start=0;start<length;start+=16384) {
            int count=Math.min(16384,length-start);
            List<Value> values=array.getValues(offset+start,count);
            if(values.size()!=count)throw new IllegalStateException("short JDI byte array read");
            for(int i=0;i<count;i++)result[start+i]=((ByteValue)values.get(i)).value();
        }
        return result;
    }
    /** Generation evidence only: factory names select VM breakpoints, never grant trust. */
    private static final class Generation {
        static final String FACTORY="java.lang.invoke.InnerClassLambdaMetafactory";
        static final String INVOKER="java.lang.invoke.InvokerBytecodeGenerator";
        static final String LOADER="java.lang.ClassLoader";
        static final String DEFINE="(Ljava/lang/String;[BIILjava/security/ProtectionDomain;)Ljava/lang/Class;";
        static final Set<String> EMITTERS=Set.of("generateCustomizedCodeBytes","generateLambdaFormInterpreterEntryPointBytes","generateNamedFunctionInvokerImpl");
        boolean v2;
        static final String DEFINER="java.lang.invoke.MethodHandles$Lookup$ClassDefiner";
        static final Map<String,Object> definitions=new LinkedHashMap<>();
        final Map<Long,Deque<Map<String,Object>>> pending=new HashMap<>();
        final Map<Long,MethodExitRequest> exits=new HashMap<>();
        final Map<Long,Map<String,Object>> completed=new HashMap<>();
        final Set<String> installed=new HashSet<>();
    static Map<String,Object> readDefinition(ReferenceType type) throws Exception {
        Map<String,Object> r=new LinkedHashMap<>();byte[] cp=type.constantPool();
        r.put("class",type.name());r.put("signature",type.signature());r.put("loader",type.classLoader()==null?"bootstrap":Long.toString(type.classLoader().uniqueID()));
        r.put("module",type.module().name());r.put("module_id",type.module().uniqueID());
        r.put("module_loader",type.module().classLoader()==null?"bootstrap":Long.toString(type.module().classLoader().uniqueID()));
        r.put("loader_class",type.classLoader()==null?null:type.classLoader().referenceType().name());
        r.put("loader_class_object_id",type.classLoader()==null?null:type.classLoader().referenceType().classObject().uniqueID());r.put("class_object_id",type.classObject().uniqueID());r.put("modifiers",type.modifiers());
        r.put("constant_pool_count",type.constantPoolCount());r.put("constant_pool_hex",HexFormat.of().formatHex(cp));r.put("constant_pool_sha256",hash(cp));
        List<Object> methods=new ArrayList<>();
        for(Method m:type.methods()) { Map<String,Object> x=new LinkedHashMap<>();x.put("name",m.name());x.put("signature",m.signature());x.put("modifiers",m.modifiers());
            if(!m.isNative()&&!m.isAbstract()){byte[] b=m.bytecodes();x.put("bytecode_hex",HexFormat.of().formatHex(b));x.put("sha256",hash(b));}methods.add(x); }
        r.put("methods",methods);return r;
    }
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
                List<Value> values=array.getValues();
                for(int i=0;i<values.size();i++)selected.put(Integer.toString(i),values.get(i));
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
            Map<String,Object> d=readDefinition(t);
            if(t.classLoader()!=null)remember(t.classLoader().referenceType());
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

        boolean selected(Method m) {
            return (v2 && m.declaringType().name().equals(LOADER) && m.name().equals("defineClass") && m.signature().equals(DEFINE))
                || (v2 && m.declaringType().name().equals(INVOKER) && EMITTERS.contains(m.name()) && m.signature().endsWith(")[B"))
                || (m.declaringType().name().equals(FACTORY) && m.name().equals("spinInnerClass") && m.signature().equals("()Ljava/lang/Class;"))
                || (m.declaringType().name().equals(DEFINER) && m.name().equals("defineClass") && m.signature().equals("(ZLjava/lang/Object;)Ljava/lang/Class;"));
        }
        void configure(VirtualMachine vm,ReferenceType t) {
            if(!(v2?Set.of(FACTORY,DEFINER,INVOKER,LOADER):Set.of(FACTORY,DEFINER)).contains(t.name()) || !installed.add(t.name()+":"+loader(t)))return;
            for(Method m:t.methods())if(selected(m)){
                BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(m.location());
                q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();
                for(int index:returnInstructions(m.bytecodes())) {
                    BreakpointRequest ret=vm.eventRequestManager().createBreakpointRequest(m.locationOfCodeIndex(index));
                    ret.putProperty("generation-return",true);ret.setSuspendPolicy(EventRequest.SUSPEND_ALL);ret.enable();
                }
            }
        }
        // Walk instructions, never search raw operand bytes for opcode 0xb0.
        static List<Integer> returnInstructions(byte[] code) {
            List<Integer> result=new ArrayList<>();
            java.nio.ByteBuffer b=java.nio.ByteBuffer.wrap(code);
            for(int i=0;i<code.length;) {
                int op=code[i]&255, size=1;
                if(op==0xb0)result.add(i);
                if(op==0xaa || op==0xab) {
                    int start=(i+4)&~3;
                    if(op==0xaa) {int low=b.getInt(start+4),high=b.getInt(start+8);if(high<low)throw new IllegalStateException("bad switch");size=start-i+12+Math.multiplyExact(high-low+1,4);}
                    else {int pairs=b.getInt(start+4);if(pairs<0)throw new IllegalStateException("bad switch");size=start-i+8+Math.multiplyExact(pairs,8);}
                } else if(op==0xc4) {size=(code[i+1]&255)==0x84?6:4;}
                else if(op==0xb9 || op==0xba || op==0xc8 || op==0xc9)size=5;
                else if(op==0xc5)size=4;
                else if(op==0x11 || op==0x13 || op==0x14 || op==0x84 || op>=0x99 && op<=0xa8 || op>=0xb2 && op<=0xb8 || op==0xbb || op==0xbd || op==0xc0 || op==0xc1 || op==0xc6 || op==0xc7)size=3;
                else if(op==0x10 || op==0x12 || op>=0x15 && op<=0x19 || op>=0x36 && op<=0x3a || op==0xa9 || op==0xbc)size=2;
                else if(op>0xc9)throw new IllegalStateException("unsupported opcode");
                if(size<=0 || i+size>code.length)throw new IllegalStateException("truncated instruction");i+=size;
            }
            return result;
        }
        void atReturn(VirtualMachine vm,BreakpointEvent e) {
            // JDI has no operand-stack read. Arm an exact class/thread exit only
            // at ARETURN; no intervening Java invocation can occur.
            if(exits.containsKey(e.thread().uniqueID()))throw new IllegalStateException("duplicate return arm");
            MethodExitRequest q=vm.eventRequestManager().createMethodExitRequest();
            q.addThreadFilter(e.thread());q.addClassFilter(e.location().declaringType());
            q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();exits.put(e.thread().uniqueID(),q);
        }
        Map<String,Object> enter(VirtualMachine vm,BreakpointEvent e) throws Exception {
            ThreadReference t=e.thread();
            Map<String,Object> r=new LinkedHashMap<>();r.put("kind","generation");r.put("thread_id",t.uniqueID());
            r.put("entry_depth",t.frameCount());r.put("entry_method",e.location().declaringType().name()+"."+e.location().method().name()+e.location().method().signature());
            r.put("stack",stack(t));
            StackFrame top=t.frame(0);
            if(v2){
                        if(e.location().declaringType().name().equals(LOADER)){
                            r.put("kind","ordinary-definition");
                            List<Value> argv=top.getArgumentValues();ArrayReference bytes=(ArrayReference)argv.get(1);
                            int offset=((IntegerValue)argv.get(2)).value(),length=((IntegerValue)argv.get(3)).value();
                            if(length<0 || length>1024*1024 || offset<0 || offset+length>bytes.length())throw new IllegalStateException("class definition size");
                            byte[] raw=readBytes(bytes,offset,length);
                            r.put("definition_input_hex",HexFormat.of().formatHex(raw));r.put("definition_input_sha256",hash(raw));
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
                        if(bytes.length()>1024*1024)throw new IllegalStateException("definition size bound");
                        byte[] raw=readBytes(bytes,0,bytes.length());
                        r.put("definition_input_hex",HexFormat.of().formatHex(raw));r.put("definition_input_sha256",hash(raw));r.put("definition_input_object_id",bytes.uniqueID());
                        r.put("class_data_graph",graph(top.getArgumentValues().get(1)));
                        for(StackFrame f:t.frames())if(f.location().declaringType().name().equals("java.lang.invoke.InvokerBytecodeGenerator")&&f.thisObject()!=null){
                            Field field=f.thisObject().referenceType().fieldByName("lambdaForm");
                            r.put("lambda_form_graph",graph(f.thisObject().getValue(field)));break;
                        }
                        }
            }
            if(e.location().declaringType().name().equals(FACTORY)){
                r.put("lambda_factory",selected(t.frame(0).thisObject(),List.of("targetClass","factoryType","interfaceClass","interfaceMethodName","interfaceMethodType","implementation","implMethodType","implInfo","implKind","implIsInstanceMethod","implClass","dynamicMethodType","isSerializable","altInterfaces","altMethods","implMethodClassName","implMethodName","implMethodDesc","argNames","argDescs","useImplMethodHandle"),2));
            }
            pending.computeIfAbsent(t.uniqueID(),k->new ArrayDeque<>()).push(r);
            return r;
        }
        Map<String,Object> returned(VirtualMachine vm,MethodExitEvent e) throws Exception {
            Deque<Map<String,Object>> q=pending.get(e.thread().uniqueID());
            if(q==null || q.isEmpty() || !selected(e.method()))return null;
            Map<String,Object> r=q.pop();
            String name=e.method().declaringType().name()+"."+e.method().name()+e.method().signature();
            if(!r.get("entry_method").equals(name) || !r.get("entry_depth").equals(e.thread().frameCount()))throw new IllegalStateException("generation return mismatch");
            if(e.returnValue() instanceof ClassObjectReference c){
                remember(c.reflectedType());r.put("returned_class",value(c,0));
                if(name.startsWith(FACTORY+"."))completed.put(c.uniqueID(),r);
            }else if(v2 && e.returnValue() instanceof ArrayReference a && a.referenceType().signature().equals("[B")){
                if(a.length()>1024*1024)throw new IllegalStateException("generated byte array bound exceeded");
                byte[] bytes=readBytes(a,0,a.length());
                r.put("returned_bytes_object_id",a.uniqueID());r.put("returned_bytes_hex",HexFormat.of().formatHex(bytes));r.put("returned_bytes_sha256",hash(bytes));
            }else throw new IllegalStateException("generation return unsupported");
            MethodExitRequest armed=exits.remove(e.thread().uniqueID());
            if(armed==null || !armed.equals(e.request()))throw new IllegalStateException("unarmed generation exit");
            vm.eventRequestManager().deleteEventRequest(armed);
            if(q.isEmpty())pending.remove(e.thread().uniqueID());
            return r;
        }
        Map<String,Object> proof(ReferenceType t) throws Exception {
            Map<String,Object> record=completed.get(t.classObject().uniqueID());
            if(record==null)return null;
            remember(t);
            Map<?,?> factory=(Map<?,?>)record.get("lambda_factory");
            Map<?,?> host=(Map<?,?>)factory.get("targetClass");
            String hostId=host.get("class_object_id").toString(), generatedId=Long.toString(t.classObject().uniqueID());
            return Map.of("record",record,"definitions",Map.of(hostId,definitions.get(hostId),generatedId,definitions.get(generatedId)));
        }
    }
    private final Generation generation=new Generation();
    private record GenerationCatch(BreakpointRequest request, String exceptionClass) {}
    private final Map<Long,GenerationCatch> generationCatches=new HashMap<>();

    private record Call(long sequence, Method method, List<Integer> document, MethodExitRequest exit, int depth) {}

    private static String hash(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?,?> map) {
            List<String> fields = new ArrayList<>();
            for (var entry : map.entrySet()) fields.add(json(entry.getKey().toString()) + ":" + json(entry.getValue()));
            return "{" + String.join(",", fields) + "}";
        }
        if (value instanceof Iterable<?> iterable) {
            List<String> fields = new ArrayList<>();
            for (Object item : iterable) fields.add(json(item));
            return "[" + String.join(",", fields) + "]";
        }
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toString().toCharArray()) {
            if (c == '"' || c == '\\') out.append('\\').append(c);
            else if (c < 32) out.append(String.format("\\u%04x", (int)c));
            else out.append(c);
        }
        return out.append('"').toString();
    }
    private long emit(Map<String,Object> value, boolean checkpoint) throws Exception {
        value.put("sequence", ++sequence);
        value.put("checkpoint", checkpoint);
        System.out.println(json(value)); System.out.flush();
        if (checkpoint && !Long.toString(sequence).equals(acknowledgements.readLine()))
            throw new IOException("Missing trusted native-readback acknowledgement");
        return sequence;
    }
    private static Value field(ObjectReference object, String name) {
        Field found = object.referenceType().fieldByName(name);
        if (found == null) throw new IllegalStateException("Required native model field missing");
        return object.getValue(found);
    }
    private static List<Integer> po(ObjectReference object) {
        ObjectReference info = (ObjectReference)field(object, "p_info");
        int table = ((IntegerValue)field(info, "m_AD_Table_ID")).value();
        ArrayReference ids = (ArrayReference)field(object, "m_IDs");
        if (ids.length() != 1) throw new IllegalStateException("Composite document key unsupported");
        int id = ((IntegerValue)field((ObjectReference)ids.getValue(0), "value")).value();
        if (table <= 0 || id <= 0) throw new IllegalStateException("Unpersisted document");
        return List.of(table, id);
    }
    private List<Integer> document(StackFrame frame) throws Exception {
        String type = frame.location().declaringType().name();
        List<Value> args = frame.getArgumentValues();
        if (type.equals(SUPPORT)) return po((ObjectReference)args.get(0));
        if (type.equals("org.compiere.model.PO")) return po(frame.thisObject());
        if (type.equals("org.compiere.acct.Doc")) return po((ObjectReference)field(frame.thisObject(), "p_po"));
        return List.of(((IntegerValue)args.get(1)).value(), ((IntegerValue)args.get(2)).value());
    }
    private Map<String,Object> location(Location location) throws Exception {
        Method method = location.method();
        ReferenceType type = location.declaringType();
        String loader = type.classLoader() == null ? "bootstrap" : Long.toString(type.classLoader().uniqueID());
        byte[] pool = type.constantPool();
        boolean unavailable = method.isNative() || method.isAbstract();
        byte[] bytes = unavailable ? new byte[0] : method.bytecodes();
        String methodHash = unavailable ? "unavailable" : hash(bytes), poolHash = hash(pool);
        String id = loader + ":" + type.classObject().uniqueID() + ":" + method.name() + method.signature()
            + ":" + poolHash + ":" + methodHash;
        // Capture every definition, including all hidden classes, without a name allowlist.
        // This external JDI read invokes no target method and reads no captured values.
        if (definitions.add(id)) {
            Map<String,Object> definition = new LinkedHashMap<>();
            definition.put("definition_id", id); definition.put("class", type.name());
            definition.put("class_signature", type.signature());
            definition.put("class_object_id", type.classObject().uniqueID());
            definition.put("class_modifiers", type.modifiers()); definition.put("loader", loader);
            definition.put("method", method.name()); definition.put("signature", method.signature());
            definition.put("method_modifiers", method.modifiers()); definition.put("native_or_abstract", unavailable);
            definition.put("constant_pool_count", type.constantPoolCount());
            definition.put("constant_pool_hex", HexFormat.of().formatHex(pool));
            definition.put("constant_pool_sha256", poolHash);
            definition.put("bytecode_hex", HexFormat.of().formatHex(bytes));
            definition.put("method_sha256", methodHash);
            List<Map<String,Object>> fields = new ArrayList<>();
            for (Field f : type.fields()) fields.add(Map.of("name", f.name(), "signature", f.signature(), "modifiers", f.modifiers()));
            definition.put("fields", fields);
            Map<String,Object> provenance=generation.proof(type);
            if(provenance!=null)definition.put("generation",provenance);
            emit(new LinkedHashMap<>(Map.of("kind", "frame-definition", "definition", definition)), false);
        }
        Map<String,Object> result=new LinkedHashMap<>(Map.of("class", type.name(), "method", method.name(), "signature", method.signature(), "line", location.lineNumber(),
                      "code_index", location.codeIndex(), "method_sha256", methodHash,
                      "constant_pool_sha256", poolHash, "loader", loader, "definition_id", id));
        if(bindingV2){Generation.definitions.remove(Long.toString(type.classObject().uniqueID()));Generation.remember(type);result.put("class_object_id",type.classObject().uniqueID());result.put("module",type.module().name());}
        return result;
    }
    private List<Map<String,Object>> frames(ThreadReference thread) throws Exception {
        List<Map<String,Object>> result = new ArrayList<>();
        for (StackFrame frame : thread.frames()) {
            Map<String,Object> item=location(frame.location());
            if(bindingV2 && !frame.location().method().isNative()) {
                List<Object> handles=new ArrayList<>();List<Value> values=new ArrayList<>(frame.getArgumentValues());
                if(frame.thisObject()!=null)values.add(frame.thisObject());
                for(int i=0;i<values.size();i++)if(values.get(i) instanceof ObjectReference o && o.referenceType() instanceof ClassType ct){
                    boolean handle=false;for(ClassType t=ct;t!=null;t=t.superclass())if(t.name().equals("java.lang.invoke.MethodHandle"))handle=true;
                    if(handle)handles.add(Map.of("value_index",i,"handle_graph",Generation.graph(o)));
                }
                item.put("handle_uses",handles);
            }
            result.add(item);
        }
        if(bindingV2)flushDefinitions();
        return result;
    }
    private void flushDefinitions() throws Exception {
        for(var entry:Generation.definitions.entrySet()) {
            String sha=hash(json(entry.getValue()).getBytes(StandardCharsets.UTF_8));
            if(!sha.equals(emittedV2Definitions.get(entry.getKey()))) {
                emit(new LinkedHashMap<>(Map.of("kind","class-definition-v2","definition",entry.getValue())),false);
                emittedV2Definitions.put(entry.getKey(),sha);
            }
        }
    }
    private boolean relevant(ThreadReference thread) throws Exception {
        for(StackFrame f:thread.frames()) {String n=f.location().declaringType().name();if(n.equals(SUPPORT)||n.equals(CANDIDATE)||n.startsWith(CANDIDATE+"$"))return true;}
        return false;
    }
    private boolean selected(Method method) {
        String type = method.declaringType().name(), name = method.name(), signature = method.signature();
        return (type.equals(TERMINAL) && name.equals("executionFinished")
                && signature.equals("(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V"))
            || (type.equals("org.compiere.util.DB") && name.equals("executeUpdate")
                && signature.equals("(Ljava/lang/String;Ljava/lang/String;)I"))
            || (type.equals(SUPPORT) && name.equals("postOnce") && signature.equals("(Lorg/compiere/model/PO;[Lorg/compiere/model/MAcctSchema;)V"))
            || (type.equals("org.compiere.model.PO") && name.equals("lock") && signature.equals("()Z"))
            || (type.equals("org.compiere.acct.Doc") && name.equals("post") && signature.equals("(ZZZ)Ljava/lang/String;"))
            || (type.equals("org.compiere.acct.DocManager") && name.equals("postDocument")
                && signature.equals("([Lorg/compiere/model/MAcctSchema;IIZZLjava/lang/String;)Ljava/lang/String;"));
    }
    private void configure(ReferenceType type) {
        generation.configure(vm,type);
        if (!TYPES.contains(type.name()) || !configured.add(type.name() + ":" + type.classLoader())) return;
        for (Method method : type.methods()) if (selected(method)) {
            BreakpointRequest request = vm.eventRequestManager().createBreakpointRequest(method.location());
            request.setSuspendPolicy(EventRequest.SUSPEND_ALL); request.enable();
        }
    }
    private void entry(BreakpointEvent event) throws Exception {
        if(Boolean.TRUE.equals(event.request().getProperty("generation-catch"))) {generationCatch(event);return;}
        if(Boolean.TRUE.equals(event.request().getProperty("generation-return"))) {generation.atReturn(vm,event);return;}
        if(generation.selected(event.location().method())) {
            emit(new LinkedHashMap<>(Map.of("kind","generation-entry","record",generation.enter(vm,event))),false);return;
        }
        ThreadReference thread = event.thread(); Method method = event.location().method();
        if(!method.declaringType().name().equals(TERMINAL) && !relevant(thread))return;
        List<Map<String,Object>> stack = frames(thread);
        if (method.declaringType().name().equals(TERMINAL)) {
            terminal(thread, stack); return;
        }
        if (stack.stream().noneMatch(f -> f.get("class").equals(SUPPORT) || f.get("class").toString().startsWith(CANDIDATE))) return;
        StackFrame modelFrame = thread.frame(0);
        boolean database = method.declaringType().name().equals("org.compiere.util.DB");
        if (database) {
            // Observe only the direct lock UPDATE in the hash-bound Doc.post;
            // never assign a document from SQL text supplied by a candidate.
            if (thread.frameCount() < 2 || !thread.frame(1).location().declaringType().name().equals("org.compiere.acct.Doc")
                    || !thread.frame(1).location().method().name().equals("post")) return;
            modelFrame = thread.frame(1);
        }
        List<Integer> document = document(modelFrame);
        Map<String,Object> record = new LinkedHashMap<>();
        record.put("kind", "method-entry"); record.put("thread", thread.uniqueID());
        record.put("document", document); record.put("frames", stack);
        if (database) record.put("sql", ((StringReference)thread.frame(0).getArgumentValues().get(0)).value());
        if (modelFrame.location().declaringType().name().equals("org.compiere.acct.Doc")) {
            List<Value> args = modelFrame.getArgumentValues();
            record.put("force", ((BooleanValue)args.get(0)).value());
            record.put("repost", ((BooleanValue)args.get(1)).value());
        }
        long id = emit(record, true);
        MethodExitRequest exit = vm.eventRequestManager().createMethodExitRequest();
        exit.addThreadFilter(thread); exit.addClassFilter(method.declaringType());
        exit.setSuspendPolicy(EventRequest.SUSPEND_ALL); exit.enable();
        active.computeIfAbsent(thread.uniqueID(), unused -> new ArrayDeque<>()).push(new Call(id, method, document, exit, thread.frameCount()));
    }
    private void terminal(ThreadReference thread, List<Map<String,Object>> stack) throws Exception {
        // Read the real engine descriptor/result, not XML or candidate log text.
        List<Value> args = thread.frame(0).getArgumentValues();
        ObjectReference descriptor = (ObjectReference)args.get(0);
        if (descriptor.referenceType().fieldByName("testMethod") == null) return; // container descriptor
        ObjectReference method = (ObjectReference)field(descriptor, "testMethod");
        ClassObjectReference owner = (ClassObjectReference)field(method, "clazz");
        if (!owner.reflectedType().name().equals(CANDIDATE)) return;
        ObjectReference result = (ObjectReference)args.get(1);
        ObjectReference status = (ObjectReference)field(result, "status");
        ObjectReference throwable = (ObjectReference)field(result, "throwable");
        Map<String,Object> record = new LinkedHashMap<>();
        record.put("kind", "test-terminal"); record.put("thread", thread.uniqueID());
        record.put("frames", stack); record.put("descriptor_id", descriptor.uniqueID());
        record.put("descriptor_class", descriptor.referenceType().name());
        record.put("test_class", owner.reflectedType().name());
        record.put("test_method", ((StringReference)field(method, "name")).value());
        record.put("status", ((StringReference)field(status, "name")).value());
        record.put("exception_id", throwable == null ? null : throwable.uniqueID());
        emit(record, true);
    }
    private void exit(MethodExitEvent event) throws Exception {
        if(event.request().equals(generation.exits.get(event.thread().uniqueID()))) {
            Map<String,Object> record=generation.returned(vm,event);
            if(record!=null)emit(new LinkedHashMap<>(Map.of("kind","generation-return","record",record)),false);
            return;
        }
        Deque<Call> calls = active.get(event.thread().uniqueID());
        if (calls == null || calls.isEmpty() || !calls.peek().method().equals(event.method())
                || !calls.peek().exit().equals(event.request())) return;
        Call call = calls.pop(); vm.eventRequestManager().deleteEventRequest(call.exit());
        Value returned = event.returnValue(); Object value = null;
        if (returned instanceof BooleanValue b) value = b.value();
        else if (returned instanceof IntegerValue i) value = i.value();
        else if (returned instanceof StringReference s) value = s.value();
        else if (returned != null && !(returned instanceof VoidValue)) throw new IllegalStateException("Unexpected posting return type");
        Map<String,Object> record = new LinkedHashMap<>();
        record.put("kind", "method-exit"); record.put("thread", event.thread().uniqueID());
        record.put("call_sequence", call.sequence()); record.put("document", call.document());
        record.put("return_value", value); record.put("frames", frames(event.thread()));
        emit(record, true);
    }
    private void unwindGeneration(ThreadReference thread, int depth, String exceptionClass,
                                  Map<String,Object> resolution) throws Exception {
        Deque<Map<String,Object>> generated=generation.pending.get(thread.uniqueID());
        if(generated==null)return;
        while(!generated.isEmpty() && ((Number)generated.peek().get("entry_depth")).intValue()>depth) {
            Map<String,Object> unwound=generated.pop();
            emit(new LinkedHashMap<>(Map.of("kind","generation-unwind","record",unwound,
                "exception_class",exceptionClass,"catch_depth",depth,"catch_resolution",resolution)),false);
        }
        if(generated.isEmpty())generation.pending.remove(thread.uniqueID());
    }
    private void generationCatch(BreakpointEvent event) throws Exception {
        GenerationCatch pending=generationCatches.remove(event.thread().uniqueID());
        if(pending==null || !pending.request().equals(event.request()) ||
           !pending.request().location().equals(event.location()))throw new IllegalStateException("unarmed generation catch");
        vm.eventRequestManager().deleteEventRequest(pending.request());
        // JDI gives a catch Location, not an activation identity. Observe the
        // handler itself: its top frame is now the actual selected activation,
        // even if recursive invocations of the same Method were on the stack.
        if(!event.thread().frame(0).location().equals(event.location()))throw new IllegalStateException("generation catch not top frame");
        int depth=event.thread().frameCount();
        unwindGeneration(event.thread(),depth,pending.exceptionClass(),Map.of(
            "kind","handler-breakpoint","thread_id",event.thread().uniqueID(),
            "frame_count",depth,"location",location(event.location())));
    }
    private void failure(ExceptionEvent event) throws Exception {
        long threadId=event.thread().uniqueID();
        GenerationCatch prior=generationCatches.remove(threadId);
        if(prior!=null)vm.eventRequestManager().deleteEventRequest(prior.request());
        Deque<Map<String,Object>> generated=generation.pending.get(threadId);
        if(generated!=null) {
            // A superseding exception (for example in a finally block) selects
            // its own handler. Never guess an activation from repeated methods.
            if(event.catchLocation()==null) {
                unwindGeneration(event.thread(),-1,event.exception().referenceType().name(),
                    Map.of("kind","uncaught","thread_id",threadId,"frame_count",0));
            } else {
                BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(event.catchLocation());
                q.addThreadFilter(event.thread());q.putProperty("generation-catch",true);
                q.setSuspendPolicy(EventRequest.SUSPEND_ALL);
                generationCatches.put(threadId,new GenerationCatch(q,event.exception().referenceType().name()));q.enable();
            }
            MethodExitRequest armed=generation.exits.remove(threadId);
            if(armed!=null)vm.eventRequestManager().deleteEventRequest(armed);
        }
        if(!relevant(event.thread()))return;
        List<Map<String,Object>> stack = frames(event.thread());
        if (stack.stream().noneMatch(f -> f.get("class").equals(SUPPORT) || f.get("class").toString().startsWith(CANDIDATE))) return;
        Map<String,Object> record = new LinkedHashMap<>();
        record.put("kind", "exception"); record.put("thread", event.thread().uniqueID());
        record.put("exception_class", event.exception().referenceType().name());
        record.put("exception_id", event.exception().uniqueID());
        List<String> ancestry = new ArrayList<>();
        for (ClassType type = (ClassType)event.exception().referenceType(); type != null; type = type.superclass())
            ancestry.add(type.name());
        record.put("exception_ancestry", ancestry);
        record.put("frames", stack); record.put("caught", event.catchLocation() != null);
        record.put("catch_location", event.catchLocation() == null ? null : location(event.catchLocation()));
        // Exceptional unwinds do not emit MethodExitEvent. Record the exact
        // affected calls while the real stack is still available, then remove
        // their requests. Never pretend these were successful normal returns.
        int catchDepth = -1;
        if (event.catchLocation() != null) {
            List<StackFrame> nativeFrames = event.thread().frames();
            for (int i = 0; i < nativeFrames.size(); i++)
                if (nativeFrames.get(i).location().method().equals(event.catchLocation().method())) {
                    if (catchDepth >= 0) throw new IllegalStateException("Ambiguous recursive catch frame");
                    catchDepth = nativeFrames.size() - i;
                }
            if (catchDepth < 0) throw new IllegalStateException("Catch frame not found");
        }
        List<Long> unwound = new ArrayList<>();
        Deque<Call> calls = active.get(event.thread().uniqueID());
        while (calls != null && !calls.isEmpty() && calls.peek().depth() > catchDepth) {
            Call call = calls.pop(); unwound.add(call.sequence());
            vm.eventRequestManager().deleteEventRequest(call.exit());
        }
        record.put("unwound_calls", unwound);
        if(bindingV2)flushDefinitions();
        emit(record, true);
    }
    private void run(String host, String port) throws Exception {
        AttachingConnector connector = Bootstrap.virtualMachineManager().attachingConnectors().stream()
            .filter(c -> c.name().equals("com.sun.jdi.SocketAttach")).findFirst().orElseThrow();
        var args = connector.defaultArguments(); args.get("hostname").setValue(host); args.get("port").setValue(port);
        args.get("timeout").setValue("30000"); vm = connector.attach(args);
        if (!vm.canGetBytecodes() || !vm.canGetConstantPool() || !vm.canGetMethodReturnValues())
            throw new IllegalStateException("Required VM inspection unavailable");
        Set<String> observedTypes=new HashSet<>(TYPES);observedTypes.add(Generation.FACTORY);observedTypes.add(Generation.DEFINER);
        if(bindingV2){observedTypes.add(Generation.INVOKER);observedTypes.add(Generation.LOADER);}
        for (String type : observedTypes) {
            ClassPrepareRequest request = vm.eventRequestManager().createClassPrepareRequest();
            request.addClassFilter(type); request.setSuspendPolicy(EventRequest.SUSPEND_ALL); request.enable();
        }
        for (ReferenceType type : vm.allClasses()) configure(type);
        ExceptionRequest exceptions = vm.eventRequestManager().createExceptionRequest(null, true, true);
        exceptions.setSuspendPolicy(EventRequest.SUSPEND_ALL); exceptions.enable();
        emit(new LinkedHashMap<>(Map.of("kind", "ready", "vm_version", vm.version(), "binding_version", bindingV2?2:1, "generation_catch_policy", "handler-activation-v1")), false);
        vm.resume();
        boolean running = true;
        while (running) {
            EventSet set = vm.eventQueue().remove(1000);
            if (set == null) continue;
            for (Event event : set) {
                if (event instanceof ClassPrepareEvent prepared) configure(prepared.referenceType());
                else if (event instanceof BreakpointEvent breakpoint) entry(breakpoint);
                else if (event instanceof MethodExitEvent methodExit) exit(methodExit);
                else if (event instanceof ExceptionEvent exception) failure(exception);
                else if (event instanceof VMDeathEvent) {
                    emit(new LinkedHashMap<>(Map.of("kind", "vm-death", "generation_pending", generation.pending.size())), false); running = false;
                } else if (event instanceof VMDisconnectEvent) running = false;
            }
            if (running) set.resume();
        }
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 2 && !(args.length==3 && args[2].equals("observer-binding-v2"))) throw new IllegalArgumentException("host, port and optional observer-binding-v2 required");
        PostingObserver observer=new PostingObserver();observer.bindingV2=args.length==3;
        observer.generation.v2=observer.bindingV2;observer.run(args[0],args[1]);
    }
}
