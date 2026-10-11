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
