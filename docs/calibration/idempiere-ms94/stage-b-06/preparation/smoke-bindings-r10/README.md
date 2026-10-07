# B06 smoke r9 diagnosis and prospective correction r10

The r9 J1 smoke failed as equipment-suspect. It remains failed; no verdict,
signature or frozen file has been amended. This increment corrects preparation
and replay code offline. It creates no executable freeze, Tower authorization,
Docker window or measurement permission. Operator review, not independent
attestation. Zero model calls, Docker commands and new native pairs.

## Preserved outcome

The group started at 2026-10-07T04:12:56.987519Z and stopped the retained-reference
slot at 04:23:52.471960Z. Terminal elapsed time was 714.047 seconds, including
failed finalization and cleanup recovery. Both candidate processes exited zero,
which does **not** establish a business pass. Zero slots finalized successfully;
the duplicate-invoice-line and candidate-null-dereference slots never started.
The controller's archive replay rejected the same observer identity mismatch.

| Binding | SHA-256 |
| --- | --- |
| Failed executable snapshot | `a9a532df45a0db27602da668394437dc3efd189143eaec32ef336073ab7e6c70` |
| Signed terminal report | `8e8ae1024f77a9a7e3cbda7daf04c25da5248287d9863488c35257ef3ddf6888` |
| Signed native receipt | `ec56e6066b9ad75660cc277ad1c401e5edb8fda6df99f6fcf22aaaefade4a680` |
| Offline diagnosis | `f76eb8a32ce21ee63bdbc8808d0f6a007175c6d7bce74efaf32eb618c3446e7a` |

The preceding status check verified all 11 owned Docker resources absent and the
signed cleanup records. This correction rechecked all 2,106 frozen input files,
terminal/native signatures and saved observer event-file hashes read-only.
Archives, raw captures and private inputs stay local.

## Causes and corrections

1. **Instrumented runtime versus uninstrumented catalog.** The signed native
   process records for both engines contain the JaCoCo 0.8.10 `-javaagent`.
   The earlier runtime-resolution agent recorded class bytes before JaCoCo's
   later transformation. The external JDI collector observed executing methods:
   23,075 checked frames on Oracle and 17,906 on PostgreSQL differed from the
   catalog, spanning the same 28 classes and 81 methods. The check correctly
   refused to treat these as the bound original bytes. Both recorded JVM argv
   hashes are equal. No transformed-byte reconstruction or equivalence claim is
   made from the old hashes alone.

   The prospective B06 worker supplies `-Djacoco.skip=true` and clears
   `tycho.testArgLine`. It still executes the test and starts suspended for JDI.
   [JaCoCo documents both the Tycho property and skip switch](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html).
   The plan must declare `untransformed-classes-jdwp-only-v1`. Before attaching,
   the broker checks the actual host-read JVM command and permits only the exact
   suspended JDWP agent. It rejects any Java/native agent, duplicate JDWP,
   unexpanded argument file, wrong Java binary, missing policy or nonempty
   `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` or `_JAVA_OPTIONS`. The launcher
   removes those option variables; the listener records names only, not values.
   Offline replay repeats admission from the signed collector receipt. Existing
   constant-pool/method hashes and loader checks remain strict and unchanged.

2. **Purchasing register selected for J1.** The r6 private-input assembly used
   `idempiere-declared-purchasing-comparison-v4-ms94` for every journey. J1's
   unchanged combined judge requires `idempiere-declared-comparison-v3`.
   The inventory hashes matched; the register version was wrong. The native gate
   therefore recorded `Register inventory/version differs`.

   Selection now uses J1's original repeatability register bytes, keeping the
   purchasing register for J2/J3. Private assembly v2 validates the full original
   validator, inventory, rule scope and assessment date before writing, and
   revalidates on readmission. Plan assembly checks the content-hash binding;
   native entry checks it again. No register is relabelled and no J1 predicate
   changes. Fresh local manifests cover the 55 J1 qualification slots and the
   three smoke slots; only their register input bytes differ. Source hashes and
   every other input are preserved. Assessment date: October 7, 2026; scenario
   dates remain October 1. Prior assemblies stay immutable and are superseded
   only for prospective preparation, not retrospective claims.

3. **Latent archive replay layout error.** The finalizer extracted a run at
   `<temporary>/<run>` although the unchanged J1 judge derives its repository
   root from `<root>/factory/idempiere/ms86-journeys/runs/<run>`. A scratch-copy
   diagnostic exposed missing public-contract context; it made no qualification
   claim and did not repair signatures. The prospective finalizer now restores
   the proper layout and copies exactly two snapshot-bound public contracts and
   the matching public verification key. It copies no private key. Replay still
   uses the frozen implementation/class bindings and only rewrites the extracted
   gate; original run and archive bytes remain untouched. Freeze refuses J1
   snapshots missing these replay dependencies.

## New input bindings

| Input | SHA-256 |
| --- | --- |
| Correct J1 register file | `0f10b3fad375016f52e1001caf2d7015e091832c4ffe09f3837e80ec28a5f60c` |
| Correct J1 register content | `c8b7406882117b9987b01b34a10072a951cf5ae3831a39f18595116372db1516` |
| [55-slot hash-only input manifest](j1-private-inputs.json) | `cc91aa313cb22e3f75d0fc174851a0481303a4f827310fa674501f680eae54eb` |
| [Three-slot hash-only smoke input manifest](j1-smoke-private-inputs.json) | `26cae135f094611aeba8376ac5b8c077b508368b8a9e06441c8674e8a007d2d2` |

## Validation and next gate

Offline regressions cover full register validation, wrong version/inventory/scope,
expiry, rehashed wrong-register inputs, early refusal without creating a slot,
actual-JVM agent refusal before attach, missing/unsafe JVM environment evidence,
archive root inference, public-key matching, bound public-file corruption,
unchanged candidate inputs, and direct candidate diagnostic delivery while
support/outside-origin failures remain empty and equipment-suspect.

The initial restricted-shell test invocation could not create Windows temporary
files; the same tests passed with normal temporary-directory access. No ACL or
security-setting change was used. The full B06 offline suite passed **149 tests
in 31.099 seconds**. This is not native qualification or proof that the corrected
uninstrumented target will match every bound class.

All nine milestone-documentation tests also passed (2.286 seconds), and
`git diff --check` passed. The 291 inherited calibration/non-B06 tool files match
the failed snapshot. Sixteen unrelated graph/Tower source differences already
exist in this checkout's committed history and were not changed here. A future
executable assembly must retain its explicit dependency bindings rather than
copying the entire current checkout into the qualified runtime.

A fresh executable snapshot/plan and exact Tower decision must bind these
equipment changes and a newly approved Docker window before another native
pair. The old window expired. No restart, replacement slot, model call or new
measurement is authorized by this correction. B04 stays void; B05, template-r1,
J1 predicates and historical qualification evidence are unchanged.
