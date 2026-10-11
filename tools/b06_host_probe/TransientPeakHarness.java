import java.io.*;
import java.lang.management.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Public synthetic peak test, invoking the actual production streaming writer. */
public final class TransientPeakHarness {
    static final Runtime RUNTIME=Runtime.getRuntime();
    static final List<byte[]> BALLAST=new ArrayList<>();
    static long used() { return RUNTIME.totalMemory()-RUNTIME.freeMemory(); }
    static long peak;
    static class SampledOutput extends FilterOutputStream {
        long bytes;
        SampledOutput(OutputStream output) { super(output); }
        public void write(int value) throws IOException { out.write(value);bytes++;peak=Math.max(peak,used()); }
        public void write(byte[] value,int offset,int length) throws IOException {out.write(value,offset,length);bytes+=length;peak=Math.max(peak,used());}
    }
    public static void main(String[] args) throws Exception {
        if(RUNTIME.maxMemory()!=192L*1024*1024)throw new IllegalArgumentException("requires-exact-192MiB-heap");
        byte[] definition=new byte[1024*1024];for(int i=0;i<definition.length;i++)definition[i]=(byte)(i%251);
        Map<String,Object> nodes=new LinkedHashMap<>();
        for(int i=0;i<4096;i++) {Map<String,Object> node=new LinkedHashMap<>();node.put("type","public.synthetic.Node");node.put("index",i);node.put("next",(i+1)%4096);nodes.put(Integer.toString(i),node);}
        Map<String,Object> graph=new LinkedHashMap<>();graph.put("root","0");graph.put("nodes",nodes);
        Map<String,Object> entry=new LinkedHashMap<>();entry.put("definition_input_base64",definition);entry.put("class_data_graph",graph);
        Class<?> observer=Class.forName("lightyear.observer.PostingObserver");
        Method serializer=observer.getDeclaredMethod("writeJson",Writer.class,Object.class,boolean.class);serializer.setAccessible(true);
        serializer.invoke(null,Writer.nullWriter(),Map.of("warmup",new byte[768]),false);
        var allocated=(com.sun.management.ThreadMXBean)ManagementFactory.getThreadMXBean();
        if(!allocated.isThreadAllocatedMemorySupported())throw new IllegalStateException("allocation-meter-unavailable");
        allocated.setThreadAllocatedMemoryEnabled(true);long thread=Thread.currentThread().threadId();
        MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try(var file=Files.newOutputStream(Path.of(args[0]),StandardOpenOption.CREATE_NEW);
            var hashed=new java.security.DigestOutputStream(file,digest);
            var sampled=new SampledOutput(hashed);
            var writer=new OutputStreamWriter(sampled,StandardCharsets.UTF_8)) {
            System.gc();long target=(RUNTIME.maxMemory()*85+99)/100;
            while(used()<target) {byte[] block=new byte[32768];block[0]=1;BALLAST.add(block);}
            System.gc();
            while(used()<target) {byte[] block=new byte[32768];block[0]=1;BALLAST.add(block);}
            long before=used();peak=before;long allocatedBefore=allocated.getThreadAllocatedBytes(thread);long started=System.nanoTime();
            serializer.invoke(null,writer,entry,false);writer.flush();
            long allocatedBytes=allocated.getThreadAllocatedBytes(thread)-allocatedBefore;long elapsed=System.nanoTime()-started;peak=Math.max(peak,used());
            System.out.println("{\"schema\":\"b06-transient-peak/1\",\"heap_max_bytes\":"+RUNTIME.maxMemory()+",\"heap_before_bytes\":"+before+",\"sampled_peak_bytes\":"+peak+",\"serialization_allocated_bytes\":"+allocatedBytes+",\"allocation_upper_bound_bytes\":"+(before+allocatedBytes)+",\"output_bytes\":"+sampled.bytes+",\"elapsed_nanoseconds\":"+elapsed+",\"definition_bytes\":1048576,\"graph_nodes\":4096,\"oom\":false,\"sha256\":\""+HexFormat.of().formatHex(digest.digest())+"\"}");
            // Keep both resident input and ballast reachable through the measured operation.
            java.lang.ref.Reference.reachabilityFence(entry);java.lang.ref.Reference.reachabilityFence(BALLAST);
        }
    }
}
