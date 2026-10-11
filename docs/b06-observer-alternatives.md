# B06 observer alternatives — host measurements and 2c split

**2026-10-11: Part 5 measured offline.** Howard's October 10 decision withdrew
host reproduction as the prerequisite for the memory work. This independent
alternatives study does not lift the engineering hold or authorize a native run.
No Docker, native application, model calls, customer data or machine changes were
used. No qualification or measurement credit is claimed. Operator review, not
independent attestation.

The [aggregate measurement record](b06-observer-alternatives-measurements.json)
binds the public fixture, compiled classes, JDK executable, training trace,
archive, linked images, dump inventories and authenticated historical streams.
Raw dumps, archives, runtimes and captured native inputs stay local.

## Experiment and denominator

Amazon Corretto **21.0.10+7 on Windows**, one public synthetic fixture, 24 iterations
per process, three repetitions per configuration. Each iteration creates a lambda
proxy, invokes a method handle with one of twelve argument shapes, defines a
hidden class and defines an ordinary class through a fresh loader. A separate
invokedynamic lambda call site is exercised. Every process completed; generation
counts were identical across all three repetitions of each configuration.

`AlternativesCounter.java` is a bounded **entry-only JDI counter**, not the strict
provenance observer. It counts `spinInnerClass`, `ClassDefiner.defineClass`, and
the three byte-emitter methods watched by the existing observer. The selected
fixture exercised `generateCustomizedCodeBytes`; the other two emitters recorded
zero entries. Requests are installed at VMStart/class prepare and each event set
is resumed once. No target method is invoked through JDI. The counter does not
establish entry/return pairing, native payload completeness, or calls before its
requests were installed. Counts are invocation counts, **not unique classes**;
a generator and its downstream class definer are counted separately.

Wall timings use separate processes **without JDI**, measuring process launch to
exit, including JVM startup and output. They are a small host experiment, not a
stable throughput benchmark: three repetitions, fixed variant order, no confidence
interval, filesystem/cache effects included. All raw timings are retained in the
aggregate record. First cold linked-image times were 847 ms (trained) and 653 ms
(control), so medians must not be presented as cold-start speedups. Source newline
normalization was followed by recompilation; all four class-file bytes match the
classes actually measured.

## JLI pre-generation and dynamic CDS

Training used `-Djava.lang.invoke.MethodHandle.TRACE_RESOLVE=true` and
`-XX:ArchiveClassesAtExit=fixture.jsa` on a jar containing the same fixture.
A separate runtime was built with `jlink --generate-jli-classes=@trace`, adding
`java.base,jdk.jdwp.agent`. A module-identical control image used
`--disable-plugin generate-jli-classes`. Dynamic CDS was selected using
`-XX:SharedArchiveFile=fixture.jsa`; CDS logs confirm that the dynamic archive
mapped in both the timed process and the counting process. The retained B06
runtime image was never modified.

| Runtime | spinInnerClass | Customized-code emitter | ClassDefiner | Total watched calls | Removed vs installed JDK | Median wall time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Installed JDK baseline | 25 | 82 | 133 | 240 | — | 97.35 ms |
| Linked control, JLI plug-in disabled | 25 | 152 | 211 | 388 | −61.67% (more calls) | 168.07 ms |
| Trained JLI image | 25 | 61 | 110 | 196 | 18.33% | 114.56 ms |
| Installed JDK + dynamic CDS | 25 | 61 | 85 | 171 | 28.75% | 97.17 ms |

Against the **module-identical linked control**, JLI removes **192/388 = 49.48%**
of the watched calls. The installed JDK already contains pre-generation/sharing,
so comparing its 240 calls with the untrained linked image would confound runtime
packaging with this treatment. The trained JLI image has 101 files / 49,878,001
bytes; the dynamic archive is 720,896 bytes. Whole-image inventory digests and
build/training durations are recorded in JSON.

Neither treatment removed the **25 outer lambda-factory invocations**. A CDS
cache hit can occur inside a watched method. Neither percentage is an estimate
of how many of the approximately 12,400 native calls disappear. A different
native runtime/archive would require separate preparation and approval.

## JDK dumps: coverage, bytes, attribution and overhead

These are the actual Corretto 21 properties tested, each with `=true`:

- `jdk.invoke.MethodHandle.dumpMethodHandleInternals`
- `jdk.invoke.MethodHandle.dumpClassFiles`
- `jdk.invoke.LambdaMetafactory.dumpProxyClassFiles`

| Property / combination | Observed class files | Bytes | Median wall time | Change vs 97.35 ms baseline | Fixture coverage |
| --- | ---: | ---: | ---: | ---: | --- |
| Method-handle internals | 83 | 123,886 | 165.46 ms | +69.97% | 82 LambdaForm files; one bound-method-handle species |
| Lookup class files | 24 | 8,472 | 120.76 ms | +24.05% | 24 hidden definition dumps, all byte-identical to their input |
| Lambda proxy files | 25 | 7,000 | 115.57 ms | +18.72% | 25 proxy files for the 25 factory calls |
| All three | 132 | 139,358 | 178.92 ms | +83.80% | Union of the three categories above |

