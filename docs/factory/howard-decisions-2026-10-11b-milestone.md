# Howard's October 11 decisions: conditional approvals and follow-up

[Decision record](howard-decisions-2026-10-11b.json) binds the exact supplied
[decision document](howard-decisions-2026-10-11b-source.md), prior evidence and
[unsigned ten-record POSTTRAN acceptance](posttran-decisions-unsigned-2026-10-11.json).
All ten supplied rows validate against the unchanged review sheet, source and
acceptance hashes. No signature was created. Howard will use the existing operator
flow with reviewer name `Howard Weale`; historical sheet bytes remain unchanged.
The equivalence sample is AI-assisted operator review by Claude, accepted by
Howard, not independent human attestation. The TWO-BYTES mutant is host scoped.

scenario-threshold/2 is conditionally approved as amended, and remains ineffective
until B1 evidence, individual acceptance of remaining arguments, current-head
compiled campaign and dependency checks complete. A recorded conditional approval
is not evidence that those prerequisites have passed.

## POSTTRAN amendment

[Amended plan](posttran-second-opinion/amended-plan-2026-10-11.json):
`bb91aad8d0533118ecf8270348ac509435fc22bec4dbf18611a6b696d89f3bd5`.
[Machine-readable diff](posttran-second-opinion/amendment-2026-10-11.json) is against
`97b105a5f9e1c26b378be927b7fc74e947a051a6ef0c49f03b5ac4ddcfa1d95e`.
Budgets, model, inputs, work orders and Phase 2 gate are unchanged. Results are
labelled **independent model-built candidate**. The exact packet's zero-generation
input-token count request and success/failure are durably recorded before any
candidate generation. A failed count consumes the reserved attempt and allowance.
All calls remain blocked pending `go POSTTRAN bb91aad8d0533118ecf8270348ac509435fc22bec4dbf18611a6b696d89f3bd5`.
The broker is transport-injected and tests use fakes; no credential or live API
request is used by this change. Phase 2 remains unapproved.

The input-count contract is documented in the [official API reference](https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens/methods/count).
It returns an input token count; the model-generation endpoint is separate.

## B06 and B07

B06's October 12 window is withdrawn. The conditional request is for October 13,
9 AM-noon PDT, due October 12 at 5 PM PDT. Exact executable commit/request seal and
Howard's `go B06 <commit> <request seal>` remain mandatory. B3 implementation and
host evidence are maintained on a separate branch. No execution is authorized here.

The [B07 power sensitivity](b07-prefreeze-power-2026-10-11.json) keeps 72 paired
analysis slots per arm. It cannot support an 80% planning-power claim for a 15-point
non-inferiority margin across the tested equal-performance scenarios. This must be
reviewed before freezing. The 14-day two-runner calendar replaces the old 96-hour cap;
model spending remains unapproved and starts only after B06 Part 6 and graph coverage.

[CI timing](ci-times-316-320-2026-10-11.json) preserves exact PushEvent timestamps
when available and distinguishes the workflow-created proxy. Tower source now links
the generated [current status](current-status.md); the deployed runtime is untouched.

Validation: 18 focused offline approval/preflight/review/power and CI-history tests passed;
publication CI must complete before commit-specific merge approval. No merge,
model call, native attempt or operator signing is part of this milestone.

## Plans for Howard

Implementation waits for review of the one-page plans, in priority order: the
generic scenario engine (separate B1/B2 PR), [dual-run prototype](dual-run-prototype-plan.md),
[production and evidence modes](production-evidence-mode-plan.md), then
[parallel candidates](parallel-candidates-plan.md).

## Preserved CI findings

Initial PR CI runs 38175575983 and 38175576007 failed because the generated-scenario
and coverage workflows did not install the declared cryptography dependency now
required by the engineering evidence-boundary test. Both workflows install the
existing control-tower extra before those tests. The tests and boundary remain
unchanged; fresh final-head CI must pass. Historical failed attempts remain visible.
