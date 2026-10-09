# B06 observer-v2 integration and generated target proof

Status: offline implementation and host proof passed. **Not Oracle/PostgreSQL qualification.**
Operator review; not independent attestation. No model calls, Docker commands,
native pairs, new Tower decision or measurement launch.

Report content hash: `ec0fdb9401a2db462999495a1860c332410bb7b1de78f454b4c2e32cdcc60941`.
The [hash-only report](report.json) binds source, compiled collector, captured
stream and independent replay. It is a content-hashed development report, not a
new signed operator authorization. Raw captures and class files remain local.

## Implemented boundary

- Explicit `observer_binding_v2` plan opt-in, with a bound
  `b06-observer-bindings/2` manifest. Historical replay remains on its old path.
- External JDI collection of ordinary `ClassLoader.defineClass` bytes, actual
  returned Class, loader and protection-domain origin; module and loader-class
  identities; full pool/method/field material at observed frames and catches.
- JDK generator entry/return/unwind lifecycle; LambdaForm emission array to
  definition array to returned Class; method-handle graphs from arguments and
  receiver of the actual suspended frame. No target method invocation.
- Every ordinary frame requires exact artifact/module bytes, methods and flags.
  The only non-JDK pool exception is the approved exact HierarchicalTestEngine
  rule, including its byte-bound TestEngine interface. The generalized overpass
  proposal is not imported or enabled. Ordinary JDK material comes from
  `lib/modules`, not development `jmods`.
- Lambda host, invokedynamic/bootstrap, recipe, capture layout, loader, body and
  immediately younger target agree. Candidate/support/outside remain distinct.
- LambdaForms require pinned generator origins, exact emission/definition,
  class-data initializer, full expression/body replay and a unique actual target
  in younger frames. All intervening frames are checked; an opaque handle,
  competing target, missing adjacent lambda target or unknown helper refuses.
- The broker hashes runtime files before candidate startup: Java executable,
  module image, release metadata, JVM/native providers and class/artifact files.
  Actual executable path, exact argv, option environment, read-only root/mounts
  and unchanged built-runtime bindings are required. Boot/module patches and
  extra agents/native-library options refuse. The executable freeze includes
  the manifest and every local class/archive input used by replay.
- Signed collector receipt/census commitments cover all v2 records and events.
  Definition refresh invalidates cached proofs. Missing or truncated material
  cannot become a completed result or a trusted frame.

### Captured data is not executable authority

`invokeWithArguments` used a generated `BoundMethodHandle$Species_LI` capture
holder. Its two final instance fields are checked against the ClassDefiner input
bytes, returned Class and JVM-read full layout. Only the verified instance field
read is used as captured data. No constructor, initializer, invocation, static
field or write receives trust from that rule. The holder still **fails** ordinary
frame admission. Tests cover this distinction. There is no species/lambda name
allowlist and no automatic approval of other generated executable recipes.
Unsupported proxies/accessors/other generated executable forms remain fail-closed.

## Validation

The actual production `PostingObserver` attached to fresh public host fixtures:
three role-specific lambda paths, `invokeExact`, and `invokeWithArguments`.
The fixture's PO/support methods perform **no database work** and cannot stand
in for the retained reference or any native verdict.

| Check | Result |
| --- | --- |
| Final capture | 186 events; 10 entry/exit checkpoints; 2.859 seconds |
| Independent replay | 62 frame observations; 22 byte-bound Class identities |
| Generated proof occurrences | 6 lambda and 6 LambdaForm (entry/exit observations, not 12 independent trials) |
| Offline B06 test suite | 201 passed, zero failed; includes 18 v2 tests and adversarial subcases |
| Additional real JDI lifecycle test | Passed: 300 factories, direct hidden class, exceptional definition unwind |
| Final compilation | All 9 observer/fixture class files byte-identical to tested bytes |
| Separate closure-agent fixture | Skipped on this Windows JDK because process command/arguments are unavailable; not counted as passed |

Final event SHA-256: `f9af3776f9aa29f3ea6735b5cac80a72a97daf7952bfe2a1c08ee2be055907a3`.
Independent host replay file SHA-256: `ca778a7720ce0646a4877e84dbba068a097ff025967c2d3b933e8093239a8eec`.

Wrong host, loader, origin, return identity, pool, code, flags, missing younger
frame, missing/opaque handle graph, altered field layout, stale proof reuse,
missing signed commitments, JDK patching and runtime-file changes are tested.
The two saved real HierarchicalTestEngine pool orders also enter the native
ordinary-binding path under the approved comparator.

Earlier host attempts and failed replay reports remain intact. The first host
replayer incorrectly used a development jmod placeholder for
`DirectMethodHandle$Holder`; the actual module image contains the exact executed
method. A separately retained `-Xshare:off` experiment did not fix that wrong-input
comparison. Native launch arguments were not changed. Subsequent replay gaps for
generated dispatch members/capture-field dependencies were implemented and tested;
failed reports were not rewritten. The older closure-agent test double was
updated to its current metadata API; its separate Windows process-metadata
limitation remains explicitly unverified.

## Remaining native gates

This proves the collector/replay mechanism on Windows public fixtures, not the
Temurin/Linux iDempiere runtime. The five-path native census still needs its full
per-slot v2 manifest, compiled observer closure, fresh executable snapshot,
public commit verification, exact window and signed Tower decision. It must cover
J1's three paths and J2/J3 retained references on both engines. Qualification and
measurement remain gated; unfamiliar generated forms must preserve their census
and halt rather than expand trust during execution.

B04 remains void; B05, `work/ms94`, template-r1, J1 business predicates and all
frozen/historical evidence were not changed.
