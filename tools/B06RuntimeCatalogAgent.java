import java.lang.instrument.*;
import java.security.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Observation only: returns null for every class; no bytecode rewriting. */
public final class B06RuntimeCatalogAgent {
    private static final Set<String> TARGETS = new HashSet<>(Arrays.asList(
        "org/compiere/acct/Doc", "org/compiere/acct/DocManager", "org/compiere/model/PO", "org/compiere/util/DB",
        "org/junit/platform/engine/support/hierarchical/NodeTestTask",
        "org/junit/platform/launcher/core/ExecutionListenerAdapter"));
    public static void premain(String destination, Instrumentation instrumentation) throws Exception {
        final Path root = Paths.get(destination);
        Files.createDirectories(root);
        instrumentation.addTransformer(new ClassFileTransformer() {
            public synchronized byte[] transform(ClassLoader loader, String name, Class<?> redef,
                                                  ProtectionDomain domain, byte[] bytes) {
                if (!TARGETS.contains(name)) return null;
                try {
                    StringBuilder hex = new StringBuilder();
                    for (byte b : MessageDigest.getInstance("SHA-256").digest(bytes)) hex.append(String.format("%02x", b & 255));
                    String sha = hex.toString();
                    Path blob = root.resolve(sha+".class");
                    if (!Files.exists(blob)) Files.write(blob, bytes, StandardOpenOption.CREATE_NEW);
                    String origin = domain == null || domain.getCodeSource() == null ? "unavailable" : domain.getCodeSource().getLocation().toString();
                    String line = name + "\t" + sha + "\t" + origin + "\t" + String.valueOf(loader).replace('\n',' ') + "\n";
                    Files.write(root.resolve("loaded.tsv"), line.getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                } catch (Exception e) {
                    // Failure must make acceptance impossible, not disappear in instrumentation.
                    try { Files.write(root.resolve("FAILED"), e.getClass().getName().getBytes(StandardCharsets.UTF_8)); }
                    catch (Exception ignored) { Runtime.getRuntime().halt(71); }
                }
                return null;
            }
        });
    }
}
