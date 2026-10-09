# B06 preparation status

## October 9 observer practice r1 frozen; exact Tower approval pending

[Observer practice r1](observer-practice-r1/README.md) prepares one fresh retained J1
Oracle/PostgreSQL pair for 12:30–15:30 PDT; latest start 13:20:10 PDT.
Full validation passed: 113,572 frozen files, 767 public source files, 39 frozen tests.
Snapshot `cb142c2805b7d7d8947afbeae1026b6353cfbbac4f979890d8be3a71ee9ade13`;
plan `fec26f2cba5a6a4a497a590087a3cf51e202a8eb36407e38724550b471943ed1`.
No native execution, Docker or model calls during preparation. The one-pair practice
has no qualification or measurement credit. Earlier failed runs remain preserved.
Fresh exact public-bound Tower authorization is required before arming the launcher.


## October 9 census r3 window2 failed; offline performance correction tested

R3 window2 stopped on Oracle in the first J1 retained-reference slot. Exact
collector error: `com.sun.jdi.VMDisconnectedException`, while reading a class
array in `PostingObserver$Generation.enter(PostingObserver.java:196)`.
Signed report `eb19052ae94619234c8308ee1421c2a903a39ec0c066382fc157168bc4c57c58`
remains failed: 2,212.687 seconds, four slots unstarted, zero passes/models or
qualification credit. The partial audit authenticated 7,485 Oracle events;
there were no posting checkpoints. All owned resources were absent after cleanup.

The [offline repair report](../../../../b06-census-r3-performance-repair-milestone.md)
documents two reproduced defects: per-byte JDI reads while the JVM is suspended,
and charging observer preparation against the execution watchdog. The corrected
collector uses exact bounded batch reads; execution timing begins at worker
launch, with the outer slot/window limits unchanged. Host lifecycle diagnostics
now record preparation, worker launch/return, watchdog expiry and stop requests.

The identical large-class host fixture improved from 10.594 to 0.625 seconds
with the same 34 events and five byte-exact definitions. Fresh production-collector
host replay passed 10 checkpoints / 62 frame observations. This is an offline
correction, not a successful native census. The old disconnect's initiating stop
reason was not recorded; watchdog expiry is a strong timing/code inference,
not an independently observed kill reason. No Docker, Tower request, replacement
snapshot or native run was made for this repair. Monitor remains paused.

## October 9 census r3 replacement window ready for exact Tower decision

[Window2](census-v2-r3-window2/README.md) binds 10:00-21:00 PDT; latest launch
10:50:50 PDT. Full freeze and verification passed: 113,634 files, 767 public
code files, 23 frozen tests. Only five prospective slot windows changed; all
other bytes and outcomes remain exact. Zero Docker/native/model calls. Fresh
public-bound Tower authorization remains required. R2 stays failed and the
original r3 window stays unlaunched. No qualification or measurement credit.

## October 9 census r2 failed; r3 correction preparing

R2 stopped on Oracle J1 with `java.lang.IllegalStateException: ambiguous generation catch`.
Finalization then lacked `b06-clock-evidence.json`; it did not complete. All four
remaining slots stayed unstarted. Signed terminal report
`417ff6e3ce43fc3c656a2ccde4d3911709a218756c487807ca0eacdb2fcb0388`
is preserved. [R3](census-v2-r3/README.md) replaces method-based catch guessing
with observed handler activation and adds an explicitly incomplete failure audit.
Host JDI regressions and the 205-test suite (10 skips) passed. The proposed
08:30-19:30 PDT replacement window still requires a fresh frozen plan and exact
Tower authorization. No Docker or model calls; no qualification credit.

## October 9 morning census r2 prepared; Tower decision pending

The [r2 executable preparation](census-v2-r2/README.md) passed all five offline
assemblies, 113,610 frozen hashes, 766 public source comparisons and 20 focused
tests. Window: October 9 07:00-18:00 PDT; latest full-budget launch 07:50:50 PDT.
Snapshot `b1bd1b72ea82486c10ab306f054581f4c6351dc0d6e8261d04bd4e7779516f0d`;
plan `17c4aac5fc98bbef39ed1de9af940592420328bf5d0cac20583977ee3f1a1bf7`.
R1 expired unlaunched and remains preserved. No Docker, model calls or native
pairs during preparation. A fresh exact Tower decision is required; nothing is
armed. No journey qualification or measurement credit. Operator review, not
independent attestation.

## October 8 five-path observer-v2 census executable prepared

The [census preparation](census-v2-r1/README.md) seals five fresh zero-model pairs
into a new 113,610-file snapshot. All five native plan assemblies and the final
frozen offline verification passed. The window is October 8 20:00 to October 9
07:00 PDT; latest full-group start is 20:50:50 PDT. Exact publication and a new
Tower decision remain required before Docker. No census pair has run.

This advances per-slot assembly and executable preparation, not native
qualification. Observer-v2/generated provenance on both engines, J1/J2/J3
qualification, measurement admission and its preflight remain. No model calls,
no B05/work/ms94/template-r1/J1 predicate changes. Prior failures remain failed.
Operator review, not independent attestation.


## October 8 observer-v2 native integration and host target proof implemented

