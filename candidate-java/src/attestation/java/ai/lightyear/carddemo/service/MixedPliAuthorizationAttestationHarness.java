package ai.lightyear.carddemo.service;

import ai.lightyear.carddemo.service.MixedPliAuthorizationService.AuthorizationInput;
import ai.lightyear.carddemo.service.MixedPliAuthorizationService.AuthorizationRow;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** JDK-only deterministic test harness that emits a JUnit-compatible XML report. */
public final class MixedPliAuthorizationAttestationHarness {
    private static final MixedPliAuthorizationService SERVICE = new MixedPliAuthorizationService();
    private static final Map<String, AuthorizationRow> ROWS = Map.of(
            "TX0000000000001", new AuthorizationRow(new BigDecimal("125.50"), "N"),
            "TX0000000000002", new AuthorizationRow(new BigDecimal("0.00"), "Y"));

    private MixedPliAuthorizationAttestationHarness() { }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected JUnit XML output path");
        }
        List<TestResult> results = List.of(
                run("normalRiskAndCobolBoundary", MixedPliAuthorizationAttestationHarness::normalRisk),
                run("fraudRiskIsOneHundred", MixedPliAuthorizationAttestationHarness::fraudRisk),
                run("invalidInputStopsBeforeCall", MixedPliAuthorizationAttestationHarness::invalidInput),
                run("missingDb2RowStopsBeforeCall", MixedPliAuthorizationAttestationHarness::missingRow),
                run("decimalDivisionTruncates", MixedPliAuthorizationAttestationHarness::decimalTruncation));
        long failures = results.stream().filter(result -> result.failure() != null).count();
        StringBuilder xml = new StringBuilder();
        xml.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
                .append("<testsuite name=\"MixedPliAuthorizationAttestation\" tests=\"")
                .append(results.size()).append("\" failures=\"").append(failures)
                .append("\" errors=\"0\" skipped=\"0\">\n");
        for (TestResult result : results) {
            xml.append("  <testcase classname=\"ai.lightyear.carddemo.service.MixedPliAuthorizationService\" name=\"")
                    .append(result.name()).append("\">");
            if (result.failure() != null) {
                xml.append("<failure message=\"").append(escape(result.failure())).append("\"/>");
            }
            xml.append("</testcase>\n");
        }
        xml.append("</testsuite>\n");
        Files.writeString(Path.of(args[0]), xml.toString(), StandardCharsets.UTF_8);
        if (failures != 0) {
            throw new AssertionError(failures + " attestation test(s) failed");
        }
    }

    private static TestResult run(String name, CheckedTest test) {
        try {
            test.run();
            return new TestResult(name, null);
        } catch (Throwable failure) {
            return new TestResult(name, failure.getMessage() == null ? failure.getClass().getName() : failure.getMessage());
        }
    }

    private static void normalRisk() {
        List<MixedPliAuthorizationService.CobolCall> calls = new ArrayList<>();
        var result = SERVICE.execute(input("TX0000000000001", "999.99", "Y"),
                MixedPliAuthorizationService.repository(ROWS), calls::add);
        require("NORMAL".equals(result.status()), "normal status");
        require("125.50".equals(result.authorizationRecord().approvedAmount()), "Db2 overwrite");
        require("1.25".equals(result.riskScore()), "risk score");
        require(calls.size() == 1 && "CBACT04C".equals(calls.get(0).program()), "COBOL call");
    }

    private static void fraudRisk() {
        var result = SERVICE.execute(input("TX0000000000002", "1.00", "N"),
                MixedPliAuthorizationService.repository(ROWS), ignored -> { });
        require("100.00".equals(result.riskScore()), "fraud risk");
    }

    private static void invalidInput() {
        List<MixedPliAuthorizationService.CobolCall> calls = new ArrayList<>();
        var result = SERVICE.execute(new AuthorizationInput("BAD", "TX0000000000001", "Z99999",
                        new BigDecimal("1.00"), "N"), MixedPliAuthorizationService.repository(ROWS), calls::add);
        require("INPUT_ERROR".equals(result.status()) && calls.isEmpty(), "input boundary");
    }

    private static void missingRow() {
        List<MixedPliAuthorizationService.CobolCall> calls = new ArrayList<>();
        var result = SERVICE.execute(input("TX0000000000999", "1.00", "N"),
                MixedPliAuthorizationService.repository(ROWS), calls::add);
        require("SQL_NOT_FOUND".equals(result.status()) && calls.isEmpty(), "missing row boundary");
    }

    private static void decimalTruncation() {
        Map<String, AuthorizationRow> rows = Map.of(
                "TX0000000000003", new AuthorizationRow(new BigDecimal("199.99"), "N"));
        var result = SERVICE.execute(input("TX0000000000003", "1.00", "N"),
                MixedPliAuthorizationService.repository(rows), ignored -> { });
        require("1.99".equals(result.riskScore()), "ROUND_DOWN semantics");
    }

    private static AuthorizationInput input(String transactionId, String amount, String fraud) {
        return new AuthorizationInput("4000000000000001", transactionId, "Z99999", new BigDecimal(amount), fraud);
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static String escape(String value) {
        return value.replace("&", "&amp;").replace("\"", "&quot;").replace("<", "&lt;").replace(">", "&gt;");
    }

    @FunctionalInterface
    private interface CheckedTest { void run() throws Exception; }
    private record TestResult(String name, String failure) { }
}
