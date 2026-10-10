# B06 captured return refusal: offline reproduction, October 10, 2026

The diagnostic failure is now reproducible offline in the exact frozen Java
`Generation.atReturn` guard. A repair is **not proven**, and no native rerun,
Tower request, qualification, or measurement was performed by this work.

## What the new record establishes

The complete 231,090-record stream was authenticated against the signed census
and failure commitments, including every record hash, predecessor, sequence,
file digest and final commitment. Structural audit ordering and bounds passed.
The pending stack reconstructed from generation entries, returns and unwinds
matches every recorded pre-dispatch pending stack.

At event **231089**, thread **70867** delivered request **8**, an ARETURN
breakpoint in `java.lang.invoke.InnerClassLambdaMetafactory.spinInnerClass`
(`()Ljava/lang/Class;`), bytecode index **117**, depth **25**. Its live top
location agrees with the event location. There is no pending generation and no
armed exit for that thread. Event **231090** records the refused dispatch.

This thread's nested `ClassDefiner.defineClass` invocation entered at event
231019 (generation 12392, depth 27), armed request 12468, and returned at 231068.
The recorded stack at that entry includes the outer `spinInnerClass` at bytecode
114, depth 25. Thus the outer invocation was executing, but its entry was never
recorded. There is no recorded exception, unwind, or earlier outer entry on this
thread. The entry request was not globally absent: request 3 recorded 1,942 prior spinInnerClass entries at bytecode 0 across the stream. This is not a return-stack depth mismatch or a duplicate arm. Two
other generation calls remain open because the prefix ends at the refusal.

The public fixture exports only structural fields for the failing thread:
JDK locations, depths, request IDs, generation IDs and event ordering. It omits
thread-name hashes, full application stacks, arguments, class bytes and values.
Raw events, application stacks and archives remain in the preserved local run.

## Exact code reproduction and its limit

`tools/b06_host_probe/captured_refusal.py` authenticates the original stream and
reconstructs its pending state. `CapturedReturnProbe.java` supplies the captured
structural operands through JDI interface proxies to the **unmodified frozen
Java guard**, rather than implementing a second copy of that guard. It produces:

```
java.lang.IllegalStateException: generation return arm without matching activation
```

The Java process executes only observer code with interface proxies: no target
JVM, application, JDI connection or Docker is used for this reproduction. This
is an exact guard/state reproduction at the recorded event index, **not a
reproduction of the JVM scheduling or request-delivery mechanism that omitted
the entry**. No activation is synthesized and no missing event is filled in.

The guard is correctly refusing absent entry evidence. Changing it to accept
this record would not restore that evidence. The next repair investigation must
establish why the entry request did not produce an observed event, then prove
that entry observation is restored without relaxing admission. The current
capture does not record entry-request installation/enabled lifecycle or target
JVMTI request-delivery internals. No particular JVM/JIT mechanism is established.

## Checks and bounded host experiment

- Eight focused tests passed: captured fixture pin and lifecycle, rejection of
  invented pending state/changed location, actual Java guard reproduction,
  historical prefix limitations, and audit ordering/refusal bounds.
- All **113,595** preserved frozen file hashes passed using the frozen verifier
  after controller exit (71.125 seconds).
- One host experiment used 300 newly started threads, three concurrently, with
  `Collectors.counting` and repeated LambdaMetafactory generation. Windows
  Corretto 21.0.10 completed in **17.172 seconds**, with observer exit 0 and
  neither refusal. This negative result does not prove native correctness.
- The host experiment's first setup attempt failed while parsing whitespace in
  the JDWP banner, before observer attachment. Its output remains preserved;
  the corrected setup used a different local output directory.
- No production observer code, frozen plan, original evidence, J1 predicate,
  machine configuration, B05 data or native owner was changed.

## Evidence identities

| Record | SHA-256 |
|---|---|
| Captured stream file | `67d18166362f24456af99230063f24a51ea2cbdd011fac7f65c53d643a5b578f` |
| Frozen observer Java source | `b4b8e34a858464f1b507ba0fe33e1ba92feb7d6afe7d9b637fd30f05c88dc065` |
| Public structural fixture | `9c310442cd9f25dca92a37b25f7d79bbe6038306a91c71c97d622f6dc2add447` |
| Signed collector failure | `15e1c9258bd6c78229cd397cd28fe6bf5a6dc25c42783e3db8b90fac39096790` |
| Signed terminal report | `7b7ca2c8f8cd25c4c2caacd2a3eeda6255c60bddfc7d40dacde2c0196a70dbb8` |
| Signed partial audit | `b8660d0122fc5313b8773c1fc152a56d52132318e2896bb2b632f648c7f9f311` |
| Preserved archive | `522b830558d6da35cc454f25124b7754b30e17267b181d30cab6d67c36e7651c` |
| Frozen snapshot | `ba570784e544a252682737ff0396df59dd7b3fc5d5be63e94c0afc075a1ce555` |

The original run remains an equipment failure: native receipt 1,273.735 seconds,
terminal duration 1,457.985 seconds, zero models, no qualification credit.
The prior monitor verified six signed failure/audit/cleanup records and confirmed
owned containers, networks and volumes absent. The diagnostic monitor remains
paused. No original record was modified or re-signed.

## Rerun gate

At the time of reproduction, rerun was blocked on a proven observation repair.
Howard subsequently accepted an unmatched-return diagnostic exception and
shortened the four-hour review lead for October 10, 10:30 AM–1:30 PM PDT.
This is a prospective policy amendment, not proof that missing entry delivery
was repaired. Fresh preparation, freeze, exact Tower and separate Docker
approvals remain required. The prior owner and approval remain consumed.
See `b06-unmatched-return-diagnostic-milestone.md` for the bounded exception.

Operator review only; not independent attestation.
