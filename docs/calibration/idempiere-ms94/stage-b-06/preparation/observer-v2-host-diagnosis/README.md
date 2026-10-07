# Observer-binding v2: conditional approval and host-JDK diagnosis

Operator review; not independent attestation. Zero Docker commands, native
Oracle/PostgreSQL pairs and model calls. No J1 predicate, expected outcome,
production comparator or frozen evidence was changed. r10 stays failed.

Latest follow-up: Howard requested "run smoke test asap" after the exact pool
proposal. That go-ahead is interpreted as approval of that proposal, recorded in
[expedited readiness](expedited-readiness.json), not as a fabricated Tower
decision. Six host tests now pass, including method access-flag rejection. The
original five-test report below is historical; the follow-up binds the revised
diagnostic evaluator. Production admission is still unchanged. Full generated
provenance, the five-path executable freeze and an exact Tower decision/window
remain blockers. No smoke was launched.

Howard approved the original observer-binding v2 file
`a6ae76dee979c59badeec20630b54e83dbcaddc85d8467ff3d4e1adb9d4b8898`
with four conditions on October 7, 2026. That original file stays byte-identical;
its historical PROPOSED label is superseded by this separately recorded conditional
approval, not silently edited. The narrower r11 forwarding-only snapshot and its
three-slot pending Tower request do **not** satisfy the new five-path census scope
and must not be launched under this approval.

## 1. Exact r10 pool mismatch reproduced offline

The retained extraction contains identical class bytes for
`HierarchicalTestEngine` from JUnit Platform Engine 1.9.1 and Tycho's
`surefire.junit59` 4.0.8 JAR:
`b6ebf7618c7572195ec833104be65f54aaa090263dc14297bd471f9c4a1cd056`.
The whole JAR files were not retained. These exact class entries and saved
framework dependencies were materialized into two plain host classpaths. No
framework class was recompiled or downloaded.

The standalone public fixture executes only an empty JUnit hierarchy. A separate
JDI observer reads the real class at preparation, after loading, after subclass
construction, after linking its `createThrowableCollectorFactory` invokedynamic
site, after invoking the resulting factory, and after empty engine execution.
The observer invokes no target method. The fixture itself exercises the real
unmodified framework methods. There is no application, candidate or database run.

Three host experiments completed, each with five checkpoints plus class
preparation, in 7.146 seconds total measured observer time:

| Experiment | Raw JDI pool at every sample |
|---|---|
| Surefire entries, baseline | `0f499ea8ec104321fdf6326ddb822cfbb2aac85404b60df517572c9d20bba8b2` |
| Platform 1.9.1 entries, baseline | `b6eb2698546644b688cf9fc195a7445dff77fea21a0de5125e5f929440e14411` |
| Surefire entries, dump enabled | `b6eb2698546644b688cf9fc195a7445dff77fea21a0de5125e5f929440e14411` |

The latter hash is **exactly r10's observed hash on both engines**. In every
sample, the original class-file pool bytes (`9be5af71…`, count 145 including the
reserved zero index) form an unchanged prefix. HotSpot appends 14 entries, giving
count 159, associated with AbstractMethodError overpass handling for inherited
abstract `getId()` and `discover(...)`. The two raw hashes differ only in which
method's extension entries occur first. All five declared method identities and
all four concrete bytecode hashes remain exact. `execute` remains `4e8ecde3…`.

Thus the mismatch is explained by HotSpot class preparation/reconstitution,
**not lambda linkage changing the original pool**. It already exists at class
preparation and does not change across the tested linkage/execution stages.
The mechanism matches OpenJDK's
[default-method processing](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/classfile/defaultMethods.cpp)
and [constant-pool reconstitution](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvmtiClassFileReconstituter.cpp).
These sources explain the experiment; observed bytes, not source-code prose,
establish the exact hash reproduction.

Host JDK: Amazon Corretto 21.0.10. Pinned image: Temurin 21.0.10+7-LTS.
This vendor difference remains a limitation. Host results are not a new pinned
image admission or retrospective native replay pass. Compilation emitted warnings
because the saved classpath lacks API Guardian annotation definitions; warnings
and both compiler streams are retained. The actual engine class bytes were unchanged.

