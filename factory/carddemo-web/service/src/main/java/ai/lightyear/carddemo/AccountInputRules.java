package ai.lightyear.carddemo;

/** First COACTUPC group. Storage adaptation is outside these business rules. */
public final class AccountInputRules {
  public enum Outcome {
    VALID,
    MISSING,
    INVALID
  }

  @CobolSource(program = "COACTUPC", paragraph = "1215-EDIT-MANDATORY", lines = "1824-1850")
  public static Outcome validateRequired(String value) {
    // Source quirk: all LOW-VALUES and all spaces are empty separately.
    // A mixture of NUL and spaces is supplied, as are tabs and digit zero.
    return value.chars().allMatch(c -> c == 0) || value.chars().allMatch(c -> c == ' ')
        ? Outcome.MISSING
        : Outcome.VALID;
  }

  @CobolSource(program = "COACTUPC", paragraph = "1220-EDIT-YESNO", lines = "1856-1891")
  public static Outcome validateYesNo(char value) {
    return switch (value) {
      case 0, ' ', '0' -> Outcome.MISSING;
      case 'Y', 'N' -> Outcome.VALID;
      default -> Outcome.INVALID;
    };
  }
}
