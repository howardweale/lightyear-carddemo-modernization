# Observer v2: pool approval and host generated-class proof progress

Operator review; not independent attestation. **Incomplete; not an executable
five-path snapshot or a Tower approval request.** No Docker commands, native
pairs, target method invocations through JDI, or model calls were made.

Howard approved the exact pool comparison proposal in the conversation. The
[approval transcription](pool-approval.json) binds proposal file
`31a0f4ff21208456d81ef47bfdef619c68c97bb3615348678c8d2fa7e9a0e3a7`.
It is a content-hashed transcription, not Howard's cryptographic signature.
The original proposal is preserved with its historical preapproval wording.
The transcription hash is
`92c06471136b65106bec9fcb6ec41e12b18426e515c6a53d15c1aaad25fb1ce7`.

The preserved initial [progress report](report.json) has content hash
`ab26f434341f6487cbf674a7563f9422e109030028a488106f4c6654101e050c`.
The current [progress addendum](progress-addendum.json) has content hash
`53027692cb69ba515e075a16be09f7fbff94b998fd8e29dd5327ebe2c793745d`.
It records 30 passing offline tests and the later preserved host experiments.

## What the host experiments establish

The external observer installs JDI breakpoints before the public fixture starts.
It reads actual generator objects, the defining lookup, exact generator-return
Class identities, raw runtime constant pools and all method bodies. It does not
invoke methods in the target, install an agent, or use target-written dumps as
evidence.

The last host experiment records **73 hidden classes and 73 matching generator
return identities**. Both new definitions and classes restored through the
JDK's lambda cache are covered; watching only ClassDefiner missed cached classes
in the earlier preserved attempt.

Replay checks **24 JUnit lambdas** against their exact ordinary host bytes,
invokedynamic instructions, BootstrapMethods entries, implementation handles,
SAM/instantiated descriptors, captured fields, constructors and adapter bodies.
Three additional public fixture roles—candidate, support and outside—also have
the actual immediately younger target frame checked. These are public host
fixtures, not native qualification or the private reference implementations.
Names containing `Lambda` confer no trust.

The replay treats JDWP's documented synthetic marker as a wire representation:
the complete expected modifier word must match, including the synthetic marker
where required. It does not mask arbitrary unknown bits. See the
[JDWP method modifier specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jdwp/jdwp-protocol.html#JDWP_ReferenceType_Methods).
This leaves the approved pool rule's exact original class-file flags intact.

For **24 LambdaForm definitions**, JDI links the actual byte array returned by
InvokerBytecodeGenerator to the exact array consumed by ClassDefiner, on the
same thread, then to the returned Class object. The four inspected JDK generator
classes' runtime pools and methods match this host JDK's class files. The
experimental expression decoder now matches all 24 method bodies to their
captured LambdaForm graphs, including the exact typed array-load intrinsic.
All 24 class-data initializers are checked against the returned definition's
actual ClassData object, fields, method closure and permitted instruction sequence.

**An expression match is not complete LambdaForm admission.** Dynamic target
attribution for each actual use, native collection and full replay integration
remain unfinished. The decoder explicitly returns
`adapter_body_verified:false` and `native_admission:false`, even for expression
matches. Opaque VM-internal ResolvedMethodName fields remain opaque in the
captured graphs; no target identity is invented from them. This observation does
not establish that every possible JDI approach is incapable of proving a target.

The host is Windows Corretto 21.0.10+7. The native image uses Linux Temurin
21.0.10+7-LTS. These results establish host mechanism behavior, not the native
runtime's module, loader, artifact or generator bindings.

The later ordinary-class experiment captures the exact bytes presented to
ClassLoader.defineClass, defining loader, protection-domain source and returned
Class identity. Of 57 definition records, 51 match their independently supplied
host artifacts; five unused classes remain unprepared and are not admitted.
AbstractTestDescriptor has another pool reconstitution (265 to 275 entries).
It appeared in neither the captured stack frames nor r10's saved-frame census;
it remains rejected if encountered. The approved HierarchicalTestEngine rule
has not been broadened to cover it.

## Validation and preservation

**30 focused tests passed.** The portable synthetic tests reject added logic
despite recomputed hashes, changed hosts/loaders/sites, unknown flag bits, extra
methods and missing/wrong/older adjacent targets. Local-evidence tests separately
exercise the real JDI observations and remain explicitly skipped when those
private local observations are absent. A passed incomplete-expression test
checks that admission remains false; it is not a qualification success.

All eleven host observations remain under `work/b06-observer-v2-host/`, including
the missing-main-class, class-not-prepared and attempt-10 observer failures. An intermediate host
compiler syntax failure is preserved in the conversation's tool output; there
is no invented local compiler-log hash. The report binds every retained
observation file and the test log. Raw captures and compiled class files remain
local.

Reverification found all **2,117 r10** and **2,125 r11** frozen input hashes
unchanged. r10 remains failed. The preparation increment did change production
`PostingObserver.java`, `posting_replay.py` and `posting_broker.py` behind the
`forwarding_stub` gate. Those changes fail closed and were not native
qualification. J1 business predicates, expected outcomes, frozen plans and
Tower decisions were not changed. The [review follow-up](../review-pr269-271/README.md)
adds stricter defining-host/factory checks; complete native provenance remains
a prerequisite.

## Remaining before five-path publication and Tower review

1. Complete the LambdaForm per-use dynamic-target proof and its
   adversarial replay tests; do not promote the experimental decoder.
2. Bind the actual native JDK/module and class-loader/artifact origins and
   integrate the completed proof into collection, receipts and replay.
3. Assemble a fresh five-path snapshot: J1 retained, duplicate invoice-line,
   candidate runtime exception/direct delivery, J2 retained and J3 retained,
   each on Oracle and PostgreSQL, in one declared window.
4. Publish and byte-verify the exact commit, then issue the exact Tower request.

No five-path executable hash or public commit is claimed. Howard's Oct 9
time box remains: if complete JDI provenance is not demonstrated by
2026-10-10T07:00:00Z, stop that approach and present an alternative mechanism.

The separate [image extraction proposal](../observer-v2-image-extraction-r1/README.md)
collects missing native artifacts only. It has its own frozen snapshot, exact
public commit and Tower request; approving it does not authorize the census.
