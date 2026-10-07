import java.util.*;
import org.junit.platform.engine.*;
import org.junit.platform.engine.support.descriptor.AbstractTestDescriptor;
import org.junit.platform.engine.support.hierarchical.*;

/** Public offline fixture: no application, candidate, database or model execution. */
public final class HostPoolTarget {
    public static volatile int marker;
    public static void checkpoint(int phase) { marker = phase; }
    static final class Root extends AbstractTestDescriptor implements Node<EngineExecutionContext> {
        Root() { super(UniqueId.forEngine("offline-pool-probe"), "public empty root"); }
        public Type getType() { return Type.CONTAINER; }
    }
    static final class Engine extends HierarchicalTestEngine<EngineExecutionContext> {
        public String getId() { return "offline-pool-probe"; }
        public TestDescriptor discover(EngineDiscoveryRequest request, UniqueId id) { return new Root(); }
        protected EngineExecutionContext createExecutionContext(ExecutionRequest request) { return new EngineExecutionContext() {}; }
        public ThrowableCollector.Factory link() { return createThrowableCollectorFactory(null); }
    }
    public static void main(String[] args) throws Exception {
        Class.forName("org.junit.platform.engine.support.hierarchical.HierarchicalTestEngine");
        checkpoint(0);
        Engine engine = new Engine();
        checkpoint(1);
        ThrowableCollector.Factory factory = engine.link();
        checkpoint(2);
        factory.create();
        checkpoint(3);
        ConfigurationParameters config = new ConfigurationParameters() {
            public Optional<String> get(String key) { return Optional.empty(); }
            public Optional<Boolean> getBoolean(String key) { return Optional.empty(); }
            public int size() { return 0; }
            public Set<String> keySet() { return Set.of(); }
        };
        engine.execute(new ExecutionRequest(new Root(), EngineExecutionListener.NOOP, config));
        checkpoint(4);
        System.out.println("OFFLINE_POOL_PROBE_FINISHED");
    }
}
