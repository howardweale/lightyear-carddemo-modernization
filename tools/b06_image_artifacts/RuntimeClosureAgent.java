import java.lang.instrument.*;
import java.security.*;
import java.net.URI;
import java.io.ByteArrayOutputStream;
import java.util.zip.*;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Prospective no-candidate launch probe. Output is NOT an admission signature. */
public final class RuntimeClosureAgent {
  static final Set<Integer> RESOLVED=Set.of(4,8,16,32);
  static String q(String v) {return "\""+v.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r")+"\"";}
  static Object call(Class<?> api,Object value,String method) throws Exception {return api.getMethod(method).invoke(value);}
  static byte[] applicationBytes(Path root) throws Exception {
    if(Files.isSymbolicLink(root))throw new IllegalStateException("application symlink");
    if(Files.isRegularFile(root)) {
      if(Files.size(root)>1073741824L)throw new IllegalStateException("application archive bound");
      return Files.readAllBytes(root);
    }
    if(!Files.isDirectory(root))throw new IllegalStateException("application bundle absent");
    ByteArrayOutputStream bytes=new ByteArrayOutputStream();long total=0;
    try(ZipOutputStream zip=new ZipOutputStream(bytes);var walk=Files.walk(root)) {
      var paths=walk.filter(p->!p.equals(root)).sorted().toList();
      if(paths.size()>100000)throw new IllegalStateException("application entries bound");
      for(Path p:paths) {
        if(Files.isSymbolicLink(p))throw new IllegalStateException("application symlink");
        boolean directory=Files.isDirectory(p);
        String name=root.relativize(p).toString().replace('\\','/')+(directory?"/":"");
        ZipEntry entry=new ZipEntry(name);entry.setTime(0);zip.putNextEntry(entry);
        if(!directory) {
          long size=Files.size(p);total+=size;
          if(total>1073741824L || size>134217728L)throw new IllegalStateException("application bytes bound");
          var before=Files.getLastModifiedTime(p);byte[] raw=Files.readAllBytes(p);
          if(raw.length!=size || !before.equals(Files.getLastModifiedTime(p)))throw new IllegalStateException("application changed during capture");
          zip.write(raw);
        }
        zip.closeEntry();
      }
    }
    return bytes.toByteArray();
  }
  public static void premain(String destination,Instrumentation instrumentation) {
    if(destination==null || destination.isBlank())throw new IllegalArgumentException("fresh output path required");
    Path catalogue=Path.of(destination).resolveSibling("runtime-catalogue.tsv");
    instrumentation.addTransformer(new ClassFileTransformer() {
      public synchronized byte[] transform(ClassLoader loader,String name,Class<?> redef,ProtectionDomain domain,byte[] bytes) {
        try {
          String origin=domain==null || domain.getCodeSource()==null ? "unavailable" : domain.getCodeSource().getLocation().toExternalForm();
          Files.writeString(catalogue,name+"\t"+origin+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(Exception e) {Runtime.getRuntime().halt(72);}
        return null;
      }
    });
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
              List<String> classes=new ArrayList<>();
              for(Class<?> type:loaded) {
                Object owner=get.invoke(null,type);
                if(owner!=null)classes.add("{\"name\":"+q(type.getName())+",\"bundle_id\":"+call(bundle,owner,"getBundleId")+"}");
              }
              for(Object item:bundles) {
                long id=((Number)call(bundle,item,"getBundleId")).longValue();
                int state=((Number)call(bundle,item,"getState")).intValue();
                String location=String.valueOf(call(bundle,item,"getLocation"));
                if(id==0) {if(state!=32)ready=false; }
                else if(state!=2 && !RESOLVED.contains(state))throw new IllegalStateException("unknown bundle state");
                String symbolic=String.valueOf(call(bundle,item,"getSymbolicName"));
                String version=String.valueOf(call(bundle,item,"getVersion"));
                Dictionary<?,?> headers=(Dictionary<?,?>)bundle.getMethod("getHeaders",String.class).invoke(item,"");
                boolean source=headers.get("Eclipse-SourceBundle")!=null;
                String copy="null", applicationCopy="null";
                if(id!=0) {
                  String url=location.replaceFirst("^initial@","").replaceFirst("^reference:","");
                  URI uri=URI.create(url);
                  if(!"file".equals(uri.getScheme()))throw new IllegalStateException("non-file bundle location");
                  Path install=Path.of(URI.create(System.getProperty("osgi.install.area")));
                  Path original=uri.isOpaque()?Path.of(uri.getSchemeSpecificPart()):Path.of(uri);
                  if(!original.isAbsolute())original=install.resolve(original);
                  original=original.normalize();
                  if(original.startsWith(Path.of("/application"))) {
                    byte[] raw=applicationBytes(original);
                    Path dest=Path.of(destination).resolveSibling("runtime-application").resolve(id+".jar");
                    Files.createDirectories(dest.getParent());Files.write(dest,raw,StandardOpenOption.CREATE_NEW);
                    String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));
                    String kind=Files.isDirectory(original)?"folder-archive":"jar";
                    applicationCopy="{\"path\":"+q(dest.toString())+",\"sha256\":"+q(sha)+",\"bytes\":"+raw.length+",\"kind\":"+q(kind)+"}";
                  }
                  Path tmp=Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath().normalize();
                  if(original.startsWith(tmp)) {
                    if(Files.isSymbolicLink(original) || !Files.isRegularFile(original))throw new IllegalStateException("transient bundle file required");
                    if(Files.size(original)>134217728)throw new IllegalStateException("transient bundle bound");
                    byte[] raw=Files.readAllBytes(original);
                    if(raw.length>134217728)throw new IllegalStateException("transient bundle bound");
                    Path dest=Path.of(destination).resolveSibling("runtime-transient").resolve(id+".jar");
                    Files.createDirectories(dest.getParent());Files.write(dest,raw,StandardOpenOption.CREATE_NEW);
                    String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));
                    copy="{\"path\":"+q(dest.toString())+",\"sha256\":"+q(sha)+",\"bytes\":"+raw.length+"}";
                  }
                }
                rows.add("{\"id\":"+id+",\"state\":"+state+",\"location\":"+q(location)+",\"symbolic_name\":"+q(symbolic)+",\"version\":"+q(version)+",\"eclipse_source_bundle\":"+source+",\"application_copy\":"+applicationCopy+",\"preserved_copy\":"+copy+"}");
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
              String json="{\"configuration_url\":"+q(System.getProperty("osgi.configuration.area",""))+",\"schema\":\"b06-runtime-launch-observation/4\",\"bundles\":["+String.join(",",rows)+"],\"framework_url\":"+q(framework)+",\"java_class_path\":"+q(System.getProperty("java.class.path"))+",\"java_home\":"+q(System.getProperty("java.home"))+",\"install_area\":"+q(System.getProperty("osgi.install.area",""))+",\"java_tmpdir\":"+q(System.getProperty("java.io.tmpdir"))+",\"loaded_bundle_classes\":["+String.join(",",classes)+"],\"fork_command\":["+fork+"]}";
              Files.writeString(Path.of(destination),json,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
              return;
            }
          }
          Thread.sleep(50);
        }
        throw new IllegalStateException("no running Equinox runtime with loaded test classes within 120 seconds");
      } catch(Throwable e) {System.err.println("B06 runtime closure probe failed: "+e.getClass().getName());}
    },"b06-runtime-closure-probe");
    probe.setDaemon(false);probe.start();
  }
}
