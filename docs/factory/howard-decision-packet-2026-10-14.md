# Howard decision packet — 2026-10-14

**INTCALC: Not releasable.** Fresh loader-domain receipts and effective decisions remain pending.

**POSTTRAN: Phase 2 not run.** Plan preparation and authorization guards are implemented; the exact CI-generated plan must be committed and explicitly approved before comparison.

This packet is a draft, with no signature, activation, release authorization or z/OS confirmation. AI-assisted reviews are labelled as such.

## INTCALC

[The measured verdict](intcalc-releasability-2026-10-14.md) reports the retained main results, the PR328 cross-check, all targeted comparison counts, separate program diversity, source-bound constants and remaining gaps. Raw rc66 records remain unchanged. New CI overlays grant no loader-scenario kill, equivalence, comparison or coverage credit, and remove no mutant sites. The independent receipt cross-check fails on a disagreement with the threshold engine.

## Unsigned requests

- [Effective threshold/2 request](scenario-threshold-effective-request-2026-10-14.json): prepared only; not ready to sign while any listed condition remains unmet. No condition is automatically waived.
- [INTCALC I/O exception](intcalc-io-exception-request-2026-10-14.json): source-bound CBACT04C line189 false edge. The EOF flag begins N, is only set Y, and a TEST BEFORE loop admits N. The first IF tests N before the READ can set Y; no declared public fault seam changes this guard. The full argument remains in io-gap-arguments.json.
- Items 20/23/42, seven constant fields and loader-domain effectiveness: exact fresh CI bindings are pending before their final requests can be issued. The existing dated approvals remain unchanged and conditional where recorded.
- [Historical backfill](tower-backfill-request-2026-10-14.json): incorporates the October 12 scoped acceptances and constants, loader approval, Phase 1 rerun authorization, October 13 R4 template/authority records and October 14 merge-hold lift. Signed-only consumption remains inactive.

## POSTTRAN

The candidate bytes are unchanged. Preparation builds only the compiler image and input inventory, then emits a hashed plan and unsigned request. Execution requires Howard's exact plan and head approval, PR attempt1, verified file/image/input hashes, and an atomic persistent consumed-attempt ref before execution. No automatic retry, model call or candidate repair is permitted. Every differing or indeterminate scenario is recorded as a proposed unresolved entry.

The PR335 replay was **refused before compilation**: run 38600848981, job 115979402188, `rerun-exact-parent-required`. [The preserved log excerpt and hash](release-evidence-2026-10-14/posttran-pr335-replay.json) bind that finding. Phase 1's successful original run remains historical evidence.

## Main health

All 23 post-merge workflows on 8650f58c passed, including all six systematic engineering shards. PR336 merged at 69c9893c. Its latest main workflows were still finishing when this draft was prepared; no failed main run was observed. Final health must be rechecked before handoff.

## B06 Part 6

[The Part 6 evidence-gap report](b06-part6-2026-10-14.json) preserves the supplied brief's account separately from verified evidence. Signed attempt and cleanup receipts have not been located. The ten sequence/thread rows, record counts, heap and phase witnesses cannot be filled from the brief alone. No new B06 run is authorized. Further observer work is not planned; future Java work should start with outcome comparison and use targeted instrumentation only for unanswered questions.
