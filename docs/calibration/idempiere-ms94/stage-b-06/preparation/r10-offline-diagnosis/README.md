# B06 J1 smoke r10 — offline diagnosis

Operator review; not independent attestation. r10 remains failed.
The initial proposal and blocked r11 draft in this directory are historical
preparation records. Howard subsequently requested one corrected smoke that also
serves as the census, under the narrower
[r11 forwarding-stub amendment](../smoke-bindings-r11/amendment.md).
No native run, restart, replacement, compilation, authorization signing or model call
was performed for this diagnosis. The only Docker operations were the separately
approved, owner-label-filtered inventory reads described below.

## Finding

The immediate failure is `observer-unbound-class` at event 2, stack position 29
(zero-based) on both engines: a runtime-generated
`TestMethodTestDescriptor$$Lambda/...apply(...)` class is absent from the frozen
catalogue. The verifier requires every org.junit.* frame and every candidate
prefix frame to exist in the static catalogue. Twelve generated classes per
engine hit that requirement: eleven JUnit lambdas and one candidate lambda.
Ten additional generated JDK LambdaForm classes per engine are unbound but were
not required by r10's prefix-based check.

Scanning past that first failure reveals another blocker:
`org.junit.platform.engine.support.hierarchical.HierarchicalTestEngine.execute
(Lorg/junit/platform/engine/ExecutionRequest;)V`.
Its method hash matches, but its constant-pool hash does not:

- Expected pool: `9be5af719cc23a87f944e51bceff4f10a61d043ba9352870a4b706752967a0e7`.
- Both observed pools: `b6eb2698546644b688cf9fc195a7445dff77fea21a0de5125e5f929440e14411`.
- Both observed/expected method hashes:
  `4e8ecde35f3bcd89eb803b85bd50021fa3c61b7b9ea4394e7c2d78883072252d`.

All 15 saved r4 origins of this class (six distinct class byte strings) were
checked. None has the observed pool hash. Several have the same method hash,
so checking only the method would be insufficient. r7's actual loaded-class
probe recorded six selected classes; HierarchicalTestEngine was not among them.
The present evidence cannot distinguish pool evolution, a transformed definition
or a different definition. No expected hash has been replaced with an observed hash.

## Complete saved-frame inventory

[Every class, method and JVM signature](observed-frames.md), with binding status
and stack/catch counts, is listed separately for Oracle and PostgreSQL.
[CSV](observed-frames.csv) and [JSON](observed-frames.json) additionally retain
loader ID, constant-pool/method hashes and first event sequence. Catch locations
are recorded separately and do not inflate the stack counts below.

BOUND-MATCH means both hashes match a frozen class file. UNBOUND means the class
is absent, even when the old verifier silently did not require it.
BOUND-BUT-MISMATCH is a distinct failure. Package/name categories are descriptive,
not trusted attribution. Support is separated from candidate/application.
Other dependencies include JDBC/pool code and Apache Felix OSGi service machinery;
they are shown explicitly rather than omitted. Classes named GeneratedResultSet
or HikariProxyResultSet are not assumed to be runtime-generated merely by name.

| Category | Oracle classes / methods / unbound classes | PostgreSQL classes / methods / unbound classes |
|---|---:|---:|
| Candidate (ordinary class) | 1 / 7 / 0 | 1 / 7 / 0 |
| Public support (ordinary class) | 1 / 2 / 0 | 1 / 2 / 0 |
| iDempiere application | 47 / 134 / 43 | 46 / 133 / 42 |
| OSGi/Tycho/JUnit framework | 42 / 78 / 20 | 44 / 82 / 22 |
| JDK ordinary classes | 10 / 16 / 10 | 14 / 27 / 14 |
| Generated/hidden-name classes | 22 / 22 / 22 | 22 / 22 / 22 |
| Other dependencies (including Felix) | 12 / 23 / 12 | 7 / 19 / 7 |
| Total | 135 / 282 / 107 | 135 / 292 / 107 |