Dump counts and byte totals were identical in every repetition. All dump
configurations retained the same 240 watched calls: dumping does not remove
matching work. The 82 LambdaForm files correspond numerically to the 82 emitter
entries; this is category accounting, not an authenticated per-call bijection.
The fixture's 24 ordinary `ClassLoader.defineClass` calls produced no separately
attributed ordinary-loader dump. They deliberately use the same input bytes as
the hidden definitions, so byte hashes alone cannot distinguish these two runtime
identities. There is no completeness claim for arbitrary loaders or definitions.

Hidden-class filenames contain their generated name/address suffix. Proxy names
identify the fixture's enclosing class; LambdaForm names identify a JDK category.
These are useful retrieval clues, **not** entry/return identity, thread/depth,
input-to-output provenance, or a durable runtime object identity. Filename-derived
addresses differ across runs; the inventory hashes bind each repetition separately.
No complete native category coverage, failed-definition capture, JFR byte coverage,
or loss-free collection claim is established. Class-load logs and JFR remain
potential supplements, not substitutes for missing class bytes and pairing.

## 2c split of the preserved native r1 and r3 prefixes

The analysis verified both signed incomplete census/failure envelopes using the
public campaign key, every event seal and sequence/previous-hash link, the complete
stream digest, terminal counts and plan/lane bindings. The original streams and
archives were not changed. These remain failed, incomplete observations, with no
provenance replay or qualification credit.

The rule examines captured **generation inputs** (`lambda_factory`, `definer`,
`lambda_form_graph`, `class_data_graph`) and excludes caller stacks. A direct
class-object reference with a non-bootstrap loader and a non-platform class name
is an application/library-derived input witness. This is a lower bound; platform
names loaded outside bootstrap remain unresolved. Bootstrap-only captured inputs
are plumbing **candidates**, not a proof of image-independent generated bytes.
Missing class-input witnesses are unresolved; package names alone never prove
independence. A stream-bound aggregate witness digest records each rule result.

| Classification | Diagnostic r1 (12,394 entries) | Unmatched r3 (12,396 entries) |
| --- | ---: | ---: |
| Application/library-derived class input witnessed | 3,523 (28.425%) | 3,522 (28.412%) |
| Bootstrap-only captured-input plumbing candidate | 1,241 (10.013%) | 1,244 (10.035%) |
| No captured class-input witness | 7,624 (61.514%) | 7,624 (61.504%) |
| Non-bootstrap platform-class input, unresolved | 6 (0.048%) | 6 (0.048%) |
| **Proven image-independent bytes** (not an extra partition) | **0** | **0** |

This does **not** convert the unresolved majority into plumbing. Class-data
objects, bytes, customization, opaque nodes and resolution context can still
influence output. Removing 10% of native evidence based only on this table would
be unjustified. Classification is structural analysis of an authenticated prefix,
not a causal explanation of the missing entry or native OOM.

## Comparison and decision boundary

| Alternative | Measured host result | Remaining evidence gap / contract change |
| --- | --- | --- |
| JLI pre-generation | 49.48% fewer watched calls vs matched linked control; 18.33% vs installed JDK | New runtime digest; native workload-specific effectiveness; provenance for pre-generated classes |
| Dynamic CDS | 28.75% fewer watched calls; outer factory calls remain | Archive identity/eligibility, capture misses and catalogue/admission contract |
| Three JDK dump facilities | 132 files / 139,358 bytes, +83.80% median process wall time | Loader completeness and authenticated per-call provenance/identity remain absent |
| 2c selective plumbing exclusion | 10.01–10.04% bootstrap-input candidates; 0 entries proven image independent | Explicit proofs and evidence-scope/replay amendments before any exclusion |

The lower-risk finding is that pre-generation can reduce real watched work on a
matched public workload while preserving the observer. A dump-based replacement
has substantial attribution/completeness obligations. Howard's two-attempt
request and Part 6 decision rule remain separate; this report selects no native
alternative and does not authorize or retry an attempt.

## Reproduction and validation

Host-only runner (use a **new** output directory; it refuses reuse):

```text
python -B -m tools.b06_host_probe.alternatives_experiment --jdk JDK_HOME --out NEW_LOCAL_OUTPUT
```

The checked-in runner now includes the matched linked control in the main matrix;
the recorded experiment added that control in a separate, preserved local run.
Counts, raw timings, source/class hashes and both image inventories remain bound
in the public aggregate. Local artifacts live under `work/alternatives-host-r1`
and `work/alternatives-control-r1` in the isolated alternatives worktree. No raw
artifact is staged. `alternatives_partition.py` requires a supplied **public** key
and signed incomplete envelopes; it emits only aggregate counts/hashes.

Six focused tests passed: caller-only refusal, bootstrap candidate conservatism,
application input witness, platform-loader ambiguity, class-name-only refusal,
and signed stream tamper/privacy checks. All 24 timed cells and 24 separate JDI
counting processes completed. Final-head CI must finish green; Howard's exact
commit approval is still required before merge.