The [integration report](observer-v2-integration-r1/README.md) records the new
explicit v2 collector, plan/freeze/broker wiring and independent replay. External
JDI origins, the approved narrow pool comparison, JDK module/provider checks and
per-use generated targets are implemented. The production collector's public
host fixture replay passed all 10 checkpoints / 62 frame observations, with six
lambda and six LambdaForm proof occurrences. All 201 offline B06 tests passed.
Zero Docker, models or native pairs; this is not Oracle/PostgreSQL qualification.

Generated storage fields receive data-layout proof only, never executable-frame
trust. Unsupported generated executable recipes remain fail-closed. The five-path
census still needs complete per-slot v2 manifests, its new frozen executable and
an exact public-bound Tower decision/window. No run or new authorization was
created. Earlier statuses below are historical; failures remain preserved.


## October 8 archive copy and offline five-path inputs complete; observer v2 integration incomplete

The [exact archive copy](built-catalog-r1/terminal/README.md) passed: 204 archives,
132,922,294 bytes, signed report and independent replay verified, 291 frozen files
unchanged and actual owned resources absent. Zero native pairs or models.

The [offline census assembly](built-census-offline-r1/README.md) indexes 122,650
class entries from 204 archives, 44 application bundles and 27,834 JDK classes.
Fresh host extraction of the bound module image matched all saved JDK classes.
Five fresh private input assemblies contain 82 hash-verified input references.
Fourteen offline integrity tests pass. No Docker/model call occurred in assembly.

This does not complete the approved observer-v2 boundary: external defining
origins, native use of the approved pool rule, LambdaForm per-use target proof,
JDK provider/loader bindings and full native replay integration remain. The new
five-path preparation is explicitly non-executable; no new Tower request, window
or snapshot is claimed. The Oct 9 generated-proof deadline remains. The archive
prerequisite is complete, but earlier wording must not imply it was the only
remaining executable-census gate.


## October 8 direct built-runtime launch implemented; census not launched

The [native integration](built-native-r1/README.md) now provides direct Java launch,
separately bound compiled classes, read-only application mounts, exact external
JDI command admission and offline replay. All 61 source inputs (218 class
references), including five census paths, are prepared from authenticated prior
compilations. Focused offline tests pass; there is no native qualification claim.

The full runtime catalogue still needs the 204 measured Maven/runtime archives
(132,922,294 bytes; 62,978 expanded class entries). Their exact hash-only selection
is prepared for a distinct Tower-gated copy, with no JVM/build/database/model
execution. The requested 15:30 PDT census reservation does not waive this gate.
No census Tower request or native launch has been created. Existing failures,
B04 void status, B05, work/ms94, template-r1 and J1 predicates remain unchanged.


## October 8 build-once practice passed; native integration remains blocked

The [terminal result and handoff](build-once-r1/terminal/README.md) records one
build and two direct consumers, 1,031.157 seconds, all captures/replays passed,
44 application bundles exact except the bound probe class, 102/102 source-only
temporaries, unchanged 777-file freeze and actual owned cleanup. The image is
retained locally. Zero models/native pairs; practice is not qualification.

The offline hash-bound handoff is prepared and 17 related tests pass. No new
Tower request, Docker window, evidence driver execution or measurement launch.
The native worker still uses Maven: direct built-image launch with external JDI,
per-slot class/parameter binding, the five-path provenance census, journey
qualification and final preflight remain. The handoff is non-executable until
its separately bound host adapter and exact authorization are ready.



## October 8 application-identity triage completed offline

The [22-bundle triage](application-identity-triage-r1/README.md) classifies every
changed entry: the 21 source bundles have 21 properties timestamp comments (b)
and 21 generated manifests (c), zero changed classes (a) or other resources (d).
A draft two-rule normalization is enumerated per file and bundle; five tests
and all 42 observed entry pairs pass. No normalization is active.

The test bundle's probe class is identical, but seven non-candidate entries differ
(two properties, three descriptors, two nested JAR resources). Its 324 nested
class entries are identical. A class-only exemption cannot fix those resource
differences. Exact exclusion inventory and a build-once amendment/practice draft
are prepared for review. All 98 differing byte files (21,399,748 bytes) are
preserved locally with hashes. No Docker, models, Tower request or publication.
There is no historical-content admission requirement. Earlier failures unchanged.


## October 8 operator amendment: no historical content requirement

Howard removed the historical-content requirement. The [prospective amendment](runtime-history-amendment/README.md)
and plan schema /3 omit prior-run comparisons and validate current captures.
Missing old content and supplemental r9/r10 differences are no longer historical
admission gates. Current capture, source-only, Tycho, warning, cleanup, snapshot
and later closure-to-measured identity checks remain. Legacy r9/r10 records are
unchanged. 32 offline tests passed; all 44 saved r10 current captures validate
under the new check, while the legacy report reproduces exactly. No Docker,
new freeze, Tower request or launch.


## October 8 frozen practice r10: pipeline/replay complete; acceptance blocked

The [terminal review](runtime-fidelity-r10/terminal/README.md) records the single
authorized run: 387.672 seconds, zero models/native pairs, owned cleanup confirmed,
776 frozen hashes unchanged. The corrected census audit completes. Census,
source-only transients, Tycho, warning baseline and frozen-byte checks pass;
application-content acceptance remains false for 40 unavailable historical copies.
Exact outcome: `frozen-practice-six-checks-not-satisfied`.

