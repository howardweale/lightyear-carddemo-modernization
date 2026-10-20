package ai.lightyear.carddemo;

import java.math.BigInteger;

/** Business outcomes and the source's observable scratch-buffer transformation. */
public final class AccountTextRules {
    public enum Status { VALID, MISSING, INVALID, ZERO }
    public record Result(Status status, String scratch, boolean converted) {}

    @CobolSource(program="COACTUPC", paragraph="1225-EDIT-ALPHA-REQD", lines="1898-1950")
    public static Result requiredName(String value) { return text(value, true, false); }

    @CobolSource(program="COACTUPC", paragraph="1230-EDIT-ALPHANUM-REQD", lines="1955-2008")
    public static Result requiredText(String value) { return text(value, true, true); }

    @CobolSource(program="COACTUPC", paragraph="1235-EDIT-ALPHA-OPT", lines="2012-2056")
    public static Result optionalName(String value) { return text(value, false, false); }

    @CobolSource(program="COACTUPC", paragraph="1240-EDIT-ALPHANUM-OPT", lines="2061-2104")
    public static Result optionalText(String value) { return text(value, false, true); }

    @CobolSource(program="COACTUPC", paragraph="1245-EDIT-NUM-REQD", lines="2109-2175")
    public static Result requiredNonzeroDigits(String value) {
        if (empty(value)) return new Result(Status.MISSING, value, false);
        if (!value.chars().allMatch(c -> c >= '0' && c <= '9'))
            return new Result(Status.INVALID, value, false);
        return new Result(new BigInteger(value).signum() == 0 ? Status.ZERO : Status.VALID, value, false);
    }

    @CobolSource(program="COACTUPC", paragraph="1225-EDIT-ALPHA-REQD", lines="1902-1908")
    private static boolean empty(String value) {
        // Quirk: mixed NUL/spaces is supplied. Tabs are not COBOL TRIM spaces.
        return value.chars().allMatch(c -> c == 0) || value.chars().allMatch(c -> c == ' ');
    }

    @CobolSource(program="COACTUPC", paragraph="1225-EDIT-ALPHA-REQD", lines="1923-1949")
    private static Result text(String value, boolean required, boolean digits) {
        if (empty(value)) return new Result(required ? Status.MISSING : Status.VALID, value, false);
        StringBuilder scratch = new StringBuilder(value.length());
        for (char c : value.toCharArray()) {
            boolean letter = c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z';
            scratch.append(letter || digits && c >= '0' && c <= '9' ? ' ' : c);
        }
        String converted = scratch.toString();
        return new Result(converted.chars().allMatch(c -> c == ' ') ? Status.VALID : Status.INVALID,
                          converted, true);
    }
}
