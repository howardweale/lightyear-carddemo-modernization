import java.lang.invoke.*;
import java.nio.file.*;
import java.util.function.IntUnaryOperator;

/** Public synthetic workload. No application data, database, or native candidate. */
public final class AlternativesTarget {
    public static volatile int sink;
    public static int identity(int value) { return value; }
    public static final class Bytes { public static int value() { return 7; } }
    static final class Loader extends ClassLoader {
        Class<?> define(byte[] bytes) { return defineClass(null, bytes, 0, bytes.length); }
    }
    public static void main(String[] args) throws Throwable {
        int iterations=Integer.parseInt(args[0]);
        byte[] bytes=Files.readAllBytes(Path.of(args[1]));
        MethodHandles.Lookup lookup=MethodHandles.lookup();
        MethodHandle target=lookup.findStatic(AlternativesTarget.class,"identity",MethodType.methodType(int.class,int.class));
        IntUnaryOperator cached = AlternativesTarget::identity;
        for(int i=0;i<iterations;i++) {
            sink=cached.applyAsInt(i);
            CallSite site=LambdaMetafactory.metafactory(lookup,"applyAsInt",MethodType.methodType(IntUnaryOperator.class),
                MethodType.methodType(int.class,int.class),target,MethodType.methodType(int.class,int.class));
            sink=((IntUnaryOperator)site.getTarget().invokeExact()).applyAsInt(i);
            MethodHandle spread=target;
            for(int arity=0;arity<(i%12);arity++) spread=MethodHandles.dropArguments(spread,0,Object.class);
            Object[] values=new Object[i%12+1]; values[values.length-1]=i;
            sink=(Integer)spread.invokeWithArguments(values);
            lookup.defineHiddenClass(bytes,false).lookupClass();
            new Loader().define(bytes);
        }
        System.out.println("fixture-complete iterations="+iterations+" sink="+sink);
    }
}