Supplemental r9/r10 comparison covers all 44 application bundles: every entry set
matches, but only 22 bundles match allowed normalized bytes. Twenty-one source
bundles retain host-qualifier/timestamp changes, and the test folder retains seven
changed build-artifact entries. No policy was widened. No Tower request or retry.
A future baseline/identity or build-once decision is needed; repeated runs alone
do not resolve these blockers. Operator review, not independent attestation.


## October 8 frozen practice r9: failed final audit; captures and replay completed

The [terminal review](runtime-fidelity-r9/terminal/README.md) preserves the exact
failure `; finalization: tycho-file-url-required` at the six-check census. Bundle
ID 0's `System Bundle` location was parsed as a file URL before the ID branch.
Practice duration 388.922 seconds; producer/offline replay completed and actual
owned cleanup verified. All 776 frozen files are unchanged. Zero models/native
pairs. No retry or Tower request.

Separate offline diagnosis confirms 350 bundles, 102/102 source-only transients,
correct Tycho binding and no new baseline warnings or structured error files.
The four retained historical application copies now match exactly (1,577/141/
62/65 entries), restoring all 39 omissions. Forty historical full copies remain
unavailable; 44/44 comparison is not claimed. This diagnosis does not turn the
failed frozen acceptance into a pass.


The census correction is implemented only in the unfrozen development checkout.
Nine focused tests passed; the corrected checker was exercised offline against
the saved output and still refuses overall acceptance because historical
application content is missing. No frozen bytes or result were changed.


## October 8 closure fidelity r9: prepared offline, practice approval pending

The [r9 preparation](runtime-fidelity-r9/README.md) replaces broad filename/path
filtering with a single bundle-content view used by capture, producer, replay
and comparison. JAR bytes stay exact; folder exclusions name six run-written
paths and their reasons. The 61-message warning baseline is the intersection
of r4, r5b and practice logs (74 severity lines each). New messages refuse.
Frozen practice now binds a committed executable and common plan; all six checks
are recomputed before a Tower request or evidence launch. No Docker/model calls
or Tower request in this preparation. Forty historical application captures
remain unavailable, so 44/44 historical equivalence is still blocked. Earlier
failures and the passed-pipeline/failed-six-check practice remain unchanged.


## October 8 practice r8b pre-window audit: blocked

The [six-check audit](runtime-lifecycle-r8/six-check-audit.md) confirms the exact
350-bundle census, 102/102 source-only temporary bundles and correct Tycho fork
binding. It does **not** confirm evidence readiness: the four historically
comparable application bundles lose 39 entries in practice captures; 40 other
historical bundle contents were not retained. The log contains 71 warnings and
three error-level messages despite Maven success and no structured error file.
The practice binds file hashes but no exact committed executable/snapshot/Tower
plan. Therefore no evidence window/request proceeds. The prior passed practice
report describes pipeline completion only; all earlier results remain preserved.
This audit ran offline, zero Docker/model calls. Operator review, not independent
attestation.


## October 8 corrected practice r8b passed

The user-authorized fresh non-evidence practice passed in **387.000 seconds**
(6 minutes 27 seconds), including worker finalization, producer, offline replay
with an ephemeral in-memory test key, and owned cleanup. Independent read-only
owned-label container/network/volume checks were empty afterward. No production
signer or Tower authority was used. Zero model calls, databases and native pairs;
network disabled. This is not a qualification result or measurement admission.

All 350 observed bundles were processed, including 44 application copies and
102 preserved source-only transient copies. The worker recorded the absent
`org.idempiere.test/target/test-classes` dev output; classes loaded from
`target/classes`. Folder-selection policy `/2` records this absence explicitly,
keeps manifest roots mandatory and rejects loaded classes from absent roots.
98 offline tests passed before the rerun, including complete pipeline replay
and negative cases. Host/worker hashes remained unchanged during the run.

Practice report SHA-256:
`49f654a1e0f8b3df00cb560c69ad271b734c2751a14c4c6473bb46d49d58ba90`.
Measured inventory SHA-256:
`37107d2f9253c18ceef2110ed06cb12d4c9f8dabfc28bb4f62fdaef3317b7f46`.
See [r8b review](runtime-lifecycle-r8/practice-r8b-review.json) and the
[explicit capture rule](runtime-lifecycle-r8/optional-dev-output-fix.md).

r7 and the failed r8 practice remain preserved. A future evidence run still
requires a fresh exact snapshot, publication and Tower decision; none was
created or launched here. Operator review, not independent attestation.


## October 8 r8 non-evidence practice result

Howard approved one bounded practice container. It failed after **127.532 seconds**;
owned-container/network/volume absence was independently checked after cleanup.
Zero models, native pairs and databases; no network. No retry or Tower request.

The agent completed its observation and matching completion marker: 350 bundles
and 102 preserved transient source copies. Maven succeeded. The worker then
failed at `application-capture` with exact error
`ValueError: runtime-folder-root-missing`. Producer/replay was not reached.
Practice report SHA-256:
`83ca2716ec5a6a1e6a4003d0384ac611228c59915fe9839cccc6efc9c86c21f7`.
Observation SHA-256:
`6a4f411e1a9c66570c0e7da11f3eedc9127439bca81351bfd8c7b1c3c01d64b7`.

