package ai.lightyear.carddemo;

/** Typed feedback shared by the already-native COACTUPC validation helpers.
 * It does not normalize source bytes, reset stale flags, or replace the first error.
 */
public final class AccountValidationFeedback {
    private AccountValidationFeedback() {}

    public enum Field {
        INPUT_FLAG("WS-INPUT-FLAG"), MESSAGE("WS-RETURN-MSG"), LABEL("WS-EDIT-VARIABLE-NAME");
        private final String storage;
        Field(String storage) { this.storage=storage; }
        public String storage() { return storage; }
    }
    public enum Flag {
        VALID("\u0000"), MISSING("B"), INVALID("0");
        private final String display;
        Flag(String display) { this.display=display; }
        public String display() { return display; }
    }
    public enum Reason {
        REQUIRED(" must be supplied."), YES_NO(" must be Y or N."),
        ALPHA(" can have alphabets only."), ALPHANUM(" can have numbers or alphabets only."),
        NUMERIC(" must be all numeric."), NONZERO(" must not be zero."),
        MONEY(" is not valid"), SSN_RANGE(": should not be 000, 666, or between 900 and 999"),
        FICO_RANGE(": should be between 300 and 850"), STATE(": is not a valid state code"),
        STATE_ZIP("Invalid zip code for state");
        private final String text;
        Reason(String text) { this.text=text; }
    }
    public interface State {
        String get(Field field);
        void put(Field field,String value);
        boolean messageOff();
    }

    @CobolSource(program="COACTUPC", paragraph="1215-EDIT-MANDATORY", lines="1824-1854")
    public static Flag flag(AccountInputRules.Outcome outcome) {
        return switch(outcome) { case VALID -> Flag.VALID; case MISSING -> Flag.MISSING; case INVALID -> Flag.INVALID; };
    }

    @CobolSource(program="COACTUPC", paragraph="1225-EDIT-ALPHA-REQD", lines="1898-1950")
    public static Flag flag(AccountTextRules.Status outcome) {
        return switch(outcome) { case VALID -> Flag.VALID; case MISSING -> Flag.MISSING; case INVALID, ZERO -> Flag.INVALID; };
    }

    @CobolSource(program="COACTUPC", paragraph="1215-EDIT-MANDATORY", lines="1836-1844")
    public static void error(State state,Reason reason) {
        state.put(Field.INPUT_FLAG,"1");
        if(!state.messageOff())return;
        // STATE/ZIP uses a literal message without the variable-name prefix.
        if(reason==Reason.STATE_ZIP)state.put(Field.MESSAGE,reason.text);
        else state.put(Field.MESSAGE,trimSpaces(state.get(Field.LABEL))+reason.text);
    }

    private static String trimSpaces(String value) {
        int start=0,end=value.length();
        while(start<end && value.charAt(start)==' ')start++;
        while(end>start && value.charAt(end-1)==' ')end--;
        return value.substring(start,end);
    }
}
