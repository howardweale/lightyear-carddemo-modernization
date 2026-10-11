package lightyear.observer;

import com.sun.jdi.ReferenceType;
import com.sun.jdi.VirtualMachine;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.security.MessageDigest;
import java.util.*;

/**
 * Engineering-only adapter for the pinned Corretto JDI implementation.
 *
 * This is NOT a generally supported JDI cache API. The observer must never call
 * allClasses (including indirect enumeration APIs) and must never redefine
 * classes. Exact-name queries remain JDWP queries because retrievedAllTypes is
 * false for the entire connection. We never change that flag. Cache ownership,
 * prepared-mirror identity, and the two-cache invariant are checked before edits.
 * Active/requested types must be pinned by the caller. Qualification is prohibited.
 */
public final class BoundedJdiMirrors {
    public static final int LOW_WATER = 512, HIGH_WATER = 1024;
    public static final String POLICY = "corretto21-jdi-mirrors-v1";
    private static final Map<String,String> PINS = Map.of(
        "VirtualMachineImpl", "8796f85b3a7181d6db9e79831f67b8606345482e4dbb739e0f4a0ed789a4e10a",
        "ReferenceTypeImpl", "53ad89c11c3b782d6342f9fc3ff65313a99aa0b499c39c4e3d1cf307cc41a718",
        "MethodImpl", "2fafad3289570b560a24bd2733ea2c93fcacf78ebbcbcf227999f4b543273b5b",
        "EventSetImpl", "8ba1eb2830d3bc480220634b508d23929bd8a098d746b288b4d856c60c0ecce8",
        "InternalEventHandler", "5e4e8a24662ccfe16bd1b895c0896b62d10f874ccd5627aba47193bf645fcf43",
        "ClassTypeImpl", "ff54285e8868622c148d0bced1ecca42983030da6c7a7a3b29ccdf8a42b669b7",
        "InterfaceTypeImpl", "ae52d68eac3adbc8dc479d2a02c2b5ca2b80280ba0b3b71cf1ec94aff56fec44");
    private final VirtualMachine vm;
    private final Field byId, bySignature, allTypes, prepared;
    private final Set<ReferenceType> permanentPins = new HashSet<>();
    private long evictions, sweeps;
    private int current, peak, retainedUnprepared;

    public BoundedJdiMirrors(VirtualMachine vm) throws Exception {
        if (!vm.getClass().getName().equals("com.sun.tools.jdi.VirtualMachineImpl"))
            throw new IllegalStateException("unsupported-jdi-mirror-implementation");
        for (var item : PINS.entrySet()) {
            Class<?> type = Class.forName("com.sun.tools.jdi." + item.getKey(), false, vm.getClass().getClassLoader());
            String resource = "/com/sun/tools/jdi/" + item.getKey() + ".class";
            verifyClass(type, resource, item.getValue());
        }
        this.vm = vm;
        byId = field(vm.getClass(), "typesByID");
        bySignature = field(vm.getClass(), "typesBySignature");
        allTypes = field(vm.getClass(), "retrievedAllTypes");
        prepared = field(Class.forName("com.sun.tools.jdi.ReferenceTypeImpl"), "isPrepared");
        synchronized (vm) { checkQueryMode(); }
    }
    private static void verifyClass(Class<?> type, String resource, String expected) throws Exception {
        try (InputStream in = type.getResourceAsStream(resource)) {
            if (in == null || !HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(in.readAllBytes())).equals(expected))
                throw new IllegalStateException("unsupported-jdi-mirror-bytecode:" + type.getSimpleName());
        }
    }
    private static Field field(Class<?> type, String name) throws Exception {
        Field f = type.getDeclaredField(name);
        if (!f.trySetAccessible()) throw new IllegalStateException("jdi-mirror-adapter-opens-required");
        return f;
    }
    private void checkQueryMode() throws Exception {
        if (allTypes.getBoolean(vm)) throw new IllegalStateException("jdi-full-enumeration-prohibited");
    }
    public void pin(ReferenceType type) throws Exception {
        synchronized (vm) {
            checkQueryMode();
            if (!type.virtualMachine().equals(vm)) throw new IllegalArgumentException("foreign-jdi-mirror");
            if (!permanentPins.contains(type) && permanentPins.size() >= HIGH_WATER)
                throw new IllegalStateException("jdi-mirror-pins-limit");
            permanentPins.add(type);
        }
    }
    /** Call only after handling the complete EventSet and before its resume. */
    @SuppressWarnings("unchecked")
    public Map<String,Object> prune(Collection<? extends ReferenceType> active) throws Exception {
        synchronized (vm) {
            checkQueryMode();
            Map<Long,ReferenceType> ids = (Map<Long,ReferenceType>) byId.get(vm);
            Set<ReferenceType> signatures = (Set<ReferenceType>) bySignature.get(vm);
            if (ids == null && signatures == null) return telemetryLocked();
            if (ids == null || signatures == null || ids.size() != signatures.size())
                throw new IllegalStateException("jdi-mirror-cache-inconsistent");
            Set<ReferenceType> identity = Collections.newSetFromMap(new IdentityHashMap<>());
            identity.addAll(signatures);
            if (!identity.containsAll(ids.values())) throw new IllegalStateException("jdi-mirror-cache-inconsistent");
            Set<ReferenceType> keep = new HashSet<>(permanentPins);
            for (ReferenceType type : active) {
                if (!type.virtualMachine().equals(vm)) throw new IllegalArgumentException("foreign-jdi-mirror");
                keep.add(type);
            }
            current = ids.size(); peak = Math.max(peak, current);
            retainedUnprepared = 0;
            for (ReferenceType type : ids.values()) {
                // Do not query target state while holding the JDI monitor. False
                // may be conservative during internal prepare dispatch; safe to pin.
                if (!prepared.getBoolean(type)) { keep.add(type); retainedUnprepared++; }
            }
            long pinnedPresent = ids.values().stream().filter(keep::contains).count();
            if (pinnedPresent > HIGH_WATER || keep.size() > HIGH_WATER)
                throw new IllegalStateException("jdi-mirror-pins-limit");
            if (current > HIGH_WATER) {
                int target = Math.max(LOW_WATER, (int)pinnedPresent);
                int remaining = current;
                Iterator<Map.Entry<Long,ReferenceType>> it = ids.entrySet().iterator();
                while (it.hasNext() && remaining > target) {
                    ReferenceType type = it.next().getValue();
                    if (keep.contains(type)) continue;
                    if (!signatures.remove(type)) throw new IllegalStateException("jdi-mirror-cache-inconsistent");
                    it.remove(); remaining--; evictions++;
                }
                current = remaining; sweeps++;
                if (current > HIGH_WATER || current != signatures.size())
                    throw new IllegalStateException("jdi-mirror-cache-bound-failed");
            }
            return telemetryLocked();
        }
    }
    public Map<String,Object> telemetry() { synchronized (vm) { return telemetryLocked(); } }
    private Map<String,Object> telemetryLocked() {
        return Map.of("jdi_mirror_policy",POLICY,"jdi_mirror_count",current,
            "jdi_mirror_peak_before_prune",peak,"jdi_mirror_evictions",evictions,
            "jdi_mirror_sweeps",sweeps,"jdi_mirror_unprepared",retainedUnprepared,
            "jdi_mirror_pins",permanentPins.size(),"jdi_mirror_limit",HIGH_WATER);
    }
}
