package ai.lightyear.carddemo;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.Map;

/** COSGN00C orchestration; generated bindings provide layouts and screen literals. */
public final class SignonService implements TransactionService {
    private static final String PROGRAM = "COSGN00C";
    private final Bindings bindings;
    private final TypedRecords records;

    public SignonService(Bindings bindings) {
        this.bindings = bindings;
        this.records = new TypedRecords(bindings);
    }

    @Override
    @CobolSource(program="COSGN00C", paragraph="MAIN-PARA", lines="73-102")
    public Result interact(Connection db, Commarea area, String aid,
                           Map<String, String> input) throws SQLException {
        // Receipt quirk: fresh WORKING-STORAGE, never LK-COMMAREA state.
        // SignonCommareaTest proves rejected and non-ENTER invocations clear it.
        area.copyBytes(0, new Commarea(bindings.root.path("program_commareas").path(PROGRAM), null).bytes());
        ScreenFrame frame = new ScreenFrame(bindings, PROGRAM);
        return switch (aid) {
            case "INITIAL" -> new Result(PROGRAM, frame, false);
            case "PF3" -> endSession(frame);
            case "ENTER" -> signIn(db, area, frame, input);
            default -> invalidKey(frame);
        };
    }

    @CobolSource(program="COSGN00C", paragraph="SEND-PLAIN-TEXT", lines="162-172")
    private Result endSession(ScreenFrame frame) {
        frame.message = bindings.root.path("common_constants").path("CCDA-MSG-THANK-YOU").asText().stripTrailing();
        return new Result(PROGRAM, frame, true);
    }

    @CobolSource(program="COSGN00C", paragraph="MAIN-PARA", lines="91-94")
    private Result invalidKey(ScreenFrame frame) {
        // No RECEIVE: initialized blank output replaces password underscores.
        frame.receive(Map.of()).forEach(frame::set);
        frame.error(bindings.root.path("common_constants").path("CCDA-MSG-INVALID-KEY").asText().stripTrailing(), frame.cursor);
        return new Result(PROGRAM, frame, false);
    }

    @CobolSource(program="COSGN00C", paragraph="PROCESS-ENTER-KEY", lines="108-140")
    private Result signIn(Connection db, Commarea area, ScreenFrame frame,
                          Map<String, String> input) throws SQLException {
        Map<String, String> received = frame.receive(input);
        received.forEach(frame::set);
        String user = received.get("USERID");
        String password = received.get("PASSWD");
        // Receipt quirk: the source moves the uppercase ID even after an error SEND.
        area.set("CDEMO-USER-ID", SignonRules.normalizeCredential(user));
        return switch (SignonRules.validateCredentials(user, password)) {
            case USER_REQUIRED -> error(frame, "Please enter User ID ...", "USERID");
            case PASSWORD_REQUIRED -> error(frame, "Please enter Password ...", "PASSWD");
            case NONE -> authenticate(db, area, frame,
                    SignonRules.normalizeCredential(user), SignonRules.normalizeCredential(password));
        };
    }

    @CobolSource(program="COSGN00C", paragraph="READ-USER-SEC-FILE", lines="209-251")
    private Result authenticate(Connection db, Commarea area, ScreenFrame frame,
                                String user, String password) throws SQLException {
        Map<String, Object> row = records.read(db, "usrsec", Commarea.encode(user), false);
        if (row == null) return error(frame, "User not found. Try again ...", "USERID");
        if (!records.text("usrsec", row, "SEC-USR-PWD").equals(password)) {
            return error(frame, "Wrong Password. Try again ...", "PASSWD");
        }
        String userType = records.text("usrsec", row, "SEC-USR-TYPE");
        area.set("CDEMO-FROM-TRANID", frame.transaction);
        area.set("CDEMO-FROM-PROGRAM", frame.program);
        area.set("CDEMO-USER-ID", user);
        area.set("CDEMO-USER-TYPE", userType);
        area.set("CDEMO-PGM-CONTEXT", "0");
        return new Result(SignonRules.authenticatedDestination(userType), frame, false);
    }

    @CobolSource(program="COSGN00C", paragraph="SEND-SIGNON-SCREEN", lines="145-157")
    private Result error(ScreenFrame frame, String message, String cursor) {
        frame.error(bindings.literal(PROGRAM, message), cursor);
        return new Result(PROGRAM, frame, false);
    }
}
