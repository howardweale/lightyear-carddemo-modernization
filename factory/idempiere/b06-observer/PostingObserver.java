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
    private final Map<String, String> code = new HashMap<>();
    private final Set<String> configured = new HashSet<>();
    private VirtualMachine vm;
    private long sequence = 0;
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
        String identity = type.name() + "." + method.name() + method.signature();
        String cacheKey = type.classLoader() == null ? "bootstrap:" + identity : type.classLoader().uniqueID() + ":" + identity;
        if (!code.containsKey(cacheKey)) code.put(cacheKey, method.isNative() || method.isAbstract() ? "unavailable" : hash(method.bytecodes()));
        return Map.of("class", type.name(), "method", method.name(), "signature", method.signature(), "line", location.lineNumber(),
                      "code_index", location.codeIndex(), "method_sha256", code.get(cacheKey),
                      "constant_pool_sha256", hash(type.constantPool()), "loader", cacheKey.split(":", 2)[0]);
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
        if (!TYPES.contains(type.name()) || !configured.add(type.name() + ":" + type.classLoader())) return;
        for (Method method : type.methods()) if (selected(method)) {
            BreakpointRequest request = vm.eventRequestManager().createBreakpointRequest(method.location());
            request.setSuspendPolicy(EventRequest.SUSPEND_ALL); request.enable();
        }
    }
    private void entry(BreakpointEvent event) throws Exception {
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
        for (String type : TYPES) {
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
                    emit(new LinkedHashMap<>(Map.of("kind", "vm-death")), false); running = false;
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
