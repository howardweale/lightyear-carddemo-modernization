# B06 observer: preserved failures and offline findings

October 9, 2026. Failed native observer practices; zero qualification or measurement
credit. Operator review, not independent attestation. No new Docker, native run,
Tower request or model call was used for this investigation. The frozen-file check
finished successfully before this work began. Preserved evidence was read only.

Subsequent authorization: Howard's [diagnostic gate amendment](b06-diagnostic-gate-amendment.md)
replaces the impossible historical exact-event reproduction prerequisite. The
findings below remain historical facts, not a veto on that explicitly authorized
diagnostic preparation. Qualification still requires a supported fix and proof.

## The 4:15 PM window, recorded as it happened

The window opened at 16:15 PDT; the group actually started at 16:24:53.175659 PDT
and exited at 16:47:42.139893 PDT. Total elapsed: 1,368.953 seconds. Native worker
elapsed: 1,214.203 seconds. Oracle observer preparation took 639.468 seconds;
application execution started at 16:38:55.565298 PDT. The collector failure was
recorded at 16:45:11.547627 PDT, 375.982 seconds later. The worker reported failure
at 16:45:12.500829 PDT and requested application stop. PostgreSQL application
execution did not start. This failure **recurred after the startup correction**.

```text
java.lang.IllegalStateException: generation return arm without matching activation
    at lightyear.observer.PostingObserver$Generation.atReturn(PostingObserver.java:209)
    at lightyear.observer.PostingObserver.entry(PostingObserver.java:445)
    at lightyear.observer.PostingObserver.run(PostingObserver.java:631)
    at lightyear.observer.PostingObserver.main(PostingObserver.java:646)
```

| Commitment | SHA-256 |
| --- | --- |
| Terminal report | `34a27503e9b82e0c775d6b3d10ec8e004ab00a7dc26bcd0dd8ca8ad204b8d598` |
| Partial audit | `5573a07ed30db06a9f2384c05d27e15365b354d4243e806c3b5f82cc592abad4` |
| Collector failure | `f2e6a6bfb7a9d8536af0f2b6cd84edf25cdb3a337d720ca5325e11240aebb502` |
| Native receipt | `b8aebd60d18dd65ed037b2794d6b7241c7a496d2817e2a135dbe521b522623bc` |
| Cleanup | `363355d5b876ac44c3f98c60f1d803c58f1cdd255a74b4ee28c7d1bf3f320cf2` |
| Preserved archive | `71d026978c4a7f8340a3754937b80612be34cc4268efa64cbd44a833db6dd3b1` |
| Frozen snapshot | `e58ea4f5ed0cf1b5347fb256a0d9a425e244530d6af2b24f598682ecd3c77076` |

After exit, all **113,579 frozen hashes and 13 signatures** verified. Read-only
inventory of the exact owner label found no containers, networks or volumes.
The signed audit separately checked eight owned resources. The audit authenticates
the preserved prefix only: clock, execution, complete observer and gate evidence
are missing. No missing stage is treated as successful.

## What the authenticated streams can establish

`tools/b06_host_probe/recorded_prefix.py` streams both saved files, verifies every
hash-chain envelope and the signed census/failure commitments, and derives a
closed structural fixture. The published fixtures contain only original sequence
numbers, event kinds, thread IDs, selected JDK methods and entry depths. Full
stacks, names, values, object graphs and class bytes stay local.

| Run | Ready | Entries | Returns | Frame definitions | Unwinds / other | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Practice r1 | 1 | 12,414 | 12,410 | 2 | 0 | 24,827 |
| Window2 r2 | 1 | 12,435 | 12,432 | 2 | 0 | 24,870 |

Source r1 is `f18cb1e06ca5e6bb1e71ef241402a0fea9ee4dd8`, observer SHA
`c47a8e28e4c3128856bab293dd28ec98d8a7705ec03125e40e3f1d5a63bd2b0b`.
Source r2 is `8031ad1c7376f207854d6f99df6a9e80665d0e9a`, observer SHA
`b5a7430383478985c8ad35185e312f4aeeaaf2d25b3c729f679247701292e99d`.
The pending-stack projection follows the push/pop checks in those exact sources;
it is a Python structural replay, **not execution of Java or raw JDI replay**.
No JVM or target application is involved in this step.

Every recorded return matches its thread's latest recorded entry and depth in
both streams. There are no recorded pairing contradictions. The outstanding
calls below are valid open prefixes; their later outcomes are unknown.

