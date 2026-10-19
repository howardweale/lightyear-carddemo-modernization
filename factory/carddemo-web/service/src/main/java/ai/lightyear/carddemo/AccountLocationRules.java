package ai.lightyear.carddemo;

import java.util.Set;

/** Exact source lookup outcomes. Callers retain source flags and first-error order. */
public final class AccountLocationRules {
    public record Result(String scratch, boolean valid) {}

    @CobolSource(program="COACTUPC", paragraph="1270-EDIT-US-STATE-CD", lines="2493-2510")
    public static Result state(String state, Set<String> sourceStateCodes) {
        return new Result(state, sourceStateCodes.contains(state));
    }

    @CobolSource(program="COACTUPC", paragraph="1280-EDIT-US-STATE-ZIP-CD", lines="2536-2557")
    public static Result stateZip(String state, String zip, Set<String> sourceStateZipPrefixes) {
        // Inputs are fixed-width source fields; only the first two ZIP bytes are used.
        String scratch = state + zip.substring(0, 2);
        return new Result(scratch, sourceStateZipPrefixes.contains(scratch));
    }
}
