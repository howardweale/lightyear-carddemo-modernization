# B06 r3 offline performance repair — October 9, 2026

Status: implemented and tested locally; native census remains incomplete.
Zero Docker commands, database runs or model calls. No new Tower request or
replacement execution snapshot. Operator review, not independent attestation.

## Preserved failure and limits of diagnosis

R3 window2's signed terminal report is
`eb19052ae94619234c8308ee1421c2a903a39ec0c066382fc157168bc4c57c58`.
The first retained J1 slot ended in equipment failure; four slots were never
started. Total duration was 2,212.687 seconds. The signed partial audit
`cfa692b5cd77057dfd67d045206ac44c5ae36e12970d323e0b191cca086c004e`
authenticated 7,485 Oracle events but grants no completed-stage or provenance
claim. There were 3,742 generation entries, 3,741 returns, one ready event and
one frame-definition event; no posting checkpoints. Snapshot
`72e28a5ccec6ac4bb61362b6d0c81269be927e4324c2941d299bd3492da9703b`
and all earlier failures remain unchanged. Post-stop verification checked all
113,634 frozen file hashes, 12 top-level campaign/native signatures and actual
absence of owned containers, networks and volumes for all five owners.

Exact collector exception:

```text
Exception in thread "main" com.sun.jdi.VMDisconnectedException
    at lightyear.observer.PostingObserver$Generation.enter(PostingObserver.java:196)
```

The intervening JDI frames are `ArrayReferenceImpl.getValue/getValues` and
`JDWP$ArrayReference$GetValues`. The error is a lost target connection during
collection; it does not independently identify why the target disconnected.

Saved timing (UTC): candidate admission 17:35:00.497772; first observer ready
17:45:47.341696; last event 18:05:33.424685; collector failure record
18:05:33.554056. Thus observer preparation used about 647 seconds before ready.
The old host watchdog started before `broker.start()`, with a 1,830-second
limit. Failure closely follows that deadline, after only about 1,186 seconds
of observation. The saved worker exit status and `built-after.json` are absent.
Watchdog-induced stopping is the strongest code/timing explanation, but the
old controller did not preserve the initiating stop reason, so this report
does not claim it as proven or exclude every other cause of disconnection.

## Corrections

1. `PostingObserver.readBytes()` reads suspended-VM arrays in at most 16 KiB
   chunks. It checks exact slice bounds, the existing 1 MiB maximum, returned
   lengths and byte values. Ordinary definitions, hidden-definition inputs and
   generator return arrays all use it. Method-handle graph arrays also use one
   bulk array read. Full bytes, hashes, events, loader identities, method reads,
   capture bounds, suspension and target-proof requirements stay intact.
2. `ObservedRunner` starts its execution watchdog immediately before launching
   the application worker, after observer preparation. The worker's 1,800-second
   timeout and host's 30-second allowance remain unchanged. The independent
   slot supervisor and signed window still bound preparation and execution;
   `check_cancel()` runs again before worker launch. Overall elapsed reporting
   still includes preparation. No candidate predicates or expected outcomes change.
3. Private host lifecycle events explicitly record preparation start/completion,
   worker launch/return, host watchdog expiry, failure type and application stop
   request. They contain no credentials, candidate prose or exception messages,
   and confer no verdict. They are retained with the existing native evidence.

The saved prefix contains 3,469 byte-array captures requiring 15,539,704
single-byte read calls in the old collector. The same slices need 3,723 bounded
batch calls. This calculation excludes other JDI work and uncompleted reads;
it is not an estimate of total native execution speed.

## Offline validation

| Check | Result |
| --- | --- |
| Exact slice transport | Empty/nonzero offsets, chunk boundaries and 1 MiB preserved; 1 MiB takes 64 calls |
| Invalid input | Negative/oversized/out-of-range slices and short reads refuse |
| Same real-JDI large-class fixture, old collector | 10.594 seconds; 34 events; five exact definitions |
| Same fixture, corrected collector | 0.625 seconds; 34 events; same five definitions and SHA-256 |
| Old watchdog reproduction | 1,200 seconds setup + 800 seconds execution incorrectly raises `CandidateTimeout` |
| Corrected watchdog tests | Slow setup passes; real expiry, observer failure and closed window still stop; cleanup checked |
| Focused batch/worker suite | 17 tests passed (two batch/JDI and 15 worker tests); diagnostic-write failure cannot skip cleanup |
| Real host lifecycle regressions | Legacy/v2: 300 lambda factories, direct hidden class, recursive exceptional unwind passed |
| Fresh full host fixture | 186 events, 10 checkpoints; 1.563 seconds |
| Independent full host replay | 62 frame observations, 22 bound Class identities; lambda and LambdaForm proofs passed |
| Proof/delivery/driver suite with fresh host capture | 43 passed; one optional historical pool-evidence test skipped |

The timing comparison is one bounded host fixture per implementation, not a
native performance guarantee. Host collection uses public fixtures with no
database readback. Native admission remains false. The reviewed pool comparator
was not changed; the unavailable optional historical pool test is not counted
as passing. A first sandboxed test invocation could not access Windows temporary
directories; the same host-only tests then passed with execution permission.

Corrected Java source SHA-256:
`c47a8e28e4c3128856bab293dd28ec98d8a7705ec03125e40e3f1d5a63bd2b0b`.
Fresh full host event SHA-256:
`f63b57833f38076d2e42718274f6a306df21fe5b1aca06ddf059cb20ba74ebcd`.
Local diagnosis report SHA-256:
`21970b261b7452ce8075315251d810d7f60f5a9a5d77310f8155b0218bc93ad5`.
Raw evidence and host rehearsal outputs remain local.

## Preparation time and next boundary

A read-only profile of 500 spread-out saved class entries took 0.675 seconds:
0.387 seconds in bound-file checks and 0.260 seconds parsing classes. This is
a sample, not a full-manifest timing; it does not justify bypassing validation.
Repeated full manifest validation is visibly performed at separate assembly,
freeze and broker admission boundaries. No persistent cache, weaker hash check
or signature shortcut was introduced. Further reuse would need to preserve
fresh file authentication and exact input/implementation bindings.

The correction is ready for review and a separately authorized bounded native
practice on newly frozen bytes. That practice must show startup and target
proof completing within budget before another five-path evidence run. This
document neither authorizes that practice nor changes an existing Tower decision.

## Follow-up: frozen single-pair practice prepared

The corrected source was published as `f18cb1e06ca5e6bb1e71ef241402a0fea9ee4dd8`
on draft PR 287. [Practice r1](calibration/idempiere-ms94/stage-b-06/preparation/observer-practice-r1/README.md)
completed full offline preparation at 19:07:13 UTC: 113,572 frozen files, 767
public source comparisons and 39 frozen tests passed. Its October 9 12:30–15:30 PDT
window has a latest full-budget start of 13:20:10 PDT. Publication and an exact Tower
request precede any launcher arming. No Docker/native/model calls have occurred in
this preparation, and no qualification or measurement credit is claimed.
