# Equipment 06, A3: stopped on invalid entry-admission signature

The one frozen A3 campaign stopped on its first slot. The retained reference
against the admitted checkpoint returned a native business pass, but publication
verification rejected its full entry-admission signature. The campaign failed;
13 slots were never started. No perturbed qualification slot or paired diagnostic
comparison ran. A3 is unqualified and B04 remains blocked.

The exact error was `CalibrationError: Invalid full entry admission signature`.
The new A3 entry checker returns an already sealed object. The native wrapper
passed that object directly to the signer, including its existing content hash.
The standard envelope verifier excludes the content-hash field from its signed
body, so the resulting envelope fails verification. This is an A3 evidence
implementation defect, not a candidate business failure or a demonstrated
diagnostic value-invariance failure.

Independent replay of the sole available archive through the unchanged frozen
`tools.ms94_a3_publication` reproduced the same rejection. The signed archive
receipt, manifest, native receipt and diagnostic bindings checked; all decoded
evidence and implementation checks preceding the rejection completed. The
terminal audit checked 11 valid signed records and found the one invalid
entry signature. Separately recomputing underlying entry checks and verifying
the signature against the reconstructed already-sealed payload confirmed the
cause for diagnosis only. This does not repair the invalid envelope, constitute
successful full-entry archive replay, or earn qualification credit. Complete
gate and diagnostic archive replay were not reached after that rejection.

Actual Docker inventories before and after terminal replay confirmed all nine
owned resources absent: seven containers, one network and one volume. All 911
frozen source files remained unchanged. No evidence was amended, re-signed,
reinterpreted, restarted or replaced. Private archives and captures remain local.

| Cost / outcome | Value |
|---|---:|
| Campaign elapsed seconds, including controller publication/replay | 467.547 |
| Native pair seconds, included in campaign elapsed | 435.078 |
| Independent terminal verification seconds | 29.109 |
| Frozen archive replay rejection seconds, included in terminal verification | 15.421 |
| Started native pairs / lane executions | 1 / 2 |
| Unstarted slots / completed paired comparisons | 13 / 0 |
| Model calls / model tokens | 0 / 0 |

The corrected checkpoint preparation remains separately passed: 269.906 seconds,
27.734 seconds replay, zero candidate executions, compilations or model calls,
and five resources absent. The earlier checkpoint preparation failure remains
separate at 215.641 seconds plus 8.859 seconds replay. Neither preparation result
qualifies A3. The 24 focused/documentation checks were preparation only.

The follow-up is paused under the declared failure rule. A future correction
must sign the unsealed entry body and verify the resulting envelope before
candidate execution, receive suitable tests, and use a fresh public freeze and
full native A3 qualification. It cannot resume these 13 slots or repair this
frozen evidence retroactively.

A1 and revised A2 remain accepted with their separate limitations and costs.
The original wait-only fault remains unqualified. B03 remains 12/20 first-try,
95% Wilson 38.7%–78.1%, nonvoid. These controls add no autonomous cohort success.

[Signed failed report](report.json), [terminal failure verification](terminal-verification.json)
and [independent archive rejection](publications/01/independent-verification.json)
are published with safe metadata only.

## Original prospective declaration

Howard requested correcting the checkpoint binding and running A3. The corrected
fresh checkpoint preparation passed and independently replayed. Its actual owned
Docker cleanup was verified. The original failed preparation remains unchanged.
This plan follows A1 and revised A2; it does not authorize any B04 model call.

## Exact schedule

Each row executes once against the original admitted checkpoint, then once against
the genuinely perturbed and independently admitted private checkpoint:

| Control | Native Oracle/PostgreSQL pairs | Required result |
|---|---:|---|
| Unchanged retained A1 reference | 2 | Complete business pass on both checkpoints, no diagnostics |
| Missing rollback stimulus and wait | 2 | Exact missing-rollback contract violation, both engines; lock witness retained |
| Reversal-allocation assertion | 2 | Exact declared runtime diagnostic |
| Invoice null dereference | 2 | Exact declared runtime diagnostic |
| Shipment API rejection | 2 | Exact declared runtime diagnostic |
| Test-only support throw | 2 | Empty feedback and equipment-suspect |
| Nonnumeric order identifier | 2 | Exact invalid-identifier contract violation, both engines |

These are 14 fresh pairs, zero model calls, an eight-hour campaign cap, no restarts
and no replacement slots. Stop on the first unexpected native result, broken
evidence, cleanup failure or unequal exported diagnostic bytes. Report every
started outcome and every unstarted slot. No control earns autonomous success
credit. The original wait-only omission remains unqualified; the authorized
stronger missing-stimulus-and-wait control is used unchanged from revised A2.

## Native checkpoint evidence

The private derived checkpoint changes stored product-price amounts, on-hand
quantities, price-row primary keys and active application table identifier
sequences while preserving row counts and structure. It was created by real SQL
against isolated native databases, not by rewriting logs or expected captures.
All 60 post-transformation constraint probes and the unchanged schema and
reconciliation admission checks passed, then independently replayed.

For every perturbed run, the frozen recipe executes on a fresh disposable copy
of the original seed. Complete native captures must prove the original starting
multisets, exact per-cell transformations, unchanged structure, and exact derived
admitted multisets. The existing schema preparation and all entry constraint
checks then run normally. Full entry admission is checked before every candidate,
including early-throw faults, and independently replayed from every archive.

The two retained-reference runs additionally qualify this new checkpoint
restoration path with the unchanged complete business judge. Every planted Java
source is byte-identical to revised A2; the retained source is byte-identical to
A1. The judge, observer, support, exporter and isolated application executor are
unchanged. New modules bind the checkpoint preparation and paired schedule only.

## Exact diagnostic comparison and publication

Compare canonical exported diagnostic bytes directly for each checkpoint pair;
also require identical equipment-suspect flags and dispositions. Comparing only
hashes, exception classes or verdicts is insufficient. Runtime candidate frames,
public stages and allowed provenance fields must still meet their original exact
expectations. Support throws export no feedback and remain equipment-suspect.

The plan, declaration, source and snapshot manifest must be publicly pushed and
verified before signed authorization and a single launch. Private checkpoint
inputs are content-addressed in the plan; their values and native archives remain
local. Every signed archive replays the unchanged complete gate, full entry
admission and diagnostic projection. A separate terminal replay and actual owned
Docker inventory verification are required after termination. Keys stay in place
and never enter containers. No cloud or organization API is used.

Only safe signed plan/declaration/authorization/progress/report, publication
receipts and verification records are public. Preparation, native qualification
and independent replay costs are separate. B03 remains 12/20, Wilson
38.7%–78.1%, nonvoid; all earlier measurements and failures remain unchanged.

This is a bounded leak test of the declared private-value perturbations, not a
proof covering every possible private value or another journey. Operator review
is not independent human source attestation. Even a successful A3 does not itself
launch B04: the exact new 23-slot B04 snapshot, plan, declaration and diagnostic
allowlists must be publicly frozen before generation under its original caps.
