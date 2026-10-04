# B06 posting observer preparation

October 4, 2026 UTC. Operator review, not independent attestation.

This increment implements collection and offline integrity replay for a prospective
posting-origin observer. It is **not qualified causal attribution**. No native
qualification pair, JVM attachment or model call was performed. Diagnostic
forwarding and qualification credit remain unavailable on this new path.

The preceding J2/J3 adapter increment was merged through
[PR #241](https://github.com/howardweale/lightyear-carddemo-modernization/pull/241)
at `538c0829766ca3d0d0611a46f7a06bbbaba2eba5` after all 25 checks passed.
Its preparation manifest remains
`c3c2ef4e32520f9373d4d0a6805dae94c6cd8ae79a1ddc49854440c8fdc69c33`.

## Implemented boundary

The B06-only application worker starts the target JVM with JDWP suspended on an
internal Docker network and no published port. The host broker identifies its
listener through Linux `/proc`, binds the Java executable, and attaches an
external JDI collector before permitting candidate execution. The listener probe
does not open a test connection that could consume the debugger handshake.

The collector reads real method arguments, document identity, stack frames,
executed bytecodes, constant pools, normal returns and exceptional unwinds. It
does not invoke target methods or consume candidate-authored trace messages as
provenance. While the VM is suspended at each document checkpoint, a separate
trusted process reads the native document and accounting facts. Only the host
broker writes the chained event stream and signed collection receipt. These
private records are not public publication artifacts.

Offline collection replay checks full entry admission, signed receipt bindings,
event hashes and chain, lifecycle, call/return pairing, unwinds, compiled method
identities, class loaders and exact SQL readback bindings. A collection replay
does not prove the cause of a failure and returns no diagnostic. A missing entry
replay cannot be converted into a completed replay flag by an early business
exception. The existing J1 business predicates and template-r1 are unchanged.

## Validation and costs

- 50 B06 preparation tests passed on Windows, covering the adapter and observer
  boundaries. Synthetic fixtures are unit inputs, not native evidence.
- The current observer Java source compiled successfully in the pinned image
  without network, database execution, JVM attachment or model calls. The
  compiler container was actually absent after cleanup.
- All three observer compilation attempts succeeded and remain preserved.
  Their times were 3.281, 3.282 and 3.062 seconds, totaling 9.625 seconds. They
  are separate from the J2/J3 reference compilation total of 111.969 seconds.
- An initial unit test expected FileNotFoundError for a missing JSON file. The
  existing reader wraps that error as ValueError; the test was corrected and
  the suite passed. This was not a native qualification attempt.
- Overall preparation wall time was not measured. Native qualification and
  independent native replay costs are zero for this increment.

The [manifest](manifest.json) binds the implementation, tests, current Java
source and hash-only compiler metadata. Reference sources, compiled target
classes, captures, compiler logs, private expectation values and keys are not
included in this publication.

## Remaining admission work

1. Native J2/J3 acceptance, exact per-pair plan assembly, sequence ownership and
   the additional J3 comparison-register admission still require completion and
   fresh qualification. Compilation does not establish native acceptance.
2. Bind complete target class catalogs to trusted compilation and the pinned
   image. Finish terminal exception identity, native document-label resolution,
   causal proof derivation and genuine equipment-fault exclusions. Prepare and
   qualify prior-post, prior-lock, support, outside-origin, wrong-document and
   equipment-fault controls on both engines. Collection alone is insufficient.
3. Freeze exact J1/J2/J3 qualification plans, source/mutant hashes, images and
   diagnostic expectations in a separate PR; stop for approval of that plan
   commit before running any native qualification. No plan freeze is claimed here.
4. Complete and qualify the multi-journey measurement executable and its signed
   per-attempt archive, replay and terminal reporting integration.
5. Run the supervised, immutable, three-journey zero-model preflight only after
   the preceding admissions, including Tower decisions and verified cleanup.

The pinned `PO.lock()` changes the native Processing flag; it is not proof of a
SQL row lock. Unchanged `JourneySupport.postOnce` skips a document already posted.
Therefore prior posting alone must not be assumed to cause a repairable failure.
The qualification expectations must preserve that distinction.

B05 remains closed and frozen; B04 remains VOID. No work/ms94 files or frozen
template files were changed. No native run or measurement launch is authorized
by merging this preparation. Any Docker work requires permission and must not
overlap the October 5 CardDemo intake.
