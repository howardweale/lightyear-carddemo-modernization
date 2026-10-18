package ai.lightyear.carddemo;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static ai.lightyear.carddemo.SignonRules.CredentialIssue.*;

class SignonRulesTest {
    @Test void sourceEmptyMeansUniformSpacesOrLowValuesNotMixedOrUnicodeWhitespace() {
        for (String empty : new String[]{"", " ", "        ", "\0", "\0\0"}) {
            assertTrue(SignonRules.isSourceEmpty(empty));
            assertEquals(USER_REQUIRED, SignonRules.validateCredentials(empty, "valid"));
            assertEquals(PASSWORD_REQUIRED, SignonRules.validateCredentials("valid", empty));
        }
        for (String value : new String[]{" \0", "\0 ", "\t", "x", " X      ", "\u2003"}) {
            assertFalse(SignonRules.isSourceEmpty(value));
            assertEquals(NONE, SignonRules.validateCredentials(value, value));
        }
        assertEquals(USER_REQUIRED, SignonRules.validateCredentials(" ", "\0"));
    }

    @Test void credentialCaseNormalizationRetainsPaddingAndDoesNotUseHostLocale() {
        Locale before = Locale.getDefault();
        try {
            Locale.setDefault(Locale.forLanguageTag("tr-TR"));
            assertEquals("ID      ", SignonRules.normalizeCredential("id      "));
            assertEquals("P4SS\0 ", SignonRules.normalizeCredential("p4ss\0 "));
        } finally { Locale.setDefault(before); }
    }

    @Test void onlyExactAdminStorageSelectsTheAdminDestination() {
        assertEquals("COADM01C", SignonRules.authenticatedDestination("A"));
        for (String type : new String[]{"U", "a", " ", "", "AA", "\0"}) {
            assertEquals("COMEN01C", SignonRules.authenticatedDestination(type));
        }
    }
}
