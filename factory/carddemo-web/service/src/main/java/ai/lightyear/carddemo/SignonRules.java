package ai.lightyear.carddemo;

import java.util.Locale;

/** Business rules for the fixed-width COSGN00 sign-on fields. */
public final class SignonRules {
    private SignonRules() {}

    public enum CredentialIssue { NONE, USER_REQUIRED, PASSWORD_REQUIRED }

    @CobolSource(program="COSGN00C", paragraph="PROCESS-ENTER-KEY", lines="117-130")
    public static CredentialIssue validateCredentials(String user, String password) {
        if (isSourceEmpty(user)) return CredentialIssue.USER_REQUIRED;
        if (isSourceEmpty(password)) return CredentialIssue.PASSWORD_REQUIRED;
        return CredentialIssue.NONE;
    }

    @CobolSource(program="COSGN00C", paragraph="PROCESS-ENTER-KEY", lines="118-123")
    public static boolean isSourceEmpty(String value) {
        // Source quirk: all spaces OR all LOW-VALUES. Mixed bytes are not empty;
        // Unicode strip/isBlank would silently change this source predicate.
        return value.chars().allMatch(c -> c == ' ') || value.chars().allMatch(c -> c == 0);
    }

    @CobolSource(program="COSGN00C", paragraph="PROCESS-ENTER-KEY", lines="132-136")
    public static String normalizeCredential(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    @CobolSource(program="COSGN00C", paragraph="READ-USER-SEC-FILE", lines="230-240")
    public static String authenticatedDestination(String userType) {
        return userType.equals("A") ? "COADM01C" : "COMEN01C";
    }
}
