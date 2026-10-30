package ai.lightyear.carddemo.batch;

import static org.assertj.core.api.Assertions.assertThat;

import ai.lightyear.carddemo.service.IntcalcAbendException;

import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class IntcalcProcessExitTest {

    @TempDir
    Path temporary;

    @Test
    void retainedM1MissingDisclosureHasTheTwinExitAndUnchangedDatasets() throws Exception {
        Properties binding = new Properties();
        try (var stream = getClass().getResourceAsStream(
                "/intcalc-m2-abend/missing-disclosure.properties")) {
            binding.load(stream);
        }
        Path root = repositoryRoot();
        byte[] original = Files.readAllBytes(root.resolve(binding.getProperty("source_receipt")));
        assertThat(sha(new String(original, StandardCharsets.UTF_8)
                .replace("\r\n", "\n").getBytes(StandardCharsets.UTF_8)))
                .isEqualTo(binding.getProperty("source_receipt_sha256"));
        Path fixture = root.resolve(
                "tests/mainframe/fixtures/intcalc-discriminating-v1/missing-disclosure");
        Path input = Files.createDirectory(temporary.resolve("input"));
        Map<String, Integer> lengths = new LinkedHashMap<>();
        lengths.put("ACCTFILE", 300);
        lengths.put("TCATBALF", 50);
        lengths.put("DISCGRP", 50);
        lengths.put("XREFFILE", 50);
        lengths.put("TRANSACT", 350);
        Map<String, String> files = Map.of(
                "ACCTFILE", "acctdata.txt", "TCATBALF", "tcatbal.txt",
                "DISCGRP", "discgrp.txt", "XREFFILE", "cardxref.txt");
        for (var entry : lengths.entrySet()) {
            byte[] raw = Files.readAllBytes(fixture.resolve(entry.getKey() + ".bin"));
            assertThat(sha(raw)).isEqualTo(binding.getProperty(entry.getKey() + ".input_sha256"));
            byte[] framed = frame(raw, entry.getValue());
            // This failure precedes any account change or transaction output.
            assertThat(sha(framed)).isEqualTo(binding.getProperty(entry.getKey() + ".output_sha256"));
            if (files.containsKey(entry.getKey())) {
                Files.write(input.resolve(files.get(entry.getKey())), framed);
            }
        }
        Path output = temporary.resolve("output");
        Result result = launch(input, output, "2022071800");
        assertThat(result.exitCode()).isEqualTo(
                Integer.parseInt(binding.getProperty("expected_exit_code")));
        assertThat(result.log()).contains(IntcalcAbendException.DIAGNOSTIC);
        assertThat(Files.exists(output.resolve("candidate-receipt.json"))).isFalse();
        assertThat(Files.exists(output.resolve("acctdata.txt"))).isFalse();
        assertThat(Files.exists(output.resolve("transactions.txt"))).isFalse();
        for (var entry : files.entrySet()) {
            assertThat(sha(Files.readAllBytes(input.resolve(entry.getValue()))))
                    .isEqualTo(binding.getProperty(entry.getKey() + ".output_sha256"));
        }
    }

    @Test
    void completedEmptyJobReturnsZero() throws Exception {
        Path input = emptyInput();
        Result result = launch(input, temporary.resolve("output"), "2022071800");
        assertThat(result.exitCode()).isZero();
        assertThat(result.log()).doesNotContain(IntcalcAbendException.DIAGNOSTIC);
    }

    @Test
    void invalidParametersDoNotMasqueradeAsLegacyAbend() throws Exception {
        Path input = emptyInput();
        Result result = launch(input, temporary.resolve("output"), "invalid");
        assertThat(result.exitCode()).isEqualTo(1);
        assertThat(result.log()).doesNotContain(IntcalcAbendException.DIAGNOSTIC);
    }

    private Path emptyInput() throws Exception {
        Path input = Files.createDirectory(temporary.resolve("input"));
        for (String name : new String[] {"acctdata.txt", "tcatbal.txt", "discgrp.txt", "cardxref.txt"}) {
            Files.write(input.resolve(name), new byte[0]);
        }
        return input;
    }

    private Result launch(Path input, Path output, String processingDate) throws Exception {
        String classpath = System.getProperty("surefire.test.class.path",
                System.getProperty("java.class.path"));
        String[] args = {"-cp", classpath, "ai.lightyear.carddemo.CardDemoCandidateApplication",
                "--carddemo.input-dir=" + input, "--carddemo.output-dir=" + output,
                "--carddemo.processing-date=" + processingDate,
                "--carddemo.timestamp=2022-07-18-00.00.00.000000",
                "--carddemo.final-account-policy=source-faithful",
                "--spring.datasource.url=jdbc:h2:mem:m2-exit;DB_CLOSE_DELAY=-1"};
        StringBuilder contents = new StringBuilder();
        for (String arg : args) {
            contents.append('"').append(arg.replace("\\", "\\\\").replace("\"", "\\\""))
                    .append('"').append('\n');
        }
        Path argumentFile = temporary.resolve("java.args");
        Files.writeString(argumentFile, contents, StandardCharsets.UTF_8);
        Path log = temporary.resolve("process.log");
        String binary = System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java";
        Process process = new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", binary).toString(),
                "@" + argumentFile).redirectErrorStream(true).redirectOutput(log.toFile()).start();
        try {
            assertThat(process.waitFor(45, TimeUnit.SECONDS))
                    .as("INTCALC child process completes within 45 seconds").isTrue();
            return new Result(process.exitValue(), Files.readString(log));
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(10, TimeUnit.SECONDS);
            }
        }
    }

    private static Path repositoryRoot() {
        Path path = Path.of("").toAbsolutePath();
        while (path != null && !Files.isDirectory(path.resolve("candidate-java"))) {
            path = path.getParent();
        }
        if (path == null) {
            throw new IllegalStateException("repository root not found");
        }
        return path;
    }

    private static byte[] frame(byte[] raw, int length) {
        String decoded = new String(raw, Charset.forName("IBM037"));
        assertThat(decoded.length() % length).isZero();
        StringBuilder result = new StringBuilder();
        for (int offset = 0; offset < decoded.length(); offset += length) {
            result.append(decoded, offset, offset + length).append('\n');
        }
        return result.toString().getBytes(StandardCharsets.US_ASCII);
    }

    private static String sha(byte[] raw) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));
    }

    private record Result(int exitCode, String log) {
    }
}
