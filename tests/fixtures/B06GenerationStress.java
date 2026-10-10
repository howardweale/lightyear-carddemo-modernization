package fixture;

import java.lang.invoke.*;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Public host-only fixture; no application, database, container or private inputs. */
public class B06GenerationStress {
    static final AtomicReference<Throwable> failure = new AtomicReference<>();
    static final AtomicInteger completed = new AtomicInteger();
    static volatile long sink;
    public static void target() {}
    static void deep(int depth, int iterations, byte[] bytes, CyclicBarrier barrier) throws Throwable {
        if (depth > 0) { deep(depth - 1, iterations, bytes, barrier); return; }
        var lookup = MethodHandles.lookup();
        var target = lookup.findStatic(B06GenerationStress.class, "target", MethodType.methodType(void.class));
        barrier.await();
        for (int i = 0; i < iterations; i++) {
            // A fresh hidden class and a fresh lambda factory on every worker/iteration.
            var hidden = lookup.defineHiddenClass(bytes, true);
            var getter = hidden.findStatic(hidden.lookupClass(), "value", MethodType.methodType(int.class));
            var adapted = MethodHandles.dropArguments(getter, 0, Object.class)
                .asType(MethodType.methodType(Object.class, Object.class));
            for (int j = 0; j < 40; j++) { Object value = adapted.invokeExact((Object) null); sink = (Integer) value; }
            var site = LambdaMetafactory.metafactory(lookup, "run", MethodType.methodType(Runnable.class),
                MethodType.methodType(void.class), target, MethodType.methodType(void.class));
            ((Runnable) site.getTarget().invokeExact()).run();
            completed.incrementAndGet();
        }
    }
    public static void main(String[] args) throws Throwable {
        int threads = Integer.parseInt(args[0]), iterations = Integer.parseInt(args[1]), depth = Integer.parseInt(args[2]);
        byte[] bytes = Files.readAllBytes(Path.of(args[3]));
        var barrier = new CyclicBarrier(threads);
        Thread[] workers = new Thread[threads];
        for (int i = 0; i < threads; i++) {
            workers[i] = new Thread(() -> {
                try { deep(depth, iterations, bytes, barrier); }
                catch (Throwable t) { failure.compareAndSet(null, t); barrier.reset(); }
            }, "public-stress-worker-" + i);
        }
        for (var worker : workers) worker.start();
        for (var worker : workers) worker.join();
        if (failure.get() != null) throw new AssertionError("worker failure", failure.get());
        if (completed.get() != threads * iterations) throw new AssertionError("incomplete work");
        System.out.println("completed_iterations=" + completed.get());
    }
}
class StressHidden { public static int value() { return 7; } }
