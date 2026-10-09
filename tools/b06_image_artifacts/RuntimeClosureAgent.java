import java.lang.instrument.*;
import java.security.*;
import java.net.URI;
import java.io.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.zip.*;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Prospective no-candidate launch probe. Output is NOT an admission signature. */
public final class RuntimeClosureAgent {
  static final Set<Integer> RESOLVED=Set.of(4,8,16,32);
  static volatile String stage="premain";
  static volatile boolean finished=false;
  static Path output;
  static Thread probe;
  static String hash(Path path) throws Exception {
    MessageDigest digest=MessageDigest.getInstance("SHA-256");
    try(InputStream in=Files.newInputStream(path)) {byte[] b=new byte[65536];int n;while((n=in.read(b))!=-1)digest.update(b,0,n);}
    return HexFormat.of().formatHex(digest.digest());
  }
  static void atomic(Path path,String value) throws Exception {
    Path tmp=Files.createTempFile(path.getParent(),".closure-",".tmp");
    Files.writeString(tmp,value,StandardCharsets.UTF_8);
    if(Files.exists(path))throw new FileAlreadyExistsException(path.toString());
    Files.move(tmp,path,StandardCopyOption.ATOMIC_MOVE);
  }
  static synchronized void failure(Throwable error,String at) {
    try {
      Path path=output.resolveSibling("closure-error.json");
      if(Files.exists(path))return;
      StringWriter stack=new StringWriter();error.printStackTrace(new PrintWriter(stack));
      atomic(path,"{\"schema\":\"b06-closure-error/1\",\"exception_class\":"+q(error.getClass().getName())+",\"message\":"+q(String.valueOf(error.getMessage()))+",\"stack_trace\":"+q(stack.toString())+",\"stage\":"+q(at)+"}");
      if(!Files.exists(output.resolveSibling("closure-complete.json")))
        atomic(output.resolveSibling("closure-complete.json"),"{\"status\":\"failed\",\"error_sha256\":"+q(hash(path))+"}");
    } catch(Throwable recording) {System.err.println("B06 closure error recording failed: "+recording);}
    finally {finished=true;System.err.println("B06 runtime closure probe failed: "+error);}
  }
  static synchronized void complete(String json,Path staging) throws Exception {
    if(finished)throw new IllegalStateException("probe already finalized");
    stage="publish";
    Path destination=output.resolveSibling("runtime-transient");
    if(Files.exists(destination))throw new FileAlreadyExistsException(destination.toString());
    Files.move(staging,destination,StandardCopyOption.ATOMIC_MOVE);
    atomic(output,json);
    atomic(output.resolveSibling("closure-complete.json"),"{\"status\":\"complete\",\"observation_sha256\":"+q(hash(output))+"}");
    finished=true;
  }
  static String q(String v) {
    StringBuilder b=new StringBuilder("\"");
    for(char c:v.toCharArray()) {if(c=='"'||c=='\\')b.append('\\').append(c);else if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}
    return b.append('"').toString();
  }
  static Object call(Class<?> api,Object value,String method) throws Exception {return api.getMethod(method).invoke(value);}
  public static void premain(String destination,Instrumentation instrumentation) {
    if(destination==null || destination.isBlank())throw new IllegalArgumentException("fresh output path required");
    output=Path.of(destination).toAbsolutePath();
    System.setProperty("b06.closure.output",output.toString());
    Runtime.getRuntime().addShutdownHook(new Thread(()->{
      try {if(probe!=null)probe.join(10000);}catch(InterruptedException e){Thread.currentThread().interrupt();}
      if(!finished) {failure(new IllegalStateException("interrupted by JVM exit"),stage);if(probe!=null)probe.interrupt();}
    },"b06-closure-shutdown"));
    Path catalogue=Path.of(destination).resolveSibling("runtime-catalogue.tsv");
    instrumentation.addTransformer(new ClassFileTransformer() {
      public synchronized byte[] transform(ClassLoader loader,String name,Class<?> redef,ProtectionDomain domain,byte[] bytes) {
        try {
          String origin=domain==null || domain.getCodeSource()==null ? "unavailable" : domain.getCodeSource().getLocation().toExternalForm();
          Files.writeString(catalogue,name+"\t"+origin+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(Exception e) {failure(e,"class-catalogue");}
        return null;
      }
    });
    probe=new Thread(()->{
      long until=System.nanoTime()+590_000_000_000L;
      try {
        stage="readiness";
        while(System.nanoTime()<until && !finished) {
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
              // Readiness is settled before creating any copy or capture directory.
              boolean ready=false;
              for(Object item:bundles)if(((Number)call(bundle,item,"getBundleId")).longValue()==0)ready=((Number)call(bundle,item,"getState")).intValue()==32;
              if(!ready)continue;
              stage="transient-capture";
              Path staging=Files.createTempDirectory(output.getParent(),".runtime-transient-");
              List<String> rows=new ArrayList<>();String framework=null;
              List<String> classes=new ArrayList<>();
              for(Class<?> type:loaded) {
                Object owner=get.invoke(null,type);
                if(owner!=null)classes.add("{\"name\":"+q(type.getName())+",\"bundle_id\":"+call(bundle,owner,"getBundleId")+"}");
              }
              for(Object item:bundles) {
                long id=((Number)call(bundle,item,"getBundleId")).longValue();
                int state=((Number)call(bundle,item,"getState")).intValue();
                String location=String.valueOf(call(bundle,item,"getLocation"));
                if(id==0) {if(state!=32)throw new IllegalStateException("system bundle lost readiness"); }
                else if(state!=2 && !RESOLVED.contains(state))throw new IllegalStateException("unknown bundle state");
                String symbolic=String.valueOf(call(bundle,item,"getSymbolicName"));
                String version=String.valueOf(call(bundle,item,"getVersion"));
                Dictionary<?,?> headers=(Dictionary<?,?>)bundle.getMethod("getHeaders",String.class).invoke(item,"");
                boolean source=headers.get("Eclipse-SourceBundle")!=null;
                String copy="null";
                if(id!=0) {
                  String url=location.replaceFirst("^initial@","").replaceFirst("^reference:","");
                  URI uri=URI.create(url);
                  if(!"file".equals(uri.getScheme()))throw new IllegalStateException("non-file bundle location");
                  Path install=Path.of(URI.create(System.getProperty("osgi.install.area")));
                  Path original=uri.isOpaque()?Path.of(uri.getSchemeSpecificPart()):Path.of(uri);
                  if(!original.isAbsolute())original=install.resolve(original);
                  original=original.normalize();
                  Path tmp=Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath().normalize();
                  if(original.startsWith(tmp) || original.startsWith(Path.of("/tmp"))) {
                    if(Files.isSymbolicLink(original) || !Files.isRegularFile(original))throw new IllegalStateException("transient bundle file required");
                    if(Files.size(original)>134217728)throw new IllegalStateException("transient bundle bound");
                    stage="transient-capture:"+id;
                    BasicFileAttributes before=Files.readAttributes(original,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
                    Path dest=staging.resolve(id+".jar");
                    long count=0;
                    try(InputStream in=Files.newInputStream(original);OutputStream out=Files.newOutputStream(dest,StandardOpenOption.CREATE_NEW)) {
                      byte[] buffer=new byte[65536];int n;
                      while((n=in.read(buffer))!=-1) {count+=n;if(count>134217728L)throw new IllegalStateException("transient bundle bound");out.write(buffer,0,n);}
                    }
                    BasicFileAttributes after=Files.readAttributes(original,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
                    if(count!=before.size() || before.size()!=after.size() || !before.lastModifiedTime().equals(after.lastModifiedTime()) || !Objects.equals(before.fileKey(),after.fileKey()))throw new IllegalStateException("transient bundle changed during capture");
                    String sha=hash(dest);
                    copy="{\"path\":"+q(output.resolveSibling("runtime-transient").resolve(id+".jar").toString())+",\"sha256\":"+q(sha)+",\"bytes\":"+count+"}";
                  }
                }
                rows.add("{\"id\":"+id+",\"state\":"+state+",\"location\":"+q(location)+",\"symbolic_name\":"+q(symbolic)+",\"version\":"+q(version)+",\"eclipse_source_bundle\":"+source+",\"preserved_copy\":"+copy+"}");
              }
              stage="process-metadata";
              // Identify the framework's actual loaded defining JAR, not osgi.bundles.
              Class<?> impl=ctx.getClass();
              if(impl.getProtectionDomain().getCodeSource()==null)throw new IllegalStateException("framework code source absent");
              framework=impl.getProtectionDomain().getCodeSource().getLocation().toExternalForm();
              ProcessHandle.Info process=ProcessHandle.current().info();
              List<String> command=new ArrayList<>();command.add(process.command().orElseThrow());
              command.addAll(Arrays.asList(process.arguments().orElseThrow()));
              String fork=command.stream().map(RuntimeClosureAgent::q).reduce((a,v)->a+","+v).orElseThrow();
              String json="{\"configuration_url\":"+q(System.getProperty("osgi.configuration.area",""))+",\"schema\":\"b06-runtime-launch-observation/5\",\"bundles\":["+String.join(",",rows)+"],\"framework_url\":"+q(framework)+",\"java_class_path\":"+q(System.getProperty("java.class.path"))+",\"java_home\":"+q(System.getProperty("java.home"))+",\"install_area\":"+q(System.getProperty("osgi.install.area",""))+",\"osgi_dev\":"+q(System.getProperty("osgi.dev",""))+",\"java_tmpdir\":"+q(System.getProperty("java.io.tmpdir"))+",\"loaded_bundle_classes\":["+String.join(",",classes)+"],\"fork_command\":["+fork+"]}";
              complete(json,staging);
              return;
            }
          }
          Thread.sleep(50);
        }
        throw new IllegalStateException("no running Equinox runtime with loaded test classes within 590 seconds");
      } catch(Throwable e) {failure(e,stage);}
    },"b06-runtime-closure-probe");
    probe.setDaemon(false);probe.start();
  }
}
