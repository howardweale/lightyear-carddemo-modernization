package ai.lightyear.carddemo;

import static ai.lightyear.carddemo.AccountTextRules.Status.VALID;

import java.util.List;

/** SSN edits in source order, including the implicit first-part IF scope. */
public final class AccountSsnRule {
  public record Part(String input, AccountTextRules.Status status) {}

  public record Result(Part first, boolean restrictedFirst, List<Part> remaining) {}

  @CobolSource(program = "COACTUPC", paragraph = "1265-EDIT-US-SSN", lines = "2431-2488")
  public static Result validate(String first, String second, String third) {
    var initial = new Part(first, AccountTextRules.requiredNonzeroDigits(first).status());
    // Quirk: a failed numeric first part skips both following parts.
    if (initial.status() != VALID) return new Result(initial, false, List.of());
    int number = Integer.parseInt(first);
    boolean restricted = number == 666 || number >= 900;
    // A restricted but numeric first part still enters both following edits.
    return new Result(
        initial,
        restricted,
        List.of(
            new Part(second, AccountTextRules.requiredNonzeroDigits(second).status()),
            new Part(third, AccountTextRules.requiredNonzeroDigits(third).status())));
  }
}
