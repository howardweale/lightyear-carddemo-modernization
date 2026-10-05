# B06 qualification preparation r6

Operator review; not independent attestation. Zero model calls and zero Docker
runs in this increment. B05, `work/ms94`, template-r1 and J1 predicates are
unchanged. Historical preparation attempts remain intact.

## Private inputs and assembly

All 135 slots have complete, byte-bound private input assemblies: J1 55, J2 41,
J3 39. Each public `*-private-inputs.json` contains input names and hashes only.
The actual bytes are in a new local content-addressed assembly under
`work/b06-admission-r6/private-inputs`; no input values, reference sources or
captures are published. Common blobs are stored once within each group. Every
slot independently binds its source, MS84 checkpoint and full entry multisets,
primary keys, comparison register and datatype inventory. J1 binds its invoice
contract and history bound; J2 binds its private procurement scope and history
bound; J3 binds its private work order, selection and expectations.

The inherited MS84 archive and members are verified before extraction. J2
document table identities were independently read from saved native baseline
captures in both engines and compared. J3 uses the existing independently
derived October work order/expectations. This is input preparation, not entry
admission or native qualification: the complete schema, constraints, row
multisets, private derivation and all-table reconciliation still run for every
future candidate. The native loaded-class identity remains a blocker; these
are assembly specifications, not authorized executable plans.

| Journey | Assembly v6 | Private input assembly |
|---|---|---|
| J1 | `287bff9bc4bfc10d42f69fe2f127f83823676e2c8428637b08032ed7e131514c` | `466851f37dbe1a851719d478ac800912bdfc251f5380afd65de67445cac9093d` |
| J2 | `b144e502b832f377ea090c9ce2ca3de294f342dd46eb58df7c2f52774f113815` | `a94a92ce15d8d7cc258d182c9ff8e7713f8a556c248a88814a1962c68a85256f` |
| J3 | `842c6a3f86bdbf291971534bd23c77aead83340fee0e809631c2825e9b7b4ef4` | `4aa163a3113d8f5339c45e039d435017933a28900ebff746c444942e99ea9b7e` |

The four offline-catalog-r4 corrections are selected by exact revised hash and
an explicit `applies_to_control` field. Editorial reason text has no effect.
Older v5 records and code remain available unchanged.

## Tower authorization

`b06-qualification-group` is an operator decision kind. Its request binds exact
plan, snapshot, public commit and Docker window evidence. `execute_group`
requires a live authenticated `DecisionReader`, checks its key against the
executable plan, rejects the campaign key as the Tower key, verifies the fresh
journal, operator role, outcome and complete bindings, then saves the Tower
proof before any native subprocess. A campaign-signed `authorization.json`
alone is no longer accepted. The campaign signer still signs native receipts
and individual slot records, bound to the verified Tower decision hash.

Executable conversion must receive the trusted Tower public-key hash. No
operator decision has been fabricated or issued by this preparation. Publishing
a plan does not authorize Docker.

Cross-engine native document-label disagreement now produces empty feedback
and equipment suspicion. Offline tests cover the recorded inbox/replay path,
not only the projection function.

## Proposed runtime-resolution Docker window — approval required

Proposed window: **October 5, 2026, 20:00–20:55 PDT**
(`2026-10-06T03:00:00Z` to `03:55:00Z`). This proposal does not assume the Maintec
intake is idle; Howard must approve this exact commit and window before use.

One disposable container, pinned image
`sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
Network none; all capabilities dropped; no-new-privileges; no private mounts,
database containers, credentials, native pairs or model calls. Mount only the
three source files bound in `runtime-resolution-proposal.json` read-only and a
new results directory read-write. Run `python3 /source/ms94_b06_runtime_catalog_worker.py`.

The worker compiles a small observation-only Java agent and a plain JUnit test
that does not extend the application test base or log into a database. Maven
runs offline with the existing Tycho provider and POM configuration. The test
loads the four framework classes without initialization. JUnit loads the two
terminal classes naturally. A transformer returns null, records the actual
load-time class bytes, source location and loader identity, and never modifies
class bytes. `-verbose:class`, generated OSGi runtime configuration, reports and
class bytes are retained locally. Previous baked-in reports are moved aside
before the new test; they cannot satisfy acceptance.

Acceptance requires exactly the no-database test to pass, a resolved
`config.ini`, and one unambiguous loaded identity for each of the six targets.
An absent or ambiguous class is a preserved failure, not an inferred catalog.
The operation must be supervised with a 45-minute container deadline, reserving
the remaining ten minutes for owned-container termination, cleanup inspection
and recording. Maven itself is limited to 40 minutes; compilation to two
minutes. Record real start/end and elapsed duration, preserve failure output,
and verify the named container is absent. No retry is authorized. No host
launcher or Docker action has been executed in this increment.

## Separate J1 smoke draft

`j1-smoke-draft.json` contains three fresh slots: retained reference,
duplicate-invoice-line mutant, and candidate invoice-null-dereference with
direct closed-diagnostic delivery. It has its own private input assembly and
IDs; no slot is reused from the full qualification group. Smoke results cannot
count toward the retained 10/10 qualification or measurement success.

Proposed separate window: October 6, 20:00–October 7, 02:00 PDT. Expected Docker
time is about one hour; reserve six hours for the three finalization-inclusive
7,190-second limits. Both the runtime-resolution result and a later exact
executable smoke plan/Tower decision are prerequisites. This is a draft only.

## Remaining admission work

Core-status items 1–5: native adapters, posting-origin attribution and
finalization are implemented offline; no native qualification credit is
claimed. Private inputs are sealed. Resolved runtime class identity blocks
executable snapshots and conversion. J1 smoke and J1/J2/J3 qualification all
remain unrun and require exact commit/window approval. Measurement additionally
requires the separately pinned 0.160.0 transport, fresh account proof,
preflight, preregistration and launch approval.

Validation: 118 B06 offline tests passed, plus 34 Tower/documentation regression
tests. These include synthetic native-stage seams and confer no native
qualification credit.
