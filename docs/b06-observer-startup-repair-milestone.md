# B06 observer startup suspension repair — October 9, 2026

Status: offline correction and host regression verification complete. No replacement
native run, Docker commands, model calls, Tower request or authorization reuse.
The failed observer practice remains failed. Operator review, not independent attestation.

## Preserved practice outcome

Practice r1 started at 12:31:52 PDT and exited at 12:55:51 PDT, taking 1,439.859 seconds.
Oracle observer preparation took 655.766 seconds. Its worker started at 12:46:18 PDT;
the observer failed at 12:53:03 PDT, approximately 405 seconds into execution, before
the execution timeout. PostgreSQL execution did not start.

```text
java.lang.IllegalStateException: duplicate return arm
    at lightyear.observer.PostingObserver$Generation.atReturn(PostingObserver.java:194)
```

The signed terminal report is
`5ead361bc340074209dbcdecfc0779c0abd15e662f59d9e5d16de2aa87547ed1`.
The signed partial audit is
`000adebe75a6e911897392450161d34b51727303d635c0029a6ac303878a8c3c`.
It authenticates 24,827 Oracle events without claiming complete provenance, clocks,
execution or gate replay. The prefix contains 12,414 generation entries, 12,410
returns, two frame definitions and one ready event. Four generation calls remained
open across three threads. There were no completed posting checkpoints.

Post-terminal verification checked 13 campaign/native signatures and all 113,572
frozen file hashes. Read-only inventory confirmed no remaining resources under the
practice owner label. Cleanup's signed report also records eight checked resources.
Snapshot `cb142c2805b7d7d8947afbeae1026b6353cfbbac4f979890d8be3a71ee9ade13`
and all earlier evidence remain unchanged. There is no native qualification credit.

## Reproduced suspension defect

The collector installed its requests, emitted ready, called `vm.resume()`, and then
entered its event loop. The suspended target's initial `VMStartEvent` was still queued.
When that event was consumed, `EventSet.resume()` resumed the VM a second time.
If the target had reached a breakpoint between those calls, the second resume released
that breakpoint before the collector processed it. The return request could therefore
be armed after the intended method had already returned.

A host fixture holds the observer for one second after setup and before event dispatch,
exposing this legal scheduling interleaving. With the unchanged preserved old collector,
it fails with the exact native `duplicate return arm` exception after three events.
A separate diagnostic copy identified the stale arm as `ClassLoader.defineClass` and
the colliding return as `InvokerBytecodeGenerator.generateCustomizedCodeBytes`.

The same fixture with the corrected collector completes 1,012 events, four concurrent
generator threads and 160 byte-exact direct hidden definitions. Its generation
lifecycle replays with no outstanding entries. A small concurrent run, a low JIT
threshold run, and a larger unforced old-collector stress run did not reproduce the
error. The controlled scheduling regression, rather than generation count or JIT
threshold alone, demonstrates the defect. The native prefix did not record raw
VM-start/resume traffic, so it cannot independently prove the exact scheduling of
the failed native occurrence.

## Correction

- Remove the unpaired startup `vm.resume()`. The event loop resumes each received
  event set once, including the queued VM-start event.
- Arm a generation return only when the current top frame, observed entry, method
  and depth match. Store the exact pending activation with its exit request.
- Require the exit request, method, depth and pending activation identity to match
  before accepting return values or consuming the pending entry. An unexpected exit
  is an evidence failure instead of being ignored with a stale request left armed.
- Retain duplicate-arm refusal and report both armed and current methods. Require
  generation entries, arms and catch handlers to be closed before recording VM death.

No duplicate return is silently accepted. No class-name allowlist, proof normalization,
target attribution, candidate predicate, timeout, replay rule or trust policy changed.
The bulk-read and post-preparation watchdog corrections remain intact.

## Verification

- Six host regressions passed: delayed startup with concurrent generation; missing
  entry, wrong depth/request/method, replaced activation and duplicate-arm refusal;
  exact bounded byte reads; large offset/hidden definition fidelity; legacy/v2 recursive
  exception and generation lifecycle checks.
- The same delayed-start regression against the preserved old source failed as
  expected with the exact native error. The frozen old source was only read.
- A fresh production-collector host fixture completed 186 events and 10 checkpoints.
  Independent replay verified 62 frame observations, 22 bound Class identities and
  the generated lambda/LambdaForm target proofs.
- The 44-test proof/driver suite ran with that fresh capture: 43 passed, one optional
  historical pool-evidence test skipped. No skipped test is counted as passed.

Old Java source SHA-256:
`c47a8e28e4c3128856bab293dd28ec98d8a7705ec03125e40e3f1d5a63bd2b0b`.
Corrected Java source SHA-256:
`b5a7430383478985c8ad35185e312f4aeeaaf2d25b3c729f679247701292e99d`.
Fresh full host event SHA-256:
`7d4c36421a24ef5235f48a54cdefec1c059a881ffd1b06d34ce15c418b209e58`.
Public fixture outputs and diagnostic traces are retained locally under
`work/b06-return-arm-diagnosis` in the authority workspace. Native evidence remains
in its original frozen run directory.

These are Windows host checks on JDK 21.0.10, not a Linux native pass. Publication,
a new frozen snapshot and an exact Tower decision must precede another practice.
The prior plan, authorization and window do not authorize these changed bytes.