Partial application copies 9, 10, 22 and 48 precede bundle 52,
`org.idempiere.test`, in the recorded capture order. Its dev.properties declares
`target/classes` and `target/test-classes`. The compilation log and loaded-class
catalogue confirm use of `target/classes`; `target/test-classes` is a suspected
missing root, not an established fact. The old error omitted the path, and the
full test-bundle root was not retained. The prospective error now includes the
bundle, declared root and path; missing roots still refuse. A unit test checks
that exact diagnostic. No capture/admission policy has been widened.

The one-shot practice source, plan, results and failed r7 snapshot remain
unchanged. See [practice review](runtime-lifecycle-r8/practice-review.json).
Native admission remains blocked. A fresh practice requires separate approval;
no qualification success or independent attestation is claimed.


## October 8 PR275 follow-up

Host observer, replay and runtime-closure repairs are tested; native readiness is still blocked. See [review r3](review-r3/README.md). Core items 1-2 need native provenance/qualification; item 3 needs the runtime closure, scoped artifacts, pinned-image overhead, corrected pool approval and a fresh five-path plan/Tower decision. Items 4-5 remain not measurement-ready. No new Docker window or model launch is authorized by this code publication.

| Current state (October 7 review follow-up) | Status |
| --- | --- |
| Native readiness | r10 failed; r11 rejected by Howard (operator-reported); no replacement authorized. Inventory-only and scoped runtime extraction prepared offline; generated-class/native runtime proof remains incomplete. See [review follow-up](review-pr269-271/README.md). |

The dated entries below are historical. Core items 1–2 remain natively
unqualified; item 3 needs the artifact/provenance prerequisites and a fresh
five-path executable/Tower decision; items 4–5 are not measurement-ready.

## October 7 r9 native failure and offline correction r10

The r9 retained-reference slot ran on both engines but failed as
equipment-suspect: JaCoCo transformed the executing classes relative to the
catalog, and J1 received the purchasing comparison register. The other two
slots never started. The [r10 diagnosis and correction](smoke-bindings-r10/README.md)
preserves all failed evidence and 2,106 frozen files, disables coverage in the
prospective B06 worker with live/offline JVM admission, validates journey-specific
registers before assembly/entry, and repairs the archive replay directory layout.
Fresh hash-only private manifests cover 55 J1 qualification slots and three smoke
slots. No new snapshot, authority, Docker window, native pair or model call.
Core items 1–2 remain natively unqualified; item 3 needs a fresh executable smoke
plan and exact Tower approval; items 4–5 remain incomplete. Operator review, not
independent attestation.

## October 6 J1 smoke failure and correction r9

The authorized smoke failed before candidate execution because the readable slot
name violated the inherited native journey resource-owner contract. The failed
report, absent-resource checks and 2,106-file integrity audit are preserved.
The [r9 correction](j1-smoke-r9/README.md) binds fresh native journey IDs and
validates them before assembly/freeze/conversion. The new exact plan and snapshot
require a new Tower decision; earlier approvals are not reused. Zero models ran.
No J1/J2/J3 native qualification or measurement readiness is claimed. Historical
“no smoke has run” statements below describe their publication time, before this
failed attempt.

## October 6 PR262 review follow-up r8

The [r8 report](review-r8.md) records the implemented closed loopback HTTP
broker, explicit file credential-store argv, supervised builder-login scripts
and operator-key-bound smoke preparation helper. 139 B06 offline tests passed
in 29.881 seconds;
all 2,106 existing smoke snapshot files reverified unchanged. No model call,
Docker command or native pair ran. Actual builder login and the final
account/WFP/client transport probe are still pending. Howard approved the
new isolated Tower and confirmed its key; the exact group is public at
`ec639ba6f56940e235e04b41c1cb3f013c25e568`, with all 11 files byte-verified.
The isolated Tower now uses `C:\ProgramData\Lightyear\B06TowerData-r8`.
Howard authorized the exact three-slot smoke; latest decision hash
`2dd8fc24cb7f550c778b83411c1b15943f7a0d433af6c8410eaf078b0f19774d`.
Three decisions refer to one group. Fresh-journal/controller admission is still
required within October 7 03:00–09:00 UTC; no smoke has run and no measurement
is authorized. See the [r8 milestone](milestone-r8.md). Earlier proofs and
failures remain preserved. Operator review, not independent attestation.

## October 6 approved runtime-resolution probe

The [runtime-resolution report](runtime-resolution-r7/README.md) records one
passed approved Docker attempt: 100.594 seconds including verified cleanup,
zero native pairs and zero model calls. The six actual loaded class identities
are now resolved; both JUnit terminal classes came from Tycho's Surefire bundle
under `.m2`. A separate read-only audit checked 1,905 recorded output files.

The local three-slot J1 smoke snapshot has 2,106 verified files and complete
per-slot input closures. Twenty relevant offline tests pass. Its group plan
and exact Tower request remain pending identification of the distinct B06 Tower
public key and a verified public plan commit. The October 7 03:00–09:00 UTC
window remains conditional on that exact Tower decision; no smoke has run.
Core items 1–2 remain natively unqualified, item 3 has this local smoke
preparation but no authorized group, and items 4–5 remain incomplete.
Operator review, not independent attestation.