Report content hash:
`73f462e3378fc2385087c05869130c9d61e15df0cb46092c7ac0382348e3bcf9`.
Raw observations, copied framework entries and process streams remain local under
`work/b06-observer-v2-host`. The report intended for public review contains hashes
and findings only; these new files have not been committed or published.
[Host runtime binding](host-runtime-binding.json) records the actual Corretto
version, Java/compiler/JVM/module-image hashes, compiled probe hashes and compiler
stream hashes. [Preservation check](preservation-check.json) verifies all 2,117
r10 and 2,125 r11 frozen input hashes unchanged, with no tracked production diff.

## 2. Proposed semantic rule — separate approval required

See [the exact proposal](pool-comparison-proposal.md). It is deliberately scoped
to this class-file hash and this precisely explained extension. It does not accept
arbitrary appended constants, reorder the original pool, ignore method changes or
introduce a generic semantic equivalence bypass. A host-only diagnostic evaluator
and five negative-control tests demonstrate the proposed rule; **it is not wired
into any admission, collector, replay or frozen snapshot**.

## 3. Lambda dump property: corroboration only

OpenJDK 21.0.10's
[InnerClassLambdaMetafactory source](https://github.com/openjdk/jdk21u/blob/jdk-21.0.10%2B7/src/java.base/share/classes/java/lang/invoke/InnerClassLambdaMetafactory.java)
uses `-Djdk.invoke.LambdaMetafactory.dumpProxyClassFiles=true`, writing beneath
`DUMP_LAMBDA_PROXY_CLASS_FILES` in the target's working directory. The former
`jdk.internal.lambda.dumpProxyClasses` spelling is not the property selected here.

The host experiment produced 31 dumps. All 31 had method bytecodes matching
their corresponding JDI observations; zero had identical raw pools. The external
observer read 58 hidden definitions without a byte-read failure, so these dumps
also do not cover every hidden definition. Filenames/addresses are used only to
correlate this diagnostic comparison, never as a trust rule.

Dump files are written by the target JVM in its writable filesystem. They cannot
authorize a host, loader, bootstrap site or candidate attribution, and cannot
replace missing JDI evidence. They may be copied as explicitly untrusted
corroboration in a future approved census. This property was not added to any
native launch plan. Pinned-image behavior remains to be checked in that window.

The observed HierarchicalTestEngine factory lambda allocates a ThrowableCollector
and includes a cast. It would not satisfy r11's narrower load/invoke/return-only
rule. Full v2 generation-recipe provenance is therefore still required; changing
the pool comparison alone would not make r11 qualify.

## 4. Expanded census and time box

[The five-path census scope](census-scope.json) binds J1 retained, duplicate-line
and candidate-runtime-exception paths plus J2 and J3 retained references, all on
both engines in **one future exact Tower-authorized window**. These are five fresh
serial pairs, ten engine executions, not five qualification successes. The
35950-second aggregate pair ceiling needs approximately an eleven-hour window
including group checks. An exact window is not yet selected or authorized; it
must be scheduled around Maintec intake and bound to the new plan/snapshot/commit.
The old seven-hour r11 window is insufficient for the full worst-case budget.

The census retains failed paths and generated-class records. Provenance gaps are
recorded as census findings, never converted into qualification acceptance. The
approved v2 stop-before-next-slot rule remains in force. A halt leaves remaining
paths explicitly unstarted and the five-path census incomplete; this draft
grants no authority to continue through a provenance failure. No failed slot is
replaced or reused. All five paths must have complete evidence before claiming
census coverage.

Time box: **end of October 9, 2026, America/Los_Angeles**, meaning the cutoff is
October 10, 07:00 UTC (exclusive). If full generated-class provenance remains
unavailable through the approved JDI-only approach, stop that approach and bring
an alternative for review. Raw bytes are available, but the required trustworthy
generating host, invokedynamic/BootstrapMethods site, generator and runtime-origin
closure has not yet been demonstrated. This report does not declare that condition
met merely because byte capture worked.

A possible alternative is a narrowly scoped trusted JVM generation observer at
the admitted lambda/hidden-class definition boundaries, with an externally bound
event channel. It would need separate review of its authority, instrumentation
effects and negative controls. A generic ClassFileLoadHook or target-written dump
must not be assumed to observe/prove every hidden definition. No alternative
agent, exception, native run or new authority has been installed.
