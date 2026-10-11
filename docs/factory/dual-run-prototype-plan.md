# Dual-run prototype: plan for Howard

Priority 2 after the generic scenario engine. Design only; implementation waits
for Howard's review of this one-page plan. Use public CardDemo batch inputs only.
The executable twin stands in for legacy production and must be labelled that
way; this is not a production or z/OS fidelity claim.

Build an input journal with immutable batch and record IDs, layout/source hashes
and processing-time policy. Run the twin and converted candidate from separate
copies of the same before-images. Compare normalized outputs and state deltas
using only declared normalizations; include rejections, return codes, partial
updates and record order. No write-back or failover into a real customer system.

Report record-level disagreement with input/state lineage, source locations and
keep-or-fix dependencies. Preserve every failed run and unmatched record. A
watermark proves both sides processed the same input prefix; incomplete prefixes
are unresolved rather than called matches. Repeated input tests demonstrate
idempotent journaling, not idempotent legacy posting where the source lacks it.

Acceptance: public INTCALC and POSTTRAN batches, rejection variants, duplicate
non-atomic abend, restart at a journal boundary, schema mismatch and late output.
No discrepancy may be hidden by ordering or balance normalization. Publish the
comparison contract, fixtures, deterministic offline tests and limits in a PR.
No model/native/customer execution budget is requested by this plan.
