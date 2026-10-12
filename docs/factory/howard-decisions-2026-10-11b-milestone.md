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

The following original proposal remains historical. The dated
[dedicated transport and attempt-1 milestone](posttran-dedicated-phase1-milestone.md)
supersedes its dispatch/preflight status: operator preflight is outside the
reservation ledger and attempt 1 has completed. The old sealed plan remains
unchanged. Phase 1 validation and separate Phase 2 approval remain outstanding.

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

## Current register integration

The generated current status includes the two additional Howard-approved keeps:
duplicate transaction posting retains its non-atomic RC12 behavior, and negative
cycle debits retain the legacy over-limit calculation. The register bytes match
the B1/B2 branch (LF SHA-256
`22ff2cd34c41b672ca307584e104451e7ae83d723bb0387c18e2c9c49ef74769`).
The earlier two-entry decision artifact remains unchanged and reproducible; five
focused historical-decision regressions passed.

On head `1b0b2e1574e14f12a4ada339853664545f1dc7d7`, verification run
38175904711 encountered a pinned public-ECR PostgreSQL image rate limit after
three acquisition attempts. Its application Maven tests passed before that
infrastructure failure. The failed attempt remains preserved; it is not reported
as green. The subsequent documentation/register integration requires fresh CI
on its new exact head, so no redundant retry of the superseded head is needed.

2026-10-12 correction: the [dedicated plan](posttran-second-opinion/dedicated-transport-plan-2026-10-11.json) `bb53fd6de1afed29fc1064f986c6c2dadc5d709b93c9732c50a67077aaeb2919` supersedes `bb91aad8...`; its token-count preflight is outside the reservation ledger and consumes zero attempts.
