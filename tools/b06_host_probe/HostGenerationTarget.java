import java.lang.invoke.*;
import java.util.function.*;

/** Public roles only: never an iDempiere candidate or a model invocation. */
public final class HostGenerationTarget {
    public static volatile int sink;
    static final class Candidate {
        static int target(int value) { sink=value; return value; }
        static IntUnaryOperator factory() { return value -> target(value); }
    }
    static final class Support {
        void target() { sink=2; }
        Runnable factory() { return () -> target(); }
    }
    static final class Outside {
        static void target() { sink=3; }
        static Runnable factory() { return Outside::target; }
    }
    public static void main(String[] args) throws Throwable {
        Candidate.factory().applyAsInt(1);
        new Support().factory().run();
        Outside.factory().run();
        MethodHandle handle=MethodHandles.lookup().findStatic(Candidate.class,"target",MethodType.methodType(int.class,int.class));
        sink=(int)handle.invokeExact(4);
        sink=(Integer)handle.invokeWithArguments(5);
        HostPoolTarget.main(args);
    }
}
