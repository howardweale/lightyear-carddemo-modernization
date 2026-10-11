# B06 engineering JDI mirror adapter

This offline implementation preserves the engineering hold. It grants no native,
qualification, measurement, or model authorization. It does not prove the full
192 MiB flat-heap or transient-peak criterion by itself.

## Why an adapter is required

Corretto 21.0.10+7 JDI keeps every known ReferenceType in two strong caches,
VirtualMachineImpl.typesByID and typesBySignature. Public JDI has no cache-clear
operation. Resetting retrievedAllTypes is unsafe: JDI treats it as monotonic and
reads it without synchronization before deciding whether a cached name query is
complete. Removing entries while that flag is true could silently hide classes.

BoundedJdiMirrors is a deliberately narrow engineering adapter. It requires the
actual bytes of seven implementation classes to match its compiled-in hashes.
Those hashes were measured from the installed Windows Corretto 21.0.10+7 JDI
module. A Linux runtime with different bytes is unsupported and must refuse;
version text alone is insufficient. No Docker image was inspected or changed.

## Integration contract

Compile factory/idempiere/b06-observer/BoundedJdiMirrors.java alongside
PostingObserver.java into the observer class directory and bind every resulting
class file in the plan. Add the observer-only JVM argument:

```
--add-opens=jdk.jdi/com.sun.tools.jdi=ALL-UNNAMED
```

For bounded engineering mode only, construct BoundedJdiMirrors immediately after
attach. Bootstrap each exact watched class name with vm.classesByName(name),
not vm.allClasses(). Pin every configured watched type with adapter.pin(type).
After processing the complete suspended EventSet, and before resume, call
adapter.prune(activeTypes). Include types used by pending activations and live
requests unless they are already permanently pinned. Merge adapter.telemetry()
into signed observer heap telemetry. Legacy observer modes do not use this path.

The adapter never changes retrievedAllTypes. An unexpected full-enumeration
operation refuses before pruning. Do not call allClasses or indirect enumeration
APIs such as nestedTypes, subclasses, implementors, or definedClasses. Do not
redefine classes. This adapter is not a general debugger compatibility layer.

Both caches are checked and updated under the VM monitor. Prepared inactive
mirrors are removed only when their cache exceeds 1,024 entries, down to 512 or
the number of pinned entries if larger. Unprepared and explicitly pinned mirrors
are retained. More than 1,024 necessary pins refuses instead of silently dropping
active metadata. ReferenceType, Method and Location equality retain VM/type/method
identity across recreated mirrors. We do not modify JDI object-reference caches,
object-disposal requests, target state, or archived observer evidence.

The reported peak before pruning includes transient query/event materialization.
Full-query result sizes and references held elsewhere remain separate peak risks;
a bounded cache count is not a bound on the complete process. Pin/bytecode/access/
invariant refusals must become explicit stopped-run evidence, never fallback.

## Host validation

Set B06_HOST_JDK to the pinned JDK and run:

```
python -B -m unittest tests.test_b06_jdi_mirrors -v
```

Two host tests passed on October 11, 2026 in 2.483 seconds. The real JDI fixture
uses four threads and 1,300 separately loaded classes sharing one binary name.
It verifies complete exact-name results after eviction, type/method/location
identity, active and unprepared retention, prepare/unload/reload handling,
concurrent prepare traffic, both-cache consistency, oversized-pin refusal,
full-enumeration refusal without mutation, missing module-access refusal,
unsupported implementation refusal, and a deliberately wrong bytecode pin.
It does not run the native application, Docker, a database, or model calls.

## October 11 addendum: preserved image bytes and unknown status

Read-only verification of preserved manifest
`2b4bf062bc205bb9081f54814fcbb756069ca0b6ff6bedbbec6d0d3e5e6cbe08`
found that all seven public JDI class hashes for retained image
`sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`
match the adapter pins. Each public class blob was independently hashed against
both the manifest and the adapter. The hash-only record is
[engineering-jdi-mirror-compatibility.json](calibration/idempiere-ms94/stage-b-06/preparation/engineering-jdi-mirror-compatibility.json).
This supports expected byte admission, not a live runtime verification. No
container was queried or launched; the constructor must check actual bytes again.

The first integrated host experiment stopped on the mirror pin limit. A recreated
JDI mirror has `isPrepared=false` with `status=0` until public `isPrepared()` asks
the target for its status. Treating UNKNOWN as permanently unprepared retained
mirrors unnecessarily. Before an over-cap prune, the adapter now snapshots
unknown mirrors under the VM monitor, resolves them through the public read-only
status API outside that monitor, then rechecks both caches before any removal.
Known unprepared mirrors remain pinned; no status is fabricated. Telemetry counts
these status queries. The strengthened fixture repeatedly recreates 1,300 mirrors
through actual ClassObjectReference.reflectedType calls. Both focused host tests
passed in 2.533 seconds. These tests establish adapter behavior, not the full
native-volume memory criterion. The earlier stopped experiment remains preserved.
