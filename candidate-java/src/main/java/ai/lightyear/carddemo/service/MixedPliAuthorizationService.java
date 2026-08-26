package ai.lightyear.carddemo.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Production-shaped candidate seam for the bounded ACCTPL1 mixed-language cell. */
public final class MixedPliAuthorizationService {

    public static final String COBOL_PROGRAM = "CBACT04C";
    public static final String CALLING_CONVENTION = "OPTIONS(COBOL)";
    public static final int PARM_LENGTH = 10;
    public static final String PARM_DATE = "2026-08-20";

    public Result execute(AuthorizationInput input, AuthorizationRepository repository, CobolPort cobol) {
        Objects.requireNonNull(repository, "repository");
        Objects.requireNonNull(cobol, "cobol");
        if (!valid(input)) {
            return Result.failure("INPUT_ERROR", "record-contract", List.of());
        }
        AuthorizationRow row = repository.findByTransactionId(input.transactionId());
        if (row == null) {
            return Result.failure("SQL_NOT_FOUND", input.transactionId(),
                    List.of("READ_AUTHIN", "SELECT_AUTHFRDS"));
        }
        BigDecimal risk = "Y".equals(row.fraudFlag())
                ? new BigDecimal("100.00")
                : row.approvedAmount().divide(new BigDecimal("100"), 2, RoundingMode.DOWN);
        CobolCall call = new CobolCall(COBOL_PROGRAM, CALLING_CONVENTION, PARM_LENGTH, PARM_DATE);
        cobol.invoke(call);
        AuthorizationOutput output = new AuthorizationOutput(
                input.cardNumber(), input.transactionId(), input.transactionId() + " ",
                input.authorizationCode(), row.approvedAmount().setScale(2).toPlainString(), row.fraudFlag());
        return new Result(
                "NORMAL", null, output, risk.setScale(2).toPlainString(), List.of(call),
                List.of("READ_AUTHIN", "SELECT_AUTHFRDS", "CALC_RISK", "CALL_CBACT04C", "WRITE_AUTHOUT"));
    }

    private boolean valid(AuthorizationInput input) {
        return input != null
                && width(input.cardNumber(), 16)
                && width(input.transactionId(), 15)
                && width(input.authorizationCode(), 6)
                && input.approvedAmount() != null
                && input.approvedAmount().precision() <= 12
                && input.approvedAmount().scale() <= 2
                && ("N".equals(input.fraudFlag()) || "Y".equals(input.fraudFlag()));
    }

    private boolean width(String value, int length) {
        return value != null && value.length() == length;
    }

    public interface AuthorizationRepository {
        AuthorizationRow findByTransactionId(String transactionId);
    }

    public interface CobolPort {
        void invoke(CobolCall call);
    }

    public record AuthorizationInput(
            String cardNumber,
            String transactionId,
            String authorizationCode,
            BigDecimal approvedAmount,
            String fraudFlag) { }

    public record AuthorizationRow(BigDecimal approvedAmount, String fraudFlag) { }

    public record AuthorizationOutput(
            String cardNumber,
            String transactionId,
            String transactionIdFixed16,
            String authorizationCode,
            String approvedAmount,
            String fraudFlag) { }

    public record CobolCall(String program, String callingConvention, int parmLength, String parmDate) { }

    public record Result(
            String status,
            String error,
            AuthorizationOutput authorizationRecord,
            String riskScore,
            List<CobolCall> cobolCalls,
            List<String> trace) {
        static Result failure(String status, String error, List<String> trace) {
            return new Result(status, error, null, null, List.of(), trace);
        }
    }

    public static AuthorizationRepository repository(Map<String, AuthorizationRow> rows) {
        Map<String, AuthorizationRow> immutable = Map.copyOf(rows);
        return immutable::get;
    }
}
