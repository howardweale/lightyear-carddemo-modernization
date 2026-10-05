# B06 qualification and builder admission separation

October 5, 2026. Operator review, not independent attestation.

Zero-model native judge qualification has no builder process. Conversion now
requires a zero-model, non-measurement draft and all existing exact snapshot,
input, source, image, slot and calendar checks. It does not require a builder OS
probe and does not authorize Docker or measurement. Earlier blocked drafts and
the Defender-blocked AppContainer attempt remain unchanged historical records.

Measurement launch directly authenticates the signed OS probe file named in its
plan, verifies its file hash and binds the tested transport by hash. A callback
returning `True` cannot substitute for this check. The zero-model measurement
preflight uses the same builder gate; passing that gate alone does not claim a
complete preflight. Native judge qualification remains separate from this
measurement preflight, which does exercise the builder boundary.

The change does not weaken isolation: it moves the requirement to the two paths
that use the builder. No builder transport, measurement snapshot or model call
is admitted by this preparation change. B05, `work/ms94`, template-r1 and J1
predicates are unchanged.

Validation covers a real on-disk qualification snapshot without a probe, corrupt
snapshot rejection, model/measurement draft rejection, changed image rejection,
missing/changed probe and transport rejection at both measurement boundaries,
and refusal to start the controller despite all boolean callbacks passing.
Synthetic signature fixtures confer no native or OS qualification credit.
