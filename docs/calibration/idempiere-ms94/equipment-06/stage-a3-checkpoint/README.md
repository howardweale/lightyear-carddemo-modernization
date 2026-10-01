# Equipment 06: A3 checkpoint preparation failed

The single frozen preparation run stopped before admitting a new checkpoint.
The recorded error is `CalibrationError: Schema captures must reference the same
MS84 checkpoint`. The new catalog capture used a derivation-recipe lineage field,
while the existing schema verifier requires the shared MS84 checkpoint lineage.
This is a preparation implementation defect, not a candidate business failure
or evidence that diagnostic value-invariance passed or failed.

Both real database transformations completed. Their complete native captures
passed the declared per-cell, structure and row-count audits; each engine's
30 post-transformation constraint probes passed. Those partial checks do not
admit a checkpoint. Schema assessment stopped, no admitted derived checkpoint
was written, and no planted candidate or diagnostic comparison ran.

Independent verification repeated both native transformation audits and reproduced
the exact schema-verifier exception with the unchanged frozen code. All signed
records checked, and actual Docker inventory confirmed all five owned resources
absent. All 892 frozen files remained unchanged. The failed run was neither
edited nor restarted; its captures remain local.

| Cost | Value |
|---|---:|
| Failed native preparation elapsed seconds | 215.641 |
| Independent evidence replay and cleanup verification seconds | 8.859 |
| Isolated database pairs | 1 |
| Candidate executions / Java compilations / model calls / model tokens | 0 / 0 / 0 / 0 |

The follow-up is paused under the failure rule. A3 remains unqualified and B04
remains blocked. The concrete repair is to bind new native catalog observations
to the admitted predecessor checkpoint as the unchanged schema verifier requires,
while retaining the derivation recipe in separate provenance. Such a correction
requires a new source version, new freeze and fresh preparation; it cannot be
applied retroactively to this failed run. A3's paired native fault qualification
still needs its own implementation, freeze and execution afterward.

A2 revision 1 remains passed: all 18 intended results, all 18 archives replayed,
90 signatures verified and all 162 resources removed. Its original wait-only
predecessor remains failed and separate. B03 remains 12/20 first-try, Wilson
38.7%–78.1%, nonvoid. This preparation cost is separate from all qualification
and measurement costs.

[Signed failed report](report.json), [independent verification](terminal-verification.json)
and [cleanup receipt](cleanup.json) are published. No native captures, raw
checkpoint values, archives or secrets are included.

## Original prospective preparation declaration

This is a separate, zero-model preparation run. It does not qualify A3 or admit
B04. A1 and revised A2 have passed and their terminal evidence is published.
Howard authorized native A3 followed by B04 only after all prerequisites pass.

One fresh isolated Oracle/PostgreSQL pair starts at the admitted checkpoint.
The existing preparation runner checks exact entry row multisets and the existing
schema and constraint probes. In these disposable databases only, the new worker
then changes stored product prices, on-hand quantities, price-row primary keys
and future application identifier sequence values. It changes no schema,
candidate source, public support, observer, judge or diagnostic exporter.

The recipe is deterministic: stored prices become twice the old price plus one,
stock quantities become twice the old quantity plus three, price-row identifiers
increase by ten million, and active table identifier sequences increase by the
same amount. The price-row key must have no incoming foreign keys; all existing
constraints remain enabled. Existing rows, relationships and structure must be
preserved. This limited perturbation does not cover every possible private value.

The worker captures complete native before/after/entry states. The host repeats
the per-cell transformation audit independently, rejects changes outside the
three declared tables, checks identical schema and row counts, reruns all 30
constraint probes in each engine, and reconciles the derived checkpoint using
the existing admission policy and prior witnesses. It never rewrites a capture
or sets admission based on a synthetic expected result. A successful result
must be independently checked before its checkpoint can be bound into A3.

The source snapshot, recipe, signed plan and declaration are published before
execution. The preparation has a two-hour cap, no restarts, no replacement run,
zero candidate executions, zero Java compilations and zero model calls. Actual
owned Docker cleanup must be verified; captures and all private checkpoint rows
remain local. Signing authority stays in place and never enters a container.

After successful preparation, the A3 controller and independent verifier still
need implementation, review and a new prospective freeze. Each of the six
revised planted faults must then execute natively against both the admitted and
derived checkpoints. Their exported diagnostic bytes must match exactly.
Checkpoint preparation and unit tests cannot substitute for those native pairs.
Any difference stops qualification; B04 remains blocked.

B03 remains 12/20 first-try, Wilson 38.7%–78.1%, nonvoid. The original A2 wait-only
failure remains unchanged; revised A2 qualified the stronger missing-stimulus-
and-wait control instead. All earlier outcomes and costs remain separate.
