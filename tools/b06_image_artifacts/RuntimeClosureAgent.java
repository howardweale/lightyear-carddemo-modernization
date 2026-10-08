import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Prospective no-candidate launch probe. Output is NOT an admission signature. */
public final class RuntimeClosureAgent {
  static final Set<Integer> RESOLVED=Set.of(4,8,16,32);
  static String q(String v) {return "\""+v.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r")+"\"";}
  static Object call(Class<?> api,Object value,String method) throws Exception {return api.getMethod(method).invoke(value);}
  public static void premain(String destination,Instrumentation instrumentation) {
    if(destination==null || destination.isBlank())throw new IllegalArgumentException("fresh output path required");
    Thread probe=new Thread(()->{
      long until=System.nanoTime()+120_000_000_000L;
      try {
        while(System.nanoTime()<until) {
          Class<?>[] loaded=instrumentation.getAllLoadedClasses();
          Set<String> names=new HashSet<>();for(Class<?> type:loaded)names.add(type.getName());
          // Do not capture the early system-bundle-only startup state.
          if(!names.contains("org.junit.platform.engine.support.hierarchical.NodeTestTask") ||
             !names.contains("org.junit.platform.launcher.core.ExecutionListenerAdapter")) {Thread.sleep(50);continue;}
          for(Class<?> util:loaded) if(util.getName().equals("org.osgi.framework.FrameworkUtil")) {
            Class<?> bundle=Class.forName("org.osgi.framework.Bundle",false,util.getClassLoader());
            Class<?> context=Class.forName("org.osgi.framework.BundleContext",false,util.getClassLoader());
            Method get=util.getMethod("getBundle",Class.class);
            for(Class<?> c:loaded) {
              Object b=get.invoke(null,c);if(b==null)continue;
              Object ctx=call(bundle,b,"getBundleContext");if(ctx==null)continue;
              Object[] bundles=(Object[])context.getMethod("getBundles").invoke(ctx);
              List<String> rows=new ArrayList<>();boolean ready=true;String framework=null;
              for(Object item:bundles) {
                long id=((Number)call(bundle,item,"getBundleId")).longValue();
                int state=((Number)call(bundle,item,"getState")).intValue();
                String location=String.valueOf(call(bundle,item,"getLocation"));
                if(id==0) {if(state!=32)ready=false; }
                else if(state!=2 && !RESOLVED.contains(state))throw new IllegalStateException("unknown bundle state");
                rows.add("{\"id\":"+id+",\"state\":"+state+",\"location\":"+q(location)+",\"symbolic_name\":"+q(String.valueOf(call(bundle,item,"getSymbolicName")))+"}");
              }
              if(!ready)continue;
              // Identify the framework's actual loaded defining JAR, not osgi.bundles.
              Class<?> impl=ctx.getClass();
              if(impl.getProtectionDomain().getCodeSource()==null)throw new IllegalStateException("framework code source absent");
              framework=impl.getProtectionDomain().getCodeSource().getLocation().toExternalForm();
              ProcessHandle.Info process=ProcessHandle.current().info();
              List<String> command=new ArrayList<>();command.add(process.command().orElseThrow());
              command.addAll(Arrays.asList(process.arguments().orElseThrow()));
              String fork=command.stream().map(RuntimeClosureAgent::q).reduce((a,v)->a+","+v).orElseThrow();
              String json="{\"configuration_url\":"+q(System.getProperty("osgi.configuration.area",""))+",\"schema\":\"b06-runtime-launch-observation/2\",\"bundles\":["+String.join(",",rows)+"],\"framework_url\":"+q(framework)+",\"java_class_path\":"+q(System.getProperty("java.class.path"))+",\"java_home\":"+q(System.getProperty("java.home"))+",\"install_area\":"+q(System.getProperty("osgi.install.area",""))+",\"fork_command\":["+fork+"]}";
              Files.writeString(Path.of(destination),json,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
              return;
            }
          }
          Thread.sleep(50);
        }
        throw new IllegalStateException("no running Equinox runtime with loaded test classes within 120 seconds");
      } catch(Throwable e) {System.err.println("B06 runtime closure probe failed: "+e.getClass().getName());}
    },"b06-runtime-closure-probe");
    probe.setDaemon(true);probe.start();
  }
}