## October 5 HTTP transport design r7

The [host broker/argv draft](transport-r7/README.md) separates host tools from
the restricted builder and specifies per-session loopback HTTP authentication.
The [preregistration draft](measurement-preregistration-draft.md) declares the
0.160.0 versus B05 0.155.0-alpha.9.2 client deviation. Neither is a transport
freeze or launch approval. Windows denied both S4U login-status task attempts;
actual builder login availability remains unverified. Earlier pinned/denial
proofs and the approved runtime-resolution probe are unchanged. Zero Docker
commands, model calls or native pairs in this increment.

## October 5 qualification and pinned transport r6

The [r6 milestone](milestone-r6.md) records PRs #257 and #258: sealed hash-only
private input manifests for all 135 qualification slots, Tower-bound group
authorization, equipment suspicion for cross-engine document-label disagreement,
and the passed zero-model dedicated-account probe using pinned Codex 0.160.0.
The probe includes actual denied reads, positive/missing controls, IPv4/IPv6
network denial and verified cleanup; earlier failed attempts remain preserved.

The 55/41/39 assemblies are still **not executable qualification freezes**.
Resolved native class identities remain blocked on an explicitly approved Docker
window. Native qualification, full model/MCP transport integration and immutable
measurement preflight remain outstanding. No Docker run, native pair or model
call was made in this r6 increment. Operator review, not independent attestation.

## October 5 offline integration r5

The [r5 report](execution-r5/README.md) records a J1 observer-to-inbox runtime
diagnostic test, v2 Windows admission through Controller.launch, native mutation
and evidence-boundary integration, and a bounded qualification finalization
driver. All 108 B06 offline tests pass. No Docker command, native pair or model
call ran in this increment.

The new 55/41/39 assembly specifications bind the four corrected compilation
sources, but are **not executable plans**. The extracted JUnit terminal classes
have conflicting Maven-cache copies, and the resolved test classpath was not
saved. No loaded copy is claimed. Posting-cause projection and recorded delivery
now have offline tests; complete private slot assembly remains unsealed and all
native qualification credit is still withheld. The Codex-process account proof
is a separate increment in PR #256.

## October 5 host boundary and offline preparation

PR #252 separates builder-free native qualification from the mandatory signed
builder probe in measurement admission and preflight. PR #253 records the approved
[offline compilation and class catalog](offline-catalog-r4/README.md), including
preserved failures, actual Docker time and owned-container cleanup.

The [Windows local-account probe](windows-denial-r4/README.md) now passes for the
exact tested identity and tools/private directories. Its signed admission record
requires actual native access-denied codes, a successful positive control and a
distinct missing-file control. Earlier failures remain unchanged. The future
measurement transport must bind this evidence; complete executable preflight is
still outstanding. This probe used zero Docker runs and zero model calls.

Against core items 1–5: items 1–2 have compiled catalogs and preparation code but
remain natively unqualified; item 3 still needs integration/finalization and
executable plan assembly; items 4–5 remain incomplete, with the host denial-proof
prerequisite now demonstrated. No native pair or model launch is authorized.
Operator review, not independent attestation. Earlier entries below describe
their original checkpoints.

## PR243 execution-blocker follow-up

The [execution-admission-r3 report](execution-admission-r3/README.md) records
terminal-origin binding and actual zero-model inbox delivery/replay code, J1's
unchanged-judge bridge and database fault hook, strict slot/snapshot assembly,
hash-bound OS denial admission, and class-bound lock-SQL checking. These are
preparation increments with no native qualification credit. J1's preflight now
explicitly requires a candidate-origin runtime exception delivered directly.

The attempted host OS probe was blocked by Windows security before a child
started; its signed failure is preserved. No successful OS denial is claimed.
Pinned-image compile/catalog work needs Docker approval. Actual private input
assembly, legacy mutation/evidence-boundary integration and qualification
finalization also remain before executable conversion. The 55/41/39 schedules
have new explicitly blocked assembly specifications, not executable freezes.
October 17 remains a conditional go/no-go; currently no-go. Proposed windows
and estimates are in the report. Zero Docker commands and zero model calls.

Core items 1–3 have additional tested code but remain unqualified; items 4–5
remain incomplete. B05, `work/ms94`, template-r1 and J1 predicates are unchanged.
Operator review, not independent attestation.

## PR241 review follow-up (October 4)

The [review-r2 report and draft schedules](admission-review-r2/README.md) record
candidate fault typing, evidence-bound rejection progress, plan-bound clock and
runtime checks, and synthetic posting-origin controls for both engine formats.
There have been no Docker commands, native pairs or model calls in this increment.
A local JDK syntax compilation of the observer passed; it is not target-image
qualification. Earlier failures and compilation records remain preserved.

