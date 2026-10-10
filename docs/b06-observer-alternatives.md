# B06 observer alternatives — investigation register

Status: **measurements pending**. No engineering run is approved or launched.
The active October 10 diagnostic and its evidence window take priority. This file
does not claim the requested native comparison is complete. Zero qualification,
measurement or model-call credit; no production observer or gate changes.

## What is known now

The approximately 12,400 watched calls in the request are a historical estimate,
not a denominator remeasured for these experiments. The earlier failed diagnostic
contains a partial stream, not a complete matched workload. Call reductions cannot
be inferred from fewer events before an earlier failure.

Static inspection of the installed **Corretto 21.0.10_7** public `lib/src.zip`
confirmed these implementation properties (no JVM was launched):

| Facility | Property / plug-in in this installed source | What that establishes |
| --- | --- | --- |
| Method-handle internals | `jdk.invoke.MethodHandle.dumpMethodHandleInternals` | A class-file dumper exists; complete native coverage unmeasured |
| Lambda proxies | `jdk.invoke.LambdaMetafactory.dumpProxyClassFiles` | Lambda metafactory has a separate dumper |
| Lookup-defined classes | `jdk.invoke.MethodHandle.dumpClassFiles` | Lookup uses another dumper, including hidden class definer paths |
| JLI pre-generation | `--generate-jli-classes=@trace_file` with `java.lang.invoke.MethodHandle.TRACE_RESOLVE=true` training | The installed jlink source documents a trace-driven plug-in |

The installed source hashes are: MethodHandleStatics.java
`ca0509f5f733a4731effc119da4d190d0fb6e95d26c74b91afedba7df0d81fe0`,
MethodHandles.java `3cd6f1229de979b3da578acc4bc49af394dd930e411862255de977d2252b1a0f`,
ClassFileDumper.java `79dba9a339ac4c3f81d280f9cfa6d059fc54b00b88a95488424c8ae32c1d60e7`.
Host source inspection is not verification of the retained Linux image's build.
Do not assume older flags such as `java.lang.invoke.MethodHandle.DUMP_CLASS_FILES`
or `jdk.internal.lambda.dumpProxyClasses` work on this build.

The [OpenJDK 21.0.10 lambda metafactory source](https://github.com/openjdk/jdk21u/blob/jdk-21.0.10%2B7/src/java.base/share/classes/java/lang/invoke/InnerClassLambdaMetafactory.java)
has a CDS lookup inside `spinInnerClass`. Therefore retrieving an archived proxy
need not eliminate the watched outer method call. Its generated proxy also depends
on caller/implementation signatures and captures: JDK code location alone does not
prove application independence.

The [JDK 21 CDS documentation](https://docs.oracle.com/en/java/javase/21/vm/class-data-sharing.html)
describes static/default and dynamic archives. The [java tool reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
documents training/dumping and archive-selection options. These establish options,
not B06 coverage, determinism, speed, or the fraction of calls removed.

## Measurement protocol (not yet executed)

Keep a build-once copy of the public fixture and the strict #293 observer. Record
exact Java/JDK/source/class hashes, options, workload inputs/iterations, elapsed
time, class-file count/bytes, trace bytes, and success/refusal for every cell. Use
at least three baseline and three treatment repetitions with identical workload.
Capture strict observer generation-entry counts by method and thread alongside
dump/JFR/log output. Count watched invocations separately from emitted classes.

1. Baseline versus a separately built JLI image, using the same traced public
   fixture, and baseline versus a trained dynamic CDS archive. Require complete
   matched traces before calculating removed calls. Hash the entire resulting
   runtime/archive and build recipe; never mutate the preserved image. A new
   native image needs a new standing image approval, even if the host result helps.
2. Baseline versus each dump property, then their combination; baseline versus
   `-Xlog:class+load=info` and a JFR recording with class-definition/load events
   explicitly enabled. Inspect this exact JDK's event metadata before claiming
   thread/stack fields. Compare dumped class identities/bytes against all observed
   definitions, especially direct `defineHiddenClass`, ordinary loaders, proxies,
   invokers, repeated definitions and refused calls. Count missing categories;
   filenames alone do not uniquely bind a runtime class identity.
3. After approval, collect a native engineering baseline and approved treatment.
   The current fixed-image/strict-observer approval does **not** authorize changing
   its JVM arguments, runtime image or observer policy. Publish the treatment plan
   and obtain an amendment first. Do not extrapolate public host percentages to
   the approximate 12,400 native calls.

`tools/b06_host_probe/alternatives_analysis.py` is a pure saved-record analyser.
It counts generation entries, preserves the incomplete/refused distinction, rejects
cross-workload and incomplete comparisons, and requires explicit per-entry witnesses
for provenance classification. It launches nothing and grants no archive authenticity.
The signed diagnostic archive must be verified separately before using its results.

## Scope data and attribution limits

No complete/near-complete engineering record exists yet. Counts and percentages
for image-independent versus application-derived calls are **not measured**.
The analyser leaves entries unresolved unless a reviewed witness binds the exact
entry record. It does not classify `java.lang.invoke.*` as image-only by name.
An invoker specialized to an application method handle, or a lambda proxy targeting
an iDempiere method, is a candidate for application-derived classification even
though the generator is JDK code. Proving bytes identical across a few examples is
also weaker than proving they are identical for every program on that JDK build.

Dumped files can be hashed and signed by a host collector, but a signature establishes
possession/integrity, not completeness, caller identity, returned-class identity or
input-to-output provenance. Class-load logs and JFR must be evaluated separately
from byte capture. No claim that dump-plus-verify replaces all pairing is established.
At most it is a **partial replacement hypothesis** pending category-by-category proof.

Replacing observed plumbing with an image digest would give up per-invocation
entry/return identity, thread/depth binding, generation input provenance and some
frame-linkage claims. Potential amendments include observer-v2 generation matching,
generated-frame admission, catalogue completeness and strict offline replay. Merely
relaxing a refusal or producing a dump file does not satisfy those gates. No gate
is amended in this investigation.

| Option | Measured native calls removed | Coverage gaps still to test | Effort estimate (planning only) | Contract changes required |
| --- | --- | --- | --- | --- |
| JLI pre-generation | Not measured | Workload-specific forms; outer watched calls may remain | Medium: trace, build separate runtime, compare | New runtime digest/preparation; provenance review for pre-generated classes |
| Dynamic CDS/AppCDS | Not measured | Eligibility, cache misses, outer-call counts, custom/hidden classes | Medium: train, bind, replay on exact JDK | Archive identity/mount and observer catalogue/admission |
| Three class dump facilities | Not measured | Direct loaders, completeness, failed generation, attribution | Medium-high: coverage/identity collector | Trusted collection and completeness/provenance contract |
| Class-load logging / JFR | Not measured | Class bytes, event configuration/loss, caller and thread linkage | Medium for experiment; high for replacement proof | Event loss/completeness and class identity contracts |
| Image-only proof for proven plumbing | Not measured | Application independence is unproven for unclassified entries | High: category proofs and negative tests | Explicit scope, linkage and replay amendments |

Howard can retain strict pairing, approve a measured pre-generation experiment,
investigate a partial dump-based replacement, or amend evidence scope after the
counts and coverage gaps are established. No option is silently selected here.