Each lane has 28 catalogued classes, of which HierarchicalTestEngine has the
one mismatched observed method. No ordinary candidate/support method mismatch
was found. There are 22 observed generated classes per lane: one candidate lambda,
eleven JUnit lambdas and ten java.lang.invoke LambdaForms. No name-recognized
dynamic proxy or generated reflection-accessor class was observed. Ordinary
reflection methods remain listed. Absence from this sample is not exclusion
from a future run.

## Are the events enough?

**Enough for a complete inventory of the frames actually saved in this retained
reference pair; not enough for a full trustworthy runtime catalogue.**

Oracle has 351 events: 264 exception notifications, 42 entries, 42 exits,
one ready, one successful terminal and one VM death.
PostgreSQL has 274: 187 exception notifications, 42 entries, 42 exits and the
same three boundary/terminal events. Exception notifications include caught
exceptions; these counts are not counts of failed tests. Each lane's 84 readback
hashes, event chain and signed receipt bindings verified. The successful terminal
events occur at Oracle sequence 350 and PostgreSQL sequence 273.

The collector iterates all frames returned by thread.frames(), without a depth
cap, at selected posting checkpoints and exceptions whose stack includes
candidate/support, plus the selected terminal callback. It does not record every
method invocation or every loaded class. The two mutant slots never ran.
Saved fields are name, method, signature, line, code index, loader ID and two
hashes. Raw runtime constant pools, raw method bytecodes, module/code-source,
loader provenance, generated-host linkage and bootstrap recipes are absent.
Hashes cannot reconstruct those bytes or prove a hidden class's host.

A **new, separately authorized runtime-provenance census is required**, after the
proposed collector changes. It must collect the missing material on both engines,
cover generated candidate/framework/JDK paths and resolve the pool mismatch.
An observational census is preparation, not a qualification success. Do not
reuse r10's successful business gate as a corrected smoke result.

## Preserved evidence and cleanup

All 2,117 frozen file hashes verified before and after the scan. The signed
campaign terminal, stopping and recovery records and both collector receipts
verified with the existing public key. No private key was read.

- Snapshot: `e5790d832a18ea0272b24a1bfd611ad60aa3f45c340fc68997e3c6ed30409c06`.
- Terminal report: `e58224f7a45f474bd65867889560eeafb75b37f24a9b12952eba12f2a93d81aa`.
- Native plan: `ae882fe49249d86d7cdb25bdd593a160c82529b7a9972f21297cad47e5d00c09`.
- Signed recovery reports 11 owned resources absent; this historical record is
  preserved, not newly issued.
- Fresh read-only inventory at 2026-10-07T16:55:06Z found no containers
  (including stopped), networks or volumes bearing any of the three declared
  r10 owner labels. All nine commands exited zero. This does not prove absence
  of unlabelled/relabelled resources.
- The initial inventory access attempt was denied by the sandbox's Docker pipe
  permission. Its output is retained; the same approved read-only checks then
  succeeded with sandbox escalation. No Docker mutation occurred.

A development error in the new census helper initially applied the unsigned
content-hash verifier to a signed envelope. It failed before writing output;
the helper now uses the existing signed-envelope verifier. This was not a
failure of the preserved evidence.

The [prospective amendment](observer-binding-amendment.md) and
[one corrected smoke draft](j1-smoke-r11-draft.json) await approval and new
provenance evidence. Production observer/replay/admission code and J1 predicates
are unchanged. There is no executable snapshot, authorization or scheduled run
for r11.

## Offline checks and draft limits

Seven focused offline tests passed: signed-envelope verification and tamper
rejection; pool mismatch despite equal method bytes; reporting of unbound
unchecked frames; generated-name non-acceptance; static vendor-name handling;
inventory/hash closure; and the non-executable smoke draft's approval barriers.
They do not qualify the proposed observer implementation, which is not installed.

The r11 draft contains three fresh slot/run identities and hash-only bindings to
the same input bytes and expected outcomes. It proposes a six-hour execution cap
with 7,190 seconds per slot including finalization, and a 1,800-second candidate
timeout. Census/compilation preparation is separate. The exact approved window
must include additional setup/cleanup reserve; no calendar window is assigned.
All native plans, snapshot, publication and Tower decision hashes remain unset.

