# M2.4 INTCALC abend process status - draft

Backlog lane - 30 October 2026. One purpose: process status and diagnostic.

## Policy and source boundary

CBACT04C 9999-ABEND-PROGRAM displays ABENDING PROGRAM and calls CEE3ABD with
ABCODE=999, TIMING=0. The existing engineering twin shim maps that call to process
exit 12. This draft adopts 12 explicitly, with the diagnostic:

    INTCALC ABENDING PROGRAM: CEE3ABD=999 TIMING=0 PROCESS-EXIT=12

The [dated policy](m2-intcalc-abend-policy-2026-10-30.json) binds exact source and
retained-result hashes. This is an engineering process mapping, not a native
z/OS abend/condition-code assertion and not a numeric truncation of 999.

Missing required account/xref/disclosure records use a typed abend exception.
Dataset IOException failures use the same mapping. A completed job maps to 0;
other failed jobs map to 1. Main closes the Spring context and returns its exit
code to the OS. A job failure can no longer finish with an implicit process zero.
The fixed diagnostic contains no account key, record value or connector secret.

## CI evidence design

The existing public M1 intcalc-missing-disclosure fixture has an original
retained COBOL-twin return code of 12. The new Java process test binds the whole
retained result's exact Git/LF bytes, each original EBCDIC input hash, and the
twin's logical output hashes. It checks Java's actual OS status, diagnostic,
unchanged input state and absence of success receipt/result files in that case.
A public empty-input success and an invalid-parameter failure check 0 versus 1.

Planned: CI alone launches these child processes. No local test, compilation,
application or twin execution is part of preparation. No whole-M1-suite,
later-abend partial-state, native equivalence, new mutant kill or release result
is asserted. In particular, missing Java result files are not reclassified as a
successful data comparison; the general failure-output contract remains separate.

## Limits and independent review

The native z/OS condition code and the open KF-006 source/index mismatch are not
resolved here. POSTTRAN and the existing twin/shim are unchanged. No normalisation
rule or source-fidelity policy is weakened. The retained reference stays
engineering/provisional and adds no survivor reclassification.

Spring's [exit-code interface](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ExitCodeGenerator.html)
and [batch launcher auto-configuration](https://raw.githubusercontent.com/spring-projects/spring-boot/v4.1.0/module/spring-boot-batch/src/main/java/org/springframework/boot/batch/autoconfigure/BatchJobLauncherAutoConfiguration.java)
describe the explicit bean/event-to-process mechanism used here.

Draft only, no merge before the run's verification. Documentation uses [skip ci];
the separate code commit requests normal CI feedback once. No workflows, fence,
F2/COPAU, POSTTRAN-bound files, model calls or signing.