Items 1 and 2 have additional tested preparation, with native acceptance and
production attribution/delivery still pending. Item 3 now has fixed review drafts
of 55 J1, 41 J2 and 39 J3 pairs, binding known source and image hashes and listing
unmaterialized native hooks and input/class-catalog prerequisites. These are not
executable freezes or permission to run Docker. Items 4 and 5 remain incomplete.
The builder capability boundary rejects tools/ reads, but OS-level confidentiality
under an actual B06 executable has not yet been demonstrated. This remains a
mandatory admission gate. Operator review, not independent attestation.


## October 4 admission preparation update

The [J2/J3 adapter preparation](native-adapters-r1/README.md) is merged through
PR #241. The [posting observer increment](posting-observer-r1/README.md) adds
external JVM collection and offline integrity replay, but does not yet establish
causal attribution or qualify diagnostic forwarding. Fifty B06 preparation
tests pass. Two reference compilation checks and three observer compilation
checks passed with no network, database execution, JVM attachment or model calls;
all owned compiler containers were verified absent. Hash-only records and costs
are in the linked manifests. No native qualification slots have been attempted.

Against items 1-5 below: item 1 now has adapter/reference code and offline
compilation; native acceptance, exact plan assembly and remaining register/scope
admission are pending. Item 2 has collection/replay code; causal derivation and
all native provenance controls are pending. Item 3 has no frozen qualification
plan yet. Items 4 and 5 remain incomplete. Publication is preparation only and
does not authorize native qualification or measurement. B05, work/ms94 and
template-r1 remain untouched. Operator review, not independent attestation.

## Earlier implementation checkpoint (October 3)

This is an implementation checkpoint, not a qualification result, executable
freeze, preregistration or launch authorization. No B06 model calls, Java
compilations or native qualification pairs have been run by this preparation
increment. B05 remains closed and frozen; B04 remains void.

## Implemented and tested

The [generic template and diagnostic policy](template-r1/README.md) were frozen
and signed before the J3 work order was written. Their hashes are
`0119df1c02fe9e725d51fb7e63ad9be40e70385fadb32daed39ebdcc7f05aee0`
and `441ddd2c3a4271d682c9b19e68706a0c01f66abe4db2e640039186541cd85bf5`.
They have not changed during this increment.

The materials work order remains private. The current work-order hash is
`244f8a909658b9ea3378eefcc091710787b4dfbfcad8076787cc4682977c2d75`,
bound by [the revision 2 seal](j3-work-order-r2-seal.json). The earlier
[draft seal](j3-work-order-seal.json) is preserved. Read-only inspection of the
admitted seed showed that the draft's second existing locator and costing
configuration assumptions were unavailable. Revision 2 makes setup explicit
before execution; it uses no candidate output and changes no generic prompt or
diagnostic policy. The novelty search covers available repository history,
not external implementations or model training data. Review is operator review,
not independent attestation.

The preparation modules provide:

- A deterministic 78-slot schedule: two pilots per journey, then 24 blocks with
  one trial of each journey in a seed-derived order. The actual campaign seed
  is not selected or preregistered yet.
- Real-clock calendar checks for a 96-hour campaign including pauses, with
  390 calls and 234 compilations maximum. Per-trial limits remain five calls,
  three compilations and 7,190 seconds including finalization, with the inherited
  600-second finalization reserve. No clock manipulation is introduced.
- Primary analysis per journey with Wilson intervals, pilots excluded, no
  pooling, and no headline unless all three complete journeys reach 21/24.
  J3 always counts. A journey void suppresses its rate without rewriting the
  other journeys' outcomes. Incomplete results are labelled interim.
- A controller core using the Tower boundary, admission before `started.json`,
  provider-unavailable pauses and at most three same-slot retries before candidate
  evaluation. Retries retain budgets and the original deadline. A deadline or
  export/signing failure during finalization prevents the next slot while
  preserving any verdict already written. There is no model-launch entry point.
- J2 supplemental invoice-type, accounting-date and posting-period predicates.
  They must be combined with the inherited procurement judge's quantities,
  monetary amounts, allocation signs, ownership, write footprint and native
  reconciliation checks; they are not a replacement judge.
- J3 predicates for document links, movement and inventory quantities/signs,
  cost records, valuation, cost details, and exact accounting facts by schema,
  period, account and locator. Expected accounts come from admitted pre-state,
  not candidate-provided expectations. Wrong cost, account, quantity sign and
  negative-debit representations are rejected in synthetic tests.
- A fail-closed cohort-18 attribution predicate requiring signed provenance,
  a candidate-owned prior post or lock on the same document, independently
  verified native readback, and non-candidate fault exclusions. Feedback contains
  only the frozen closed fields. Missing, forged or conflicting proof sends
  nothing and remains equipment-suspect.

Forty-three tests passed on Windows across the six B06 preparation modules and the
existing Tower boundary/export tests. The latter include the real writer and
reader running concurrently. These tests do not substitute for the full native
B06 preflight. A controller-core integration test additionally exercises real
Tower signatures and the journal through launch, a cross-trial same-journey
pause, continue into the next slot, a wrong-pause rejection, equipment-suspect
pause, void and a verified export read. Synthetic accounting rows and signed observer fixtures are test
inputs, not qualification evidence.

## Remaining admission work

1. Finish native adapters and retained reference implementations for J2 and J3.
   Bind full normal entry admission, all-table capture/footprint reconciliation,
   private expectations, typed failures, real-clock evidence and cleanup before
   any control can count. J1 business predicates must remain unchanged.
