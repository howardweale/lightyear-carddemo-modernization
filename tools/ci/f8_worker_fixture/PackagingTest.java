package ai.lightyear.worker;
import ai.lightyear.carddemo.*;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermission;
import java.net.*;
import java.io.IOException;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import tools.jackson.databind.json.JsonMapper;

/** Infrastructure fixture only: no authorization candidate or screen behavior. */
public class PackagingTest {
    @Test void sharedUtilities() throws Exception {
        assertEquals("ABC", new String(Commarea.encode("ABC"), Commarea.EBCDIC));
        assertThrows(IllegalArgumentException.class, () -> TypedRecords.identifier("x;drop"));
        assertThrows(ClassNotFoundException.class, () -> Class.forName("ai.lightyear.carddemo.SourceEdits"));
        assertThrows(ClassNotFoundException.class, () -> Class.forName("ai.lightyear.carddemo.AuthorizationListService"));
        assertFalse(Arrays.stream(AuthorizationRecords.class.getDeclaredMethods()).anyMatch(m -> m.getName().equals("load")));
        assertEquals(List.class, ScreenFrame.class.getField("trace").getGenericType());
        var json = JsonMapper.builder().build();
        var screen = "{\"program\":\"FIXTURE\",\"transaction\":\"TEST\",\"model\":{\"maps\":[{\"fields\":[]}]}}";
        var directory = Files.createTempDirectory("public-worker-fixture");
        var bindings = directory.resolve("bindings.json"); var plan = directory.resolve("plan.json");
        Files.writeString(bindings, "{\"schema\":\"carddemo-web-bindings/1\",\"upstream_commit\":\"fixture\",\"programs\":{\"FIXTURE\":{\"headers\":[]}},\"screens\":[" + String.join(",", Collections.nCopies(6, screen)) + "]}");
        Files.writeString(plan, "{\"schema\":\"carddemo-data-plan/1\",\"upstream\":{\"commit\":\"fixture\"}}");
        assertTrue(new ScreenFrame(new Bindings(bindings, plan, json), "FIXTURE").trace.isEmpty());
    }
    @Test void isolatedBuild() throws Exception {
        if (!Boolean.getBoolean("f8.isolated")) return;
        assertThrows(IOException.class, () -> Files.writeString(Path.of("/workspace/write-probe"), "denied"));
        assertThrows(IOException.class, () -> Files.writeString(Path.of("/root-write-probe"), "denied"));
        assertThrows(IOException.class, () -> Files.readString(Path.of(System.getProperty("f8.private.path"))));
        var mounts = Files.readAllLines(Path.of("/proc/mounts"));
        for (var target : List.of("/", "/workspace")) assertTrue(mounts.stream().anyMatch(line -> { var parts = line.split(" "); return parts[1].equals(target) && Arrays.asList(parts[3].split(",")).contains("ro"); }));
        assertTrue(mounts.stream().anyMatch(line -> { var parts = line.split(" "); return parts[1].equals("/tmp") && Arrays.asList(parts[3].split(",")).containsAll(List.of("noexec", "nosuid", "nodev")); }));
        var status = Files.readString(Path.of("/proc/self/status"));
        assertTrue(status.matches("(?s).*Uid:\\s+65532\\s+65532\\s+65532\\s+65532.*"));
        assertTrue(status.matches("(?s).*CapEff:\\s+0+.*"));
        assertTrue(status.matches("(?s).*NoNewPrivs:\\s+1.*"));
        for (var n : Collections.list(NetworkInterface.getNetworkInterfaces())) assertTrue(n.isLoopback());
        try (var socket = new Socket()) { assertThrows(IOException.class, () -> socket.connect(new InetSocketAddress("192.0.2.1", 443), 200)); }
        var script = Files.createTempFile("/tmp".equals(System.getProperty("java.io.tmpdir")) ? Path.of("/tmp") : Path.of(System.getProperty("java.io.tmpdir")), "noexec-", ".sh");
        Files.writeString(script, "#!/bin/sh\nexit 0\n");
        Files.setPosixFilePermissions(script, Set.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE, PosixFilePermission.OWNER_EXECUTE));
        assertThrows(IOException.class, () -> new ProcessBuilder(script.toString()).start());
        System.out.println("F8_ISOLATION_CHECKS_PASSED");
    }
}
