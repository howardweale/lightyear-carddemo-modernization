# B06 closure lifecycle correction r8 — offline review

r7 remains failed. The exact observed failure and all seven partial copies were
recorded in [core-status.md](../core-status.md) before changing code. No probe-error
line exists in its Maven log; JVM-exit interruption is supported by the partial
capture and non-waiting test, but the precise underlying exception is unavailable.
No old evidence, plan, snapshot or decision has been changed.

## Implemented

- `closure-error.json` records exception class, message, full stack trace and stage.
  The worker prints its bytes verbatim, even when Maven reports success. Worker
  failures additionally create `worker-error.json`.
- The real catalog test waits at most 600 seconds for completion and fails on an
  error or absent marker. Agent readiness requires loaded test classes and ACTIVE
  system bundle before capture starts. It captures once into fresh staging,
  atomically publishes observation and completion; shutdown joins for 10 seconds
  and records `interrupted by JVM exit` if unfinished. No overwrite/retry.
- Only temporary bundle files are streamed in the JVM. The worker captures
  persistent application JARs/folders after Maven. Folder selection uses
  Bundle-ClassPath, META-INF/resources and explicit dev output folders. It
  excludes source/build metadata and live target/work/surefire/configuration
  subtrees; explicitly selected target/classes and target/test-classes are kept.
  This is an explicit prospective folder-content rule. No recursive live build
  tree or in-memory archive construction. Files, names and final byte hashes
  are rechecked to detect mutation. Unknown/external dev paths refuse.
- Exact raw agent observation, its completion hash, effective osgi.dev properties,
  selected folder files and copy hashes are rechecked by replay. New observation
  /5, launch receipt /6 and resolved-runtime /6 retain older replay schemas.
  Runtime/native admission remains blocked.

## Offline results and limits

92 focused tests passed in 16.654 seconds; after the final streamed-JAR mutation
guard, 10 targeted tests passed in 0.689 seconds (93 distinct tests overall).
Tests used real host Equinox org.eclipse.osgi_3.18.500.v20230801-1826.jar, SHA-256
`80b275d58379723b291ea650249cc3809c8f10b34f78aaf988132cd6d434ab4e`.
The immediate-return test body, 128-source/32-MiB case, abrupt System.exit and
folder-mutation case all produced a complete result or the required specific
error record. Windows ProcessHandle does not expose argv: normal capture cases
record `java.util.NoSuchElementException` at `process-metadata`, not a fabricated
command or claimed successful Linux capture. Abrupt exit records the explicit
shutdown error; folder mutation records its worker error.

The full worker finalization, inventory, producer and independent replay passed
on disk-backed synthetic outputs with 350 bundles (44 application, 203 Maven,
102 transient, one system), including JAR/folder layouts and real-shaped
osgi.dev properties. Only jimage output is synthetic in those pipeline tests;
there is no native JDK or qualification claim. Signatures in these tests use
ephemeral in-memory test keys, never production authorities.

Two early host rehearsal invocations failed because the standalone launcher
did not load FrameworkUtil, then did not stop its own framework after the
intentional Windows error. The rehearsal was corrected; these failures are not
counted as passes. The prior r7 failure is not replaced by these test results.

## October 8 r8 non-evidence practice result

Howard approved one bounded practice container. It failed after **127.532 seconds**;
owned-container/network/volume absence was independently checked after cleanup.
Zero models, native pairs and databases; no network. No retry or Tower request.

The agent completed its observation and matching completion marker: 350 bundles
and 102 preserved transient source copies. Maven succeeded. The worker then
failed at `application-capture` with exact error
`ValueError: runtime-folder-root-missing`. Producer/replay was not reached.
Practice report SHA-256:
`83ca2716ec5a6a1e6a4003d0384ac611228c59915fe9839cccc6efc9c86c21f7`.
Observation SHA-256:
`6a4f411e1a9c66570c0e7da11f3eedc9127439bca81351bfd8c7b1c3c01d64b7`.

Partial application copies 9, 10, 22 and 48 precede bundle 52,
`org.idempiere.test`, in the recorded capture order. Its dev.properties declares
`target/classes` and `target/test-classes`. The compilation log and loaded-class
catalogue confirm use of `target/classes`; `target/test-classes` is a suspected
missing root, not an established fact. The old error omitted the path, and the
full test-bundle root was not retained. The prospective error now includes the
bundle, declared root and path; missing roots still refuse. A unit test checks
that exact diagnostic. No capture/admission policy has been widened.

The one-shot practice source, plan, results and failed r7 snapshot remain
unchanged. See [practice review](practice-review.json).
Native admission remains blocked. A fresh practice requires separate approval;
no qualification success or independent attestation is claimed.

The preparation-only `offline-review.json` remains a historical record made
before approval and execution. The consumed local plan is
`work/b06-runtime-practice-r8/practice-plan.json`; do not rerun it.

## October 8 corrected practice r8b passed

The user-authorized fresh non-evidence practice passed in **387.000 seconds**
(6 minutes 27 seconds), including worker finalization, producer, offline replay
with an ephemeral in-memory test key, and owned cleanup. Independent read-only
owned-label container/network/volume checks were empty afterward. No production
signer or Tower authority was used. Zero model calls, databases and native pairs;
network disabled. This is not a qualification result or measurement admission.

All 350 observed bundles were processed, including 44 application copies and
102 preserved source-only transient copies. The worker recorded the absent
`org.idempiere.test/target/test-classes` dev output; classes loaded from
`target/classes`. Folder-selection policy `/2` records this absence explicitly,
keeps manifest roots mandatory and rejects loaded classes from absent roots.
98 offline tests passed before the rerun, including complete pipeline replay
and negative cases. Host/worker hashes remained unchanged during the run.

Practice report SHA-256:
`49f654a1e0f8b3df00cb560c69ad271b734c2751a14c4c6473bb46d49d58ba90`.
Measured inventory SHA-256:
`37107d2f9253c18ceef2110ed06cb12d4c9f8dabfc28bb4f62fdaef3317b7f46`.
See [r8b review](practice-r8b-review.json) and the
[explicit capture rule](optional-dev-output-fix.md).

r7 and the failed r8 practice remain preserved. A future evidence run still
requires a fresh exact snapshot, publication and Tower decision; none was
created or launched here. Operator review, not independent attestation.


## Pre-window audit supersedes readiness inference

The [six-check audit](six-check-audit.md) found content-capture omissions, warnings
and missing exact commit/snapshot/Tower binding. Pipeline success does not satisfy
those requirements. No evidence run is ready or authorized.
