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
    private long sequence = 0;
    /** Generation evidence only: factory names select VM breakpoints, never grant trust. */
    private static final class Generation {
        static final String FACTORY="java.lang.invoke.InnerClassLambdaMetafactory";
        static final String DEFINER="java.lang.invoke.MethodHandles$Lookup$ClassDefiner";
        static final Map<String,Object> definitions=new LinkedHashMap<>();
        final Map<Long,Deque<Map<String,Object>>> pending=new HashMap<>();
        final Map<Long,MethodExitRequest> exits=new HashMap<>();
        final Map<Long,Map<String,Object>> completed=new HashMap<>();
        final Set<String> installed=new HashSet<>();
    static Map<String,Object> readDefinition(ReferenceType type) throws Exception {
        Map<String,Object> r=new LinkedHashMap<>();byte[] cp=type.constantPool();
        r.put("class",type.name());r.put("signature",type.signature());r.put("loader",type.classLoader()==null?"bootstrap":Long.toString(type.classLoader().uniqueID()));
        r.put("module",type.module().name());r.put("class_object_id",type.classObject().uniqueID());r.put("modifiers",type.modifiers());
        r.put("constant_pool_count",type.constantPoolCount());r.put("constant_pool_hex",HexFormat.of().formatHex(cp));r.put("constant_pool_sha256",hash(cp));
        List<Object> methods=new ArrayList<>();
        for(Method m:type.methods()) { Map<String,Object> x=new LinkedHashMap<>();x.put("name",m.name());x.put("signature",m.signature());x.put("modifiers",m.modifiers());
            if(!m.isNative()&&!m.isAbstract()){byte[] b=m.bytecodes();x.put("bytecode_hex",HexFormat.of().formatHex(b));x.put("sha256",hash(b));}methods.add(x); }
        r.put("methods",methods);return r;
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
            return (m.declaringType().name().equals(FACTORY) && m.name().equals("spinInnerClass") && m.signature().equals("()Ljava/lang/Class;"))
                || (m.declaringType().name().equals(DEFINER) && m.name().equals("defineClass") && m.signature().equals("(ZLjava/lang/Object;)Ljava/lang/Class;"));
        }
        void configure(VirtualMachine vm,ReferenceType t) {
            if(!Set.of(FACTORY,DEFINER).contains(t.name()) || !installed.add(t.name()+":"+loader(t)))return;
            for(Method m:t.methods())if(selected(m)){
                BreakpointRequest q=vm.eventRequestManager().createBreakpointRequest(m.location());
                q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();
            }
        }
        Map<String,Object> enter(VirtualMachine vm,BreakpointEvent e) throws Exception {
            ThreadReference t=e.thread();
            Map<String,Object> r=new LinkedHashMap<>();r.put("kind","generation");r.put("thread_id",t.uniqueID());
            r.put("entry_depth",t.frameCount());r.put("entry_method",e.location().declaringType().name()+"."+e.location().method().name()+e.location().method().signature());
            r.put("stack",stack(t));
            if(e.location().declaringType().name().equals(FACTORY)){
                r.put("lambda_factory",selected(t.frame(0).thisObject(),List.of("targetClass","factoryType","interfaceClass","interfaceMethodName","interfaceMethodType","implementation","implMethodType","implInfo","implKind","implIsInstanceMethod","implClass","dynamicMethodType","isSerializable","altInterfaces","altMethods","implMethodClassName","implMethodName","implMethodDesc","argNames","argDescs","useImplMethodHandle"),2));
            }
            pending.computeIfAbsent(t.uniqueID(),k->new ArrayDeque<>()).push(r);
            if(!exits.containsKey(t.uniqueID())){
                MethodExitRequest q=vm.eventRequestManager().createMethodExitRequest();q.addThreadFilter(t);
                q.addClassFilter("java.lang.invoke.*");q.setSuspendPolicy(EventRequest.SUSPEND_ALL);q.enable();exits.put(t.uniqueID(),q);
            }
            return r;
        }
        Map<String,Object> returned(VirtualMachine vm,MethodExitEvent e) throws Exception {
            Deque<Map<String,Object>> q=pending.get(e.thread().uniqueID());
            if(q==null || q.isEmpty() || !selected(e.method()))return null;
            Map<String,Object> r=q.pop();
            String name=e.method().declaringType().name()+"."+e.method().name()+e.method().signature();
            if(!r.get("entry_method").equals(name) || !r.get("entry_depth").equals(e.thread().frameCount()))throw new IllegalStateException("generation return mismatch");
            if(!(e.returnValue() instanceof ClassObjectReference c))throw new IllegalStateException("generation return not Class");
            remember(c.reflectedType());r.put("returned_class",value(c,0));
            if(name.startsWith(FACTORY+"."))completed.put(c.uniqueID(),r);
            if(q.isEmpty()){vm.eventRequestManager().deleteEventRequest(exits.remove(e.thread().uniqueID()));pending.remove(e.thread().uniqueID());}
            return r;
        }
        Map<String,Object> proof(ReferenceType t) throws Exception {
            Map<String,Object> record=completed.get(t.classObject().uniqueID());
            if(record==null)return null;
            remember(t);
            if(definitions.size()>4096)throw new IllegalStateException("generation definition bound");
            return Map.of("record",record,"definitions",new LinkedHashMap<>(definitions));
        }
    }
    private final Generation generation=new Generation();

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
        return Map.of("class", type.name(), "method", method.name(), "signature", method.signature(), "line", location.lineNumber(),
                      "code_index", location.codeIndex(), "method_sha256", methodHash,
                      "constant_pool_sha256", poolHash, "loader", loader, "definition_id", id);
    }
    private List<Map<String,Object>> frames(ThreadReference thread) throws Exception {
        List<Map<String,Object>> result = new ArrayList<>();
        for (StackFrame frame : thread.frames()) result.add(location(frame.location()));
        return result;
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
        if(generation.selected(event.location().method())) {
            emit(new LinkedHashMap<>(Map.of("kind","generation-entry","record",generation.enter(vm,event))),false);return;
        }
        ThreadReference thread = event.thread(); Method method = event.location().method();
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
    private void failure(ExceptionEvent event) throws Exception {
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
        for (String type : observedTypes) {
            ClassPrepareRequest request = vm.eventRequestManager().createClassPrepareRequest();
            request.addClassFilter(type); request.setSuspendPolicy(EventRequest.SUSPEND_ALL); request.enable();
        }
        for (ReferenceType type : vm.allClasses()) configure(type);
        ExceptionRequest exceptions = vm.eventRequestManager().createExceptionRequest(null, true, true);
        exceptions.setSuspendPolicy(EventRequest.SUSPEND_ALL); exceptions.enable();
        emit(new LinkedHashMap<>(Map.of("kind", "ready", "vm_version", vm.version())), false);
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
        if (args.length != 2) throw new IllegalArgumentException("host and port required");
        new PostingObserver().run(args[0], args[1]);
    }
}