| Run/thread | Open entry indices | Methods | Depths |
| --- | --- | --- | --- |
| r1 / 1 | 24827 | Lookup.ClassDefiner.defineClass | 109 |
| r1 / 68555 | 24822, 24824 | spinInnerClass; Lookup.ClassDefiner.defineClass | 25, 27 |
| r1 / 69371 | 24811 | Lookup.ClassDefiner.defineClass | 36 |
| r2 / 1 | 24870 | ClassLoader.defineClass | 127 |
| r2 / 70903 | 24868, 24869 | spinInnerClass; Lookup.ClassDefiner.defineClass | 23, 25 |

The fixture index gives the full method signatures. Immediately before r1's main
thread entry, events 24825/24826 are a balanced InvokerBytecodeGenerator byte-emitter
pair at depth 108. Before r2's main entry, events 24864/24866 are a balanced
ClassLoader.defineClass pair at depth 100. The background thread in both prefixes
is inside spinInnerClass -> ClassDefiner.defineClass, but thread IDs and depths
differ. The extra r1 thread is generating a customized LambdaForm; there is no
corresponding open call in r2. This does not establish the failing thread.

## Exact reproduction is blocked by missing observations

**Neither exact exception can be reproduced from its recorded stream.** Both
exceptions happen inside `atReturn`, before that raw breakpoint or its arm state
is emitted. The failed event has no collector sequence number. 24828 and 24871
would be speculative next numbers, not observed failure indices. The failing
thread, method, request, arm and live depth are unknown in both runs. The last
emitted entry is not necessarily on the failing thread.

r1 records no arm creation/deletion, MethodExit request identity, live return
location/depth, event-set ID/position or VM suspend/resume traffic. r2's stricter
guard also depends on all those absent fields. Its compound refusal does not say
which comparison failed: missing entry, wrong method, wrong depth or wrong top
location. `entry_depth` on a successful return is the saved **entry** value, not
an independent capture of all the live guard operands. Thread names and raw
exception events outside the candidate stack are also absent.

Replaying emitted successful records while inventing an ARETURN and exit for
each return would make the tests pass, but would not reproduce either failure.
The regression asserts `exact_exception_reproduced=false`, a null failure-event
index and `tracker_fix_proven=false`. It must not unlock a native window.

## Root-cause candidates tested against both prefixes

These ranks prioritize further investigation, not probabilities or findings of cause.

| Rank | Candidate | Evidence for / against; conclusion |
| --- | --- | --- |
| 1 | Event-set batching/order or suspension interaction | Both fail in return-arm handling amid multiple active generation threads. Sets and resumes were not logged, so neither ordering nor suspension can be tested directly. Insufficient evidence. |
| 2 | Re-entrant/recursive generation | Entry stacks contain the same selected method deeper in 2,014 r1 and 2,011 r2 entries. Recorded pairing still succeeds throughout. Re-entry exists, but is not shown to cause the failure. |
| 3 | Exceptional exit/unwind | Neither prefix contains a generation-unwind. Exceptions not producing a generation unwind were not logged unless relevant to a candidate. Absence of an unwind is not proof of absence of an exception. Insufficient evidence. |
| 4 | Arm installed after entry / stale arm | r1's error establishes an existing arm at the next arm attempt, but does not identify why it survived. r2's error does not identify which activation comparison failed. Arm/request traffic is missing. |
| 5 | Hidden/JIT-generated path | Both have InvokerBytecodeGenerator and hidden ClassDefiner paths, including similar open lambda definitions. Main-thread final paths differ. Generated frames are present; an unmodelled transition is not established. |
| 6 | Residual startup race | The old startup bug has a separate host reproduction, but native traffic lacks startup/resume evidence. r2 recurred after that correction, roughly 376 seconds into execution. The startup hypothesis remains unconfirmed for either native occurrence. |

**Identified native cause: insufficient evidence.** No speculative state-machine
relaxation is justified. Step 2's exact reproduction/fix proof is not green.
Step 3 diagnostic work can proceed offline, without claiming a native fix.

## Gate and effort

No new window is proposed or requested. Richer audit and host refusal tests can be
implemented offline; exact native reproduction remains an unresolved dependency.
Once a supported cause is reproduced, allow a focused implementation/test cycle,
fresh full preparation/freeze, and at least four hours of operator review before
the proposed latest start. There is no defensible completion time for the native
gate until the missing-transition problem is resolved. Code publication is not
qualification; merging requires Howard's commit-specific approval.
