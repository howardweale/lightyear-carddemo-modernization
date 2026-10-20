package ai.lightyear.carddemo;

import java.math.BigDecimal;

/** Default-dollar amount syntax; no extra range, scale or positivity policy. */
public final class AccountMoneyRule {
    public record Result(AccountInputRules.Outcome outcome, BigDecimal amount) {}

    @CobolSource(program="COACTUPC", paragraph="1250-EDIT-SIGNED-9V2", lines="2180-2220")
    public static Result validate(String input) {
        // Quirk: even zero and negative values pass this syntax-only edit.
        if (input.chars().allMatch(c -> c == 0) || input.chars().allMatch(c -> c == ' '))
            return new Result(AccountInputRules.Outcome.MISSING, null);
        try {
            return new Result(AccountInputRules.Outcome.VALID, CobolNumber.parse(input, true));
        } catch (IllegalArgumentException invalid) {
            return new Result(AccountInputRules.Outcome.INVALID, null);
        }
    }
}
