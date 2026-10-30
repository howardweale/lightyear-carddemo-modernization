package ai.lightyear.carddemo.service;

/** Engineering-twin CEE3ABD mapping, not a native z/OS condition code. */
public final class IntcalcAbendException extends IllegalStateException {

    public static final int PROCESS_EXIT_CODE = 12;
    public static final String DIAGNOSTIC =
            "INTCALC ABENDING PROGRAM: CEE3ABD=999 TIMING=0 PROCESS-EXIT=12";

    public IntcalcAbendException(String message) {
        super(message);
    }

    public IntcalcAbendException(String message, Throwable cause) {
        super(message, cause);
    }

    public static boolean causedBy(Throwable failure) {
        for (Throwable current = failure; current != null; current = current.getCause()) {
            if (current instanceof IntcalcAbendException) {
                return true;
            }
        }
        return false;
    }
}
