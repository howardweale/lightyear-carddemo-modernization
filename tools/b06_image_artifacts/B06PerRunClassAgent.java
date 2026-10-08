import java.lang.instrument.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.HexFormat;

/** Practice only: records bytes actually defined; never transforms them. */
public final class B06PerRunClassAgent {
 static String q(String s) { return "\""+s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r")+"\""; }
 public static void premain(String argument,Instrumentation instrumentation) {
  Path output=Path.of(argument);
  instrumentation.addTransformer(new ClassFileTransformer() {
   public synchronized byte[] transform(ClassLoader loader,String name,Class<?> redef,ProtectionDomain domain,byte[] bytes) {
    if (!"org/idempiere/test/B06RuntimeCatalogTest".equals(name)) return null;
    try {
     if(redef!=null || loader==null || domain==null || domain.getCodeSource()==null)throw new IllegalStateException("unbound probe definition");
     String origin=domain.getCodeSource().getLocation().toExternalForm();
     String identity=loader.getClass().getName()+"@"+Integer.toHexString(System.identityHashCode(loader));
     String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
     String json="{\"schema\":\"b06-practice-class-observation/1\",\"name\":"+q(name)+",\"origin\":"+q(origin)+",\"loader\":"+q(identity)+",\"bytes\":"+bytes.length+",\"sha256\":"+q(hash)+"}";
     Files.writeString(output,json,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
    } catch(Exception error) {
     try {Files.writeString(output.resolveSibling("per-run-class-error.json"),"{\"error\":"+q(error.toString())+"}",StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);}catch(Exception ignored) {System.err.println("B06 per-run class observation failed: "+error);}
    }
    return null;
   }
  });
 }
}
