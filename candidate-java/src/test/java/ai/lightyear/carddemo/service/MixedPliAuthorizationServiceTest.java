package ai.lightyear.carddemo.service;

import static org.assertj.core.api.Assertions.assertThat;

import ai.lightyear.carddemo.service.MixedPliAuthorizationService.AuthorizationInput;
import ai.lightyear.carddemo.service.MixedPliAuthorizationService.AuthorizationRow;
import ai.lightyear.carddemo.service.MixedPliAuthorizationService.CobolCall;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

class MixedPliAuthorizationServiceTest {

    private final MixedPliAuthorizationService service = new MixedPliAuthorizationService();
    private final Map<String, AuthorizationRow> rows = Map.of(
            "TX0000000000001", new AuthorizationRow(new BigDecimal("125.50"), "N"),
            "TX0000000000002", new AuthorizationRow(new BigDecimal("0.00"), "Y"));

    @Test
    void overwritesSelectedFieldsCalculatesRiskAndInvokesCobolOnce() {
        List<CobolCall> calls = new ArrayList<>();
        var result = service.execute(input("TX0000000000001", "999.99", "Y"),
                MixedPliAuthorizationService.repository(rows), calls::add);

        assertThat(result.status()).isEqualTo("NORMAL");
        assertThat(result.authorizationRecord().approvedAmount()).isEqualTo("125.50");
        assertThat(result.authorizationRecord().fraudFlag()).isEqualTo("N");
        assertThat(result.authorizationRecord().authorizationCode()).isEqualTo("Z99999");
        assertThat(result.authorizationRecord().transactionIdFixed16()).hasSize(16).endsWith(" ");
        assertThat(result.riskScore()).isEqualTo("1.25");
        assertThat(calls).containsExactly(new CobolCall("CBACT04C", "OPTIONS(COBOL)", 10, "2026-08-20"));
        assertThat(result.trace()).containsExactly(
                "READ_AUTHIN", "SELECT_AUTHFRDS", "CALC_RISK", "CALL_CBACT04C", "WRITE_AUTHOUT");
    }

    @Test
    void fraudBranchIsExactlyOneHundred() {
        List<CobolCall> calls = new ArrayList<>();
        var result = service.execute(input("TX0000000000002", "125.50", "N"),
                MixedPliAuthorizationService.repository(rows), calls::add);
        assertThat(result.riskScore()).isEqualTo("100.00");
        assertThat(result.authorizationRecord().fraudFlag()).isEqualTo("Y");
        assertThat(calls).hasSize(1);
    }

    @Test
    void invalidAndMissingRowsFailBeforeTheCobolBoundaryOrWrite() {
        List<CobolCall> calls = new ArrayList<>();
        var invalid = service.execute(
                new AuthorizationInput("BAD", "TX0000000000001", "Z99999", new BigDecimal("1.00"), "N"),
                MixedPliAuthorizationService.repository(rows), calls::add);
        var missing = service.execute(input("TX0000000000999", "1.00", "N"),
                MixedPliAuthorizationService.repository(rows), calls::add);

        assertThat(invalid.status()).isEqualTo("INPUT_ERROR");
        assertThat(missing.status()).isEqualTo("SQL_NOT_FOUND");
        assertThat(invalid.authorizationRecord()).isNull();
        assertThat(missing.authorizationRecord()).isNull();
        assertThat(calls).isEmpty();
        assertThat(missing.trace()).doesNotContain("CALL_CBACT04C", "WRITE_AUTHOUT");
    }

    private AuthorizationInput input(String transactionId, String amount, String fraud) {
        return new AuthorizationInput(
                "4000000000000001", transactionId, "Z99999", new BigDecimal(amount), fraud);
    }
}
