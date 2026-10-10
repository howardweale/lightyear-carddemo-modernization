# B06 structural audit extension — October 9, 2026

Status: prospective diagnostics implemented and host-tested; **native cause and
tracker correction remain unproven**. This does not authorize a native launch.
Howard has [amended the diagnostic gate](b06-diagnostic-gate-amendment.md), replacing
the impossible historical exact-event reproduction prerequisite. See [the preserved-stream findings](b06-observer-offline-findings.md)
and the [design-only degradation proposal](b06-observer-degradation-proposal.md).
No Docker, native pairs, Tower requests, model calls, machine configuration
changes, private-key reads or historical-evidence edits occurred in this work.

## What changed

The collector announces `structural-jdi-v1` and emits bounded diagnostics through
the existing external collector stream. The existing broker hash chain and signed
census/failure commitments therefore cover these records too. They are diagnostic
observations, never a substitute for class bytes, target attribution, SQL readbacks
or the complete gate.

For each event set it records its monotonic ID, size and actual suspension policy;
each raw event gets its iterator position, event type and local request identity
before dispatch. Locatable events include thread ID, class/method/signature/code
index, live frame count, top location, generation selection, return/catch request
flags, pending generation identities and the currently armed request/activation.
After dispatch it records the resulting pending IDs and arm. A refused dispatch
records the exception class and rethrows it. It does not resume or continue past
an anomaly. The actual refusal context is flushed before executing the guard.

Thread names are target-controlled and may contain private values. The stream
records their SHA-256 identity, **not plaintext names**; a host test uses a private
sentinel name and verifies it is absent. This is an explicit privacy tradeoff
against the requested name field. No argument, return-value, class-blob or object
graph capture was added to the diagnostic records. Structural locations do not
call the existing bytecode/constant-pool evidence collector.

VM-start and terminal events are recorded, along with requested/completed
EventSet resumes. The actual suspend policy describes the corresponding event
suspension. No extra suspend/resume is introduced. Per JDI, ordinary
[MethodExitEvent](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/event/MethodExitEvent.html)
does not represent an exceptional exit, so those records say `exceptional_exit=false`.
Exception events include their catch location and `unknown-until-handler`; existing
generation-unwind evidence establishes what the handler actually unwinds.
[EventSet](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/event/EventSet.html)
position is delivery order, not a fabricated global execution ordering across threads.

## Bounds and replay

The original maximum of 50,000 non-audit evidence records is retained. A separate
diagnostic allowance is capped at 500,000 records and 128 MiB of audit bodies per
collector, with no more than 256 pending generations in a diagnostic state.
Existing per-line limits remain. The collector and broker refuse budget exhaustion;
replay enforces the same allowance and keeps the evidence-event cap separate.
These are finite diagnostic bounds, not a promise that a full native run fits.

Replay validates audit policy, index continuity, set/position continuity, resume
ordering, startup/termination and refusal state. A refusal cannot be marked
complete. Old streams without the policy keep their existing replay behavior.
New diagnostic records never relax generation-entry, return-arm, exit identity,
catch, open-call-at-death or full provenance predicates.

## Verification and overhead

- Both hash-pinned native structural fixtures replay their recorded pairs and
  explicitly retain `exact_exception_reproduced=false` and `tracker_fix_proven=false`.
- Six existing host regressions cover delayed startup/concurrency, exact arm
  refusal, bounded byte reads, large/hidden definitions and legacy/v2 recursive
  exception handling. All passed.
- Thirty focused tests cover the new audit, native prefix projection, posting
  replay/controls, qualification driver and closed v2 policies. All passed.
- A temporary host-only fault clears a pending activation just before the existing
  guard. It reproduces the guard's exception and verifies that the raw event,
  thread, method, depth, request, top location and prior pending state were emitted
  before the refusal. **This injected fault is not the native root cause.**
- Order, missing-requested-resume, count/byte bounds and attempted completion after
  refusal are negative tests. Thread-name disclosure is also tested.

[Measurement metadata](b06-observer-audit-overhead.json) compares unchanged
`8031ad1` with the audited collector on a public host lambda fixture. Two samples
per variant, alternated baseline/audit/audit/baseline: median wall time rose from
0.9343 to 0.9797 seconds, approximately **4.9%**. Compilation is excluded; startup
is included. Original evidence count remained 168; audit added 1,263 records and
416,559 body bytes. Output grew from 1,064,382 to 1,528,749 bytes. This small Windows
Corretto 21 result has substantial timing uncertainty and is not a Linux/native
overhead bound. The earlier intermediate instrumentation measurement is not used.

## Remaining work and next-window gate

The evidence does not identify the failed raw event in either historical run.
The current tracker was not changed speculatively. Under Howard's amended gate,
a completed host stress experiment that does not reproduce either refusal permits
preparation of one diagnostic native window. It requires a fresh freeze, delivery
of the full plan at least four hours before latest start, and fresh Tower and
Docker approval. Strict stop at first anomaly stays in force; no degradation or
qualification credit is allowed. A failure captured by that run must be reproduced,
fixed and proven offline before any qualification window. The richer audit is
currently **not in an authorized frozen build**.

This diagnostic draft and the findings PR can be reviewed now. Merge requires
Howard's approval for the specific commits. It must not be described as completing
the requested native observer fix.