2. Implement and qualify the trusted posting-origin observer and its independent
   replay. The attribution predicate alone cannot establish what the candidate
   did. A candidate-authored trace, a source-code pattern or a signature over an
   unverified assertion is insufficient. Qualify prior-post and prior-lock
   controls plus support, outside-origin, wrong-document and genuine equipment
   faults on both engines and all applicable journeys.
3. Freeze exact zero-model qualification plans, references, mutants, image
   digests and diagnostic expectations. Run and independently audit each
   journey, including retained references 10/10, applicable business and
   invoice-type controls, dated controls and delivery controls. Requalify J1
   on the B06 executable. Preserve every failure; do not replace failed slots.
4. Complete the executable controller integration: supervised worker adapters,
   signed per-attempt archives/replay, verified journey-scoped void decisions,
   secondary metrics, terminal reporting and fail-closed admission of all
   qualification hashes. Core unit tests use a boundary fixture, and one core
   integration test uses the real Tower authority; the native executable has
   not passed preflight.
5. From a new immutable executable snapshot, run one complete zero-model
   pipeline for each journey, the real Windows Tower writer/reader, bound and
   deliberately wrong-bound decision round trips, offline replay and actual
   owned-resource cleanup checks. Only then publish measurement preregistration,
   exact costs, latest launch time and the Howard-operated launch runbook.

For an October scenario, the implemented 96-hour policy computes the latest
possible launch as October 27 at 23:59:59 UTC (16:59:59 PDT). This is a calculated
boundary, not approval to launch. The actual plan must bind its freeze date,
scenario dates and launch guard after qualification; J1's B05 work order remains
unchanged. No measurement snapshot or model launch is admitted by this document.

## Runtime closure r4 window2 failure — October 8, 2026

The 09:30 PDT authorized runtime-closure attempt failed after 137 seconds;
Maven completed successfully. The exact worker error was
`ValueError: unambiguous-surefire-configuration-required` at frozen
`runtime_worker.py:100`, in `main()` during effective Surefire configuration
discovery, after Maven/test/class capture and before runtime inventory and
signed resolution. The controller recorded `ValueError: runtime-worker-failed`.
Signed terminal report:
`ddef351691fe724f7bbbb7c55d9cbf40f27d871a8ac8805dc3f55562c3ef3235`.
All 275 frozen files were unchanged; signed cleanup and a separate read-only
owned-container absence check passed. Zero native pairs and model calls.
The failure is preserved and has not been rerun or reclassified.

The worker assumed Maven-Surefire `classPathUrl.N` properties. Tycho 4.0.8 uses
its test-provider properties and an Equinox `-jar` / `-testproperties` launch;
the old worker also omitted `target/surefire.properties` from capture. The saved
attempt has no copy of that file. No replacement properties or successful
receipt may be fabricated to complete replay.

[The r5 offline correction](tycho-runtime-r5/README.md) adds a separate closed
Tycho reader, exact file capture, observed fork argv/test bundle identity,
`b06-resolved-runtime/3` production and replay, and preserves `/2` history.
The new parser checks the preserved command/configuration layout successfully;
complete producer replay remains blocked by missing properties, new observation
fields, measured inventory and a successful signed launch receipt. This is
preparation only; remaining items 2–5 above are not admitted by it.
Operator review; not independent attestation.


## Runtime closure r5b failure and r6 offline census — October 8, 2026

r5b failed after 391.297 seconds at `runtime_inventory.measure`, `p.stat()`,
with exact worker error `FileNotFoundError: [Errno 2] No such file or directory:
'/tmp/tycho_wrapped_source10021272085316246407.jar'`. Controller:
`ValueError: runtime-worker-failed`. The Tycho properties/command checks had
passed; completed inventory/resolution had not. Signed terminal report:
`f182d02a75c63c0c628e861014c3a41dbe59f46ad5c3db46426bfd2408c45fd9`.
All 281 frozen files unchanged; signed cleanup and read-only owned-label
container/network/volume absence verified. Zero model calls/native pairs.

[The r6 correction and full saved-location census](transient-source-r6/README.md)
cover **203 `/root/.m2`, 44 `/application`, 102 `/tmp`, 0 other** non-system
bundles (349 total, plus one system bundle). All temporary paths match the
Tycho wrapper shape, but the old evidence cannot prove source-only eligibility.
New in-process copy/header/identity and loaded-class evidence is required;
the producer and replay re-inspect preserved bytes. `/2` and `/3` history and
the Tycho properties fix remain intact. 67 focused offline tests passed.

**Another blocker was found offline:** `org.adempiere.ui.zk`,
`org.adempiere.server` and `org.idempiere.webservices` changed both path and
manifest bytes/version between the two saved attempts (build qualifiers
`202610081632` versus `202610081715`). These non-source bundles stay exact.
Other Maven-generated application artifacts have no demonstrated byte stability.
Do not consume a new Tower window until an explicit deterministic runtime/build
strategy resolves this. No new snapshot, request, Docker run or model call in r6.
Operator review, not independent attestation.


## Prospective application content identity r7 — October 8, 2026

