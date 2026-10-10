# Proposal: retain anomalous observer runs as indeterminate evidence

October 9, 2026. **Design only; not implemented or authorized.**

Recommendation: consider this for bounded diagnostic practices after strict
offline lifecycle tests exist. Do not enable it for qualification or measurement
until the evidence-boundary and replay changes have been reviewed separately.
It would not retroactively change any failed run or establish the current cause.

An unmatched event would produce a signed structural anomaly with its event-set,
request, thread, method, depth and active generation identities. The affected
generation and conservatively its thread/descendant definitions would become
unobserved. Collection could continue within the original time, event and disk
bounds. Resume failure, transport loss, corrupt ordering or audit exhaustion
would still stop collection because a trustworthy boundary could not be kept.

The final report would list every anomaly and unobserved interval. If an interval
overlaps a required class definition, generated target, posting checkpoint, clock,
SQL readback, entry proof or diagnostic provenance, the verdict must be
**indeterminate**, never passed. Unknown overlap counts as overlap. A thread's
absence from a later checkpoint is insufficient to exclude influence: objects
and generated classes can escape across threads. A global indeterminate verdict
is the safe initial policy; narrower attribution needs an independently replayable
dependency proof.

Affected consumers include the observer lifecycle replay, generation/Class identity
binding, adjacent-target proof, posting gate, diagnostic admission and qualification
aggregation. All must reject an incomplete required region; the raw application
exit code cannot override it. Signed receipts need separate fields for completed
execution and complete observation. Missing observations may never be normalized
away or silently replaced by candidate-provided logs.

Tests must cover an anomaly before entry, during nested generation, at return,
on exceptional unwind and across threads; required and apparently unrelated
checkpoints; escaping generated classes; tampered/deleted/reordered anomaly
records; audit overflow; early transport death; terminal aggregation; replay of
old receipts; and strict production defaults. A run with any unresolved required
region must be unable to earn qualification or measurement credit.

The benefit is a longer diagnostic trace from one bounded practice. Risks include
masking an actual observer defect, losing attribution after an apparent recovery,
and operators mistaking application completion for validated equivalence. Visible
indeterminate status and fail-closed aggregation reduce those risks but do not
prove the observer correct. Howard's explicit decision and a new reviewed contract
are required before implementation.
