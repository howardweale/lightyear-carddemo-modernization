import java.io.InputStream;
import java.util.*;
/** Host-only mirror lifecycle fixture; no application or database execution. */
public final class BoundedMirrorsTarget {
    public static final class Payload { public int value(){return 7;} }
    public static Class<?>[] CLASSES;
    private static final List<Class<?>> LIVE = Collections.synchronizedList(new ArrayList<>());
    private static final class Loader extends ClassLoader {
        Loader(){super(null);}
        Class<?> define(byte[] bytes){return defineClass("BoundedMirrorsTarget$Payload",bytes,0,bytes.length);}
    }
    public static void checkpoint(int phase) { if(phase < 0)throw new AssertionError(); }
    public static void main(String[] args) throws Exception {
        byte[] bytes;
        try(InputStream in=BoundedMirrorsTarget.class.getResourceAsStream("/BoundedMirrorsTarget$Payload.class")){bytes=in.readAllBytes();}
        List<Thread> threads=new ArrayList<>();
        for(int t=0;t<4;t++){
            Thread thread=new Thread(()->{try{
                for(int i=0;i<650;i++){
                    Class<?> c=new Loader().define(bytes);c.getDeclaredConstructor().newInstance();LIVE.add(c);
                }
            }catch(Exception e){throw new RuntimeException(e);}});
            threads.add(thread);thread.start();
        }
        for(Thread thread:threads)thread.join();
        CLASSES=LIVE.toArray(Class<?>[]::new);
        checkpoint(1);
        CLASSES=null;LIVE.clear();
        for(int i=0;i<8;i++){System.gc();Thread.sleep(20);}
        Class<?> fresh=new Loader().define(bytes);fresh.getDeclaredConstructor().newInstance();LIVE.add(fresh);
        checkpoint(2);
    }
}