The required saved-catalogue comparison found **4 application classes compared,
4 identical, 0 different**, all in `org.adempiere.base`; no loaded-class records
exist for the three timestamped bundles. Every saved class blob was verified.
Supplemental retained-folder inspection found **2,891 identical class entries**
across UI ZK (1,301), server (59), webservices (145) and Ant (1,386), with zero
changed/added/missing entries. Artifact contents are not a loaded-class census.
All 44 application bundles and their coverage gaps are in
[the r7 report](application-content-r7/README.md).

Howard explicitly approved prospective content-identity implementation while
**keeping native admission blocked pending complete evidence**. The implementation
normalizes only the Bundle-Version qualifier, Built-By, Bnd-LastModified and
Build-Timestamp main-header values; all class/resource entry bytes, entry names
and other manifest differences stay exact. Source-only transient identities and
exact Maven-cache/JDK/framework/launcher hashes retain their separate rules.
Per-run application copies, paths, qualifiers, archive hashes, byte-replayed
production and the measured posting-class consumer are implemented. The rule
passed against all four complete saved folder bundles (1,845 file entries total).
80 focused offline tests passed. No Docker/model/Tower run or native admission.
This supersedes the proposed deterministic-build remedy in r6, not its evidence.


## 2026-10-08 r7 diagnosis, recorded before lifecycle code changes

Literal search of saved maven.log for `B06 runtime closure probe failed:`: zero matches.
Maven exit 0 / BUILD SUCCESS; the JUnit test returned after 0.097 seconds.
Exact worker exception at runtime_worker.py:89:
`FileNotFoundError: [Errno 2] No such file or directory: '/results/closure-observation.json'`.
No observation or error file exists. Partial bundle copies show capture began.
JVM exit interrupting asynchronous capture is the leading explanation, not a
recorded exception or proven exit mechanism: the test did not wait and a
non-daemon thread cannot prevent System.exit. The evidence cannot establish
a more exact cause. Writes before the final readiness check and recursive
in-memory application-folder capture are additional confirmed code defects;
there is no evidence of an r7 exception from either.

Preserved copies (not a complete runtime catalogue):

| Path | Bytes | SHA-256 |
|---|---:|---|
| runtime-transient/1.jar | 67213 | `4a22db763a964b1333e968a36d93363fbaa0f3a2543c6d58773d4c9fca041ed6` |
| runtime-transient/2.jar | 525528 | `acf1661b9987f5aa8c1da3a69eafa76a6c8c1dbd7b6b14ecd18ff0b564e47e3c` |
| runtime-transient/3.jar | 581 | `601a60288a1ab720b0eb105b20a69478ce13c002fe6a1d7e33c00e4286fabe26` |
| runtime-transient/4.jar | 83609 | `f6dfb5e4bc733570c8e649f3cf7f1f275a2ade6d2217d1e8c1be84d74ef91a92` |
| runtime-transient/6.jar | 34718 | `7a6db56c61d467f42d24355ed1b880f189d046e03291238067978021923db2d7` |
| runtime-transient/7.jar | 158683 | `aaf8d17c90a8bcecd66dbe12c1d5416efb6b1efdfd3b47f5ca671057692c119e` |
| runtime-application/9.jar | 40573 | `fc3b7114464c315f288711973741ce0ba131b6225cfd00e0fb2f74081320bfaf` |

Terminal ae86ac24880c3dd5baa89a5d58d6a59ea400229ca380f3917862d8fb0e4370de:
failed, 123.969 seconds, cleanup passed. Signature and 285 frozen hashes
verified; actual owned-label container/network/volume inventory was empty.
Zero model calls/native pairs. r7 remains failed; evidence is unchanged.
Operator review, not independent attestation.


## 2026-10-08 r8 offline lifecycle correction

See [r8 review](runtime-lifecycle-r8/README.md). 92 focused tests passed; final
10 targeted checks passed after the last mutation guard. Real host Equinox
rehearsals preserve specific errors, including unavailable Windows process argv;
350-bundle synthetic worker/producer/replay passed. No Linux practice result or
new qualification claimed. Practice plan `65c596c2514a03d57ab17f88a5d20929126fe9f5a7df7bb5577951535be7d6e8` is prepared, not authorized
or run. Zero Docker/model calls; no Tower request. r7 and every prior failure
remain preserved. Native admission stays blocked.


## October 8: build-once preparation r1

Howard approved implementing build-once preparation. [Design and bounded practice](build-once-r1/README.md) now define one pinned-image build and two direct Equinox consumers on its read-only derived image. Non-candidate application content remains byte-exact; only the enumerated probe class differs under separate compiled/observed/capture binding. No draft source normalization is enabled. Historical content is not an admission requirement; all earlier failures remain preserved.

Preparation adds offline capture/replay, host-JVM byte-recorder and mocked lifecycle tests. The preserved r10 data is readable as 44 application bundles, 207 runtime artifacts and 102 source-only JARs. This does not pass a new native run. No Docker commands, models or Tower request were executed in this increment. The proposed practice needs an approved one-hour window, with 45 minutes work plus 10 minutes cleanup reserve. The derived image digest can only be reported after that build. Native admission remains false; generated-class proof, five-path census, J1/J2/J3 qualification and final preflight are still outstanding.
