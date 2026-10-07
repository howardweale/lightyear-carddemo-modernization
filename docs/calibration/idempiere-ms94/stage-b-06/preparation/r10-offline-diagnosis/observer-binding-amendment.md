# Prospective amendment: B06 observer binding v2

**PROPOSED — not approved, not installed, not an authorization.**
Operator review; not independent attestation. Applies only to a new snapshot;
r8/r9/r10 and their verdicts/evidence remain unchanged.

The aim is to replace the incomplete package-prefix check with a closed
provenance policy, not to skip unknown frames. Every frame and catch location
must have one of the following dispositions; unknown or ambiguous provenance
is equipment-suspect and stops the smoke before the next slot.

## 1. Classes that require exact compiled-byte binding

Every ordinary non-JDK class appearing in a recorded stack or catch location:
candidate and all helpers, public support, iDempiere application, OSGi/Tycho/JUnit,
Apache Felix, JDBC/pool and other dependencies. Bind the full class-file SHA-256,
constant-pool identity and each executed method's name, descriptor and bytecode.
Native/abstract methods need their explicit access flags and approved native
provider; the string unavailable alone is not acceptance.

Also retain the existing exact compiled-byte binding for the external collector,
Doc lock-SQL class/constant-pool/template, six selected checkpoint/terminal classes,
candidate source/compiled outputs, public support and terminal/catch provenance.
Ordinary inner classes and lambda$ methods compiled into a normal host are ordinary
byte-bound classes, not exceptions to this rule.

The actual defining loader, module/bundle and code source must identify a
plan-bound artifact in the resolved runtime; an arbitrary same-name resource
lookup does not prove which class loaded. Retain classpath/OSGi configuration
and code-source artifact hashes. Unexpected loader changes, writable candidate
substitution, instrumentation, redefine/retransform or unapproved native agents
fail closed. Do not infer trust from package spelling or loader ID alone.

No exemption for HierarchicalTestEngine is proposed. Keep the current pool
mismatch blocked until raw runtime pool/method material and original definition
bytes explain it. If the VM representation legitimately differs, propose and
test a precise canonical semantic comparison in a further reviewed revision;
do not disable the pool check or accept the observed hash by fiat.

## 2. What is trusted through the pinned image

Only the admitted JDK runtime implementation: ordinary platform classes proven
to originate in the pinned JDK module image, the JVM/native libraries and the
specified JDK generators. A java.*, javax.*, jdk.*, sun.* or com.sun.* name alone
is insufficient. Require bootstrap/platform loader identity, module provenance,
and a verified binding of java, lib/modules, release metadata and native-provider
files to the pinned application image. For missing/unsupported provenance, stop.

The runtime admission must prohibit boot/module patches, upgrade-module-path
substitution, unapproved classpath/agent/native-library injections and writable
overlays of these runtime files. Validate actual launched process arguments,
environment and mounts, not a supplied boolean. An image digest alone is not
proof that its files were not shadowed after container creation.

Record runtime byte/hash observations for these frames, but do not require a
static per-generated-address class-file whitelist for JDK implementation code.
**No ordinary application, candidate, support, JUnit, OSGi or JDBC frame is
trusted solely through the image digest.** This boundary is prospective and
must be exercised by negative controls before native acceptance.

## 3. Generated and hidden classes

Never accept by stripping $$Lambda, /0x, $Proxy or a numeric suffix. Never learn
an allowlist from the candidate's first execution.

Extend the external collector to retain raw method/constant-pool material,
defining-loader/module/class-object identities, and independently verifiable
generation linkage. No target method invocation or candidate trace may supply it.
The implementation must demonstrate that the chosen JDI/VM mechanism can obtain
these fields; if it cannot, stop and submit a new mechanism for review.

- **Lambdas:** bind the ordinary host class and the exact invokedynamic site,
  BootstrapMethods entry, admitted LambdaMetafactory identity, implementation
  method handle, SAM/instantiated descriptors, captured-argument layout and
  actual defining-loader/host relationship. Decode the generated adapter's raw
  bytecode/constant pool and verify its permitted delegation to that target.
  Unexpected code or ambiguous host/site fails. A candidate lambda inherits
  candidate origin only after this proof; a support lambda inherits support;
  a framework lambda remains framework/outside, never candidate merely because
  a candidate is deeper in its stack.
- **Dynamic proxies:** bind the exact ordered interface byte identities, loader,
  admitted generator, generated dispatch body and actual invocation-handler
  class/method. Attribute behavior to the handler, not the proxy name. Unknown
  handlers, including candidate-provided handlers with framework interfaces,
  are not trusted framework code.
- **Reflection accessors and LambdaForms:** prove the admitted JDK generator and
  the actual reflected member/method-handle target and adapter shape. Treat an
  approved adapter as dispatch machinery only; it cannot create candidate cause
  or terminal success. Missing/ambiguous target yields outside/unattributed and
  equipment-suspect where causal exclusion is required.
- **Other hidden/generated code:** unsupported until an exact generation recipe
  is proposed and approved. Record and halt; no generic wildcard fallback.

Keep raw names and runtime IDs in evidence. A separate structural identity may
omit unstable addresses only after generation linkage is proven; raw identities
must never be discarded. Cross-engine structural agreement is necessary where
expected, but is not a substitute for provenance on either engine.

## 4. Census, replay and negative controls before smoke acceptance

A new zero-model, separately Tower-authorized census must collect complete stacks
and catch locations at all relevant callbacks, full method/pool material and
runtime origin evidence, including the retained and two smoke control paths.
It cannot modify the frozen catalogue while evaluating qualification outcomes.
Preserve census failures and costs separately; no census pass counts as a smoke pass.

Independent offline replay must recompute class identities and generation
linkage from retained evidence, rather than trusting a signed classification.
Fail on truncated/missing frames, unbound definitions, pool/method mismatch,
unresolved runtime origin, class-loader substitution, counterfeit lambda/proxy
names, wrong host/site/handler, corrupted generation bytes and broken evidence
chains. Test framework/candidate/support/JDK generated cases distinctly.
A changed collector requires offline compilation and its own approved Docker
preparation window if the pinned compiler is available only in Docker.

Production checked_frames, origin and terminal predicates remain unchanged while
this amendment is awaiting approval. J1 business predicates, scenario dates,
private expectations, source/support bytes and intended smoke outcomes stay fixed.
No success claim, B06 measurement launch or retrospective reclassification follows
from approval of this proposal alone.

