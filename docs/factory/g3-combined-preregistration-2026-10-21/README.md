# G3 combined COPAU and B07 request preparation

This adds an unsigned review packet for the first COPAU factory run and the
three-arm graph comparison. It is not a runnable request, sealed preregistration,
model-spend authorization or activation. Existing COPAU decisions remain:
openai-responses / gpt-5.4-2026-03-05 for all three roles, USD10 total for that
original scope. The comparison does not inherit that spending approval.

Read [analysis-plan.md](analysis-plan.md), [cost-estimate.json](cost-estimate.json)
and [request.json](request.json). The request binds exact SHA-256 hashes of the
plan and cost estimate, plus current-main source blobs. Final executable,
private expected-bundle metadata, trust/journal, schedule and operator decisions
remain explicit nulls. Do not import or sign this preparation schema.

The proposal keeps 72 analysis trials and six excluded pilots per arm across
J1/J2/J3: 234 trials for on-demand, packed and plain search. It changes the old
G/S design, primary endpoint, retrieval-eligible roles, multiplicity and call
ceilings explicitly. The plain-search adapter and zero-model parity audit remain
gates; this documentation does not claim those implementations exist.

Illustrative planning costs are USD177.45 on-demand, USD99.45 packed and
USD177.45 plain search, including pilots; USD454.35 comparison total plus
USD1.215 illustrative COPAU = USD455.565. These assume unmeasured token volumes
and are not a forecast. Proposed token ceilings instead reserve up to USD702
for the comparison plus the existing USD10 COPAU cap (USD712 scenario).
Infrastructure charges and overhead are excluded. Rates were checked against
[official model documentation](https://developers.openai.com/api/docs/models/gpt-5.4)
on 2026-10-21; the estimate records their scope and repricing conditions.

At the old7190-second trial limit, all234 trials require467.35 serial hours.
Two ideal runners at12hours/day need19.4729days before overhead; the former
14-day window is not sufficient for that full-limit scenario. Do not silently
increase concurrency, extend the calendar or shrink the cohort.

Howard's combined cost, comparison cost, wall-clock and window fields remain
blank, as requested. Preserve the already-answered COPAU model and USD10 cap.
Before requesting final execution approval, finish the listed bindings, estimate
from measured zero-model prompts, and present the complete combined packet.
A code/document merge approval is separate from execution and activation.

Every arm, including null/negative results and losing trials, must be published
after an approved run in dated records backed by immutable Release assets.
The analysis plan contains the reporting template; no outcome is fabricated.
No local tests, campaigns, models, signing or activation were performed.
