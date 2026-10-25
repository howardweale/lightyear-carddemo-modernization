package ai.lightyear.carddemo;

/** Phone edits retain the source's optional-input typo and component ordering. */
public final class AccountPhoneRules {
  private enum Part {
    AREA,
    PREFIX,
    LINE
  }

  private enum Status {
    VALID,
    BLANK,
    NONNUMERIC,
    ZERO
  }

  private static boolean spaces(String value) {
    return value.equals(" ".repeat(value.length()));
  }

  private static boolean low(String value) {
    return value.equals("\0".repeat(value.length()));
  }

  private static boolean absent(String value) {
    return spaces(value) || low(value);
  }

  private static Status status(String value) {
    if (absent(value)) return Status.BLANK;
    if (!value.matches("[0-9]+")) return Status.NONNUMERIC;
    return Integer.parseInt(value) == 0 ? Status.ZERO : Status.VALID;
  }

  private static void error(AccountEditState state, String suffix) {
    state.set(AccountEditState.Flag.INPUT_ERROR);
    if (state.test(AccountEditState.Flag.WS_RETURN_MSG_OFF))
      state.put(
          AccountEditState.Field.WS_RETURN_MSG,
          state.get(AccountEditState.Field.WS_EDIT_VARIABLE_NAME).replaceAll("^ +| +$", "")
              + suffix);
  }

  @CobolSource(program = "COACTUPC", paragraph = "1260-EDIT-US-PHONE-NUM", lines = "2225-2429")
  public static void validate(AccountEditState state) {
    String area = state.get(AccountEditState.Field.WS_EDIT_US_PHONE_NUMA),
        prefix = state.get(AccountEditState.Field.WS_EDIT_US_PHONE_NUMB),
        line = state.get(AccountEditState.Field.WS_EDIT_US_PHONE_NUMC);
    state.set(AccountEditState.Flag.WS_EDIT_US_PHONE_IS_INVALID);
    // The third source operand repeats NUMA SPACE, not NUMC SPACE.
    if (absent(area) && absent(prefix) && (spaces(area) || low(line))) {
      state.set(AccountEditState.Flag.WS_EDIT_US_PHONE_IS_VALID);
      return;
    }
    part(state, Part.AREA, area);
    part(state, Part.PREFIX, prefix);
    part(state, Part.LINE, line);
  }

  private static void part(AccountEditState state, Part part, String value) {
    Status status = status(value);
    String letter =
        switch (part) {
          case AREA -> "A";
          case PREFIX -> "B";
          case LINE -> "C";
        };
    AccountEditState.Flag valid =
        AccountEditState.Flag.valueOf("FLG_EDIT_US_PHONE" + letter + "_ISVALID");
    AccountEditState.Flag blank =
        AccountEditState.Flag.valueOf("FLG_EDIT_US_PHONE" + letter + "_BLANK");
    AccountEditState.Flag invalid =
        AccountEditState.Flag.valueOf("FLG_EDIT_US_PHONE" + letter + "_NOT_OK");
    String name =
        switch (part) {
          case AREA -> "Area code";
          case PREFIX -> "Prefix code";
          case LINE -> "Line number code";
        };
    if (status != Status.VALID) {
      state.set(status == Status.BLANK ? blank : invalid);
      error(
          state,
          ": "
              + name
              + switch (status) {
                case BLANK -> " must be supplied.";
                case NONNUMERIC ->
                    " must be A " + (part == Part.LINE ? "4" : "3") + " digit number.";
                case ZERO -> " cannot be zero";
                default -> throw new IllegalStateException();
              });
      return;
    }
    if (part == Part.AREA) {
      state.put(AccountEditState.Field.WS_US_PHONE_AREA_CODE_TO_EDIT, value);
      if (!state.test(AccountEditState.Flag.VALID_GENERAL_PURP_CODE)) {
        state.set(invalid);
        error(state, ": Not valid North America general purpose area code");
        return;
      }
    }
    state.set(valid);
  }
}
