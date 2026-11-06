package ai.lightyear.carddemo.batch;

import ai.lightyear.carddemo.service.IntcalcAbendException;

import org.springframework.batch.core.BatchStatus;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.batch.autoconfigure.JobExecutionEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

/** Transfers the completed batch outcome to the operating-system process. */
@Component
public final class IntcalcProcessStatus
        implements ExitCodeGenerator, ApplicationListener<JobExecutionEvent> {

    private int exitCode;

    @Override
    public void onApplicationEvent(JobExecutionEvent event) {
        var execution = event.getJobExecution();
        if (execution.getStatus() == BatchStatus.COMPLETED) {
            return;
        }
        boolean abend = execution.getAllFailureExceptions().stream()
                .anyMatch(IntcalcAbendException::causedBy);
        int failureCode = abend ? IntcalcAbendException.PROCESS_EXIT_CODE : 1;
        exitCode = Math.max(exitCode, failureCode);
        if (abend) {
            System.err.println(IntcalcAbendException.DIAGNOSTIC);
        }
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
