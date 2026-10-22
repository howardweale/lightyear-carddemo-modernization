# G3 analysis plan: proposed amendment, unsigned and not frozen

This preparation joins the first COPAU F8 run with a B07 comparison request.
It authorizes no execution. COPAU remains a separate engineering demonstration,
outside the comparison denominator. No result, benefit or activation is claimed.

## Changes from 11 October

Preserve J1/J2/J3, 24 matched analysis slots per journey per arm and two excluded
pilots per journey per arm. Replace G versus S with three proposed arms:
O (graph on-demand), P (graph packed), S (plain search). There are 72 analyzed
and six pilot trials per arm, 234 trials total. No fresh curated drift arm.
Do not reduce the sample to fit the prior calendar or interpret older power
simulations as power for this new three-arm family.

The primary endpoint changes from final cohort pass to first-attempt pass.
The three contemporaneous pairwise contrasts replace the old single primary
G-S contrast. Historical B06 comparisons are exploratory only here; preserve
their old nine-hypothesis family in any separately reported historical analysis.
The old analyst-without-tools condition changes: Planner and failure Analyst
are eligible for retrieval in O and S, Builder is forbidden in both.
P retains packed context with no live retrieval. This estimates a context-mode
policy effect, not the isolated effect of graph topology or Analyst access.

## Arms and parity

O uses the G2 five-tool explicit allowlist, approved public projection,
read manifest, isolation scanner and network denial. P uses the same approved
projection and frozen packing policy, with zero live retrieval. S uses only
literal search_code and bounded read_file over the identical pinned public
source corpus, with no graph hints or curated symbol list. The S adapter and
its refusal/scan/budget fixtures must be implemented and pass CI before sealing;
G2 does not itself implement a plain-search mode.

Freeze byte-level prompt diffs. All non-context instructions, role model
snapshots, reasoning settings, public contracts, judge, images and diagnostic
rules must match. Builder may receive validated evidence selected by the plan,
not direct tools. Do not share candidates, conversational state, memory,
receipts or guidance learned from another trial. No embeddings or G4.

Proposed equal per-trial ceilings across all arms: 3 attempts, 2 repair loops,
14 billable model requests, 600000 total input tokens, 100000 total billed
output tokens (including reasoning), 3 compilations and 7190 elapsed seconds.
No individual prompt may exceed 272000 input tokens. Requests, failed calls
and retries all consume the same limits; no hidden retries. P has zero retrieval;
O and S have at most 8 shared retrieval calls across Planner/Analyst/attempts,
8192 bytes per complete result and 65536 bytes total. Packed disclosed context
has the same 65536-byte evidence ceiling. Count all context and repeated history
in model-token totals. Equal ceilings do not require equal actual consumption.
These are proposed design limits, not approved cost or wall-clock caps.

Require a zero-model audit proving compatible controllers, exact disclosure
accounting and source parity before binding these numbers to an executable
work order. Reject oversize complete results; do not silently truncate a scan.

## Allocation and estimand

The analysis unit is one journey/input/seed slot, matched across O/P/S.
Use the same pinned input and seed manifest in all arms. A matched seed is a
blocking label; it does not promise deterministic provider output or an API
seed parameter. Record whether each provider actually supports that parameter.

Within each journey's 24 analysis slots assign each of six O/P/S orders four
times. Freeze a reproducible seeded shuffle (proposed seed 20261021), exact
schedule, RNG implementation and hashes before any model spend. Balance arm
positions across two isolated runners and time blocks; every arm must run on
both runners. Freeze six pilot schedules separately. Do not choose a runner,
order or slot after seeing an outcome. Native-run concurrency requires separate
authorization. The previous 14-day/two-runner calendar does not transfer.

Primary intention-to-treat denominator is all 72 preregistered analysis slots
per arm, equally weighted by journey. First attempt succeeds only with a
nonvoid pass from the frozen judge before any repair. Admission failure, budget
exhaustion, refusal, timeout, missing result or incomplete attempt counts as
no demonstrated pass. Publish reason counts. Never exclude difficult slots
after observing outcomes. If campaign cancellation leaves slots unrun, retain
them in the table, identify them as unrun and withhold a complete-campaign
superiority claim. Infrastructure reruns require a prospectively frozen,
outcome-blind policy; retain original costs and attempts.

## Primary inference

Report O-P, O-S and P-S first-attempt pass-rate differences, paired 2x2 tables
per journey and pooled, and the exact two-sided paired sign/McNemar p-value
conditional on discordant pairs. Enumerate signs within each journey stratum;
the pooled statistic is the sum of signed discordances. Conditional on the
stratum discordance counts this reduces to the exact Binomial(D, 0.5) tail.
Use p=min(1,2*P[X<=min(b,c)]) for b/c discordant totals; p=1 if D=0.
Holm-adjust these three p-values with family alpha 0.05. Superiority requires
a positive declared contrast and its adjusted p below 0.05.

Report descriptive conservative 95% paired-difference intervals: bound each
of p(b) and p(c) with exact binomial Clopper-Pearson intervals at 97.5% coverage
(1.25% per tail); subtract upper/lower endpoints. Label these pooled planning
intervals as unadjusted descriptive bounds, not simultaneous coverage and not
marginal Newcombe intervals. Provide per-journey results as descriptive.
No noninferiority/equivalence conclusion is authorized by a nonsignificant
superiority test. The previous 15-point margin and low power caveat remain
historical; this amendment makes no new noninferiority claim.

## Secondary outcomes

For every arm and slot publish attempts and repair loops, final pass, total
model input/cached/output/reasoning tokens, billable successful/failed/retried
requests and cost, retrieval calls and bytes, elapsed time and divergences found.
Start elapsed time at trial admission and stop at pass, refusal or limit;
report external queue time separately. Report loops among passes with the
pass denominator, and all-trial attempt/loop counts including failures; never
encode failure as zero loops to pass.

Define divergences as distinct frozen judge check IDs reached with evidence,
deduplicated within a trial. A model's unsupported allegation is not a finding.
Private expected values and reference traces stay private; publish IDs/counts
only after approved public sanitization. Report paired differences and raw
distributions; secondary analyses are descriptive, with no unregistered
significance claim. Cost per pass uses every arm cost including failed trials;
if zero passes, report undefined rather than zero. Pilots are excluded from
efficacy estimates but included in costs, timing and the released inventory.

## Freeze and publication

Before the first paid call bind this exact plan hash to a reviewed unsigned
combined request, then require verified Howard-signed approval of the final
scope, budget/window and all executable bindings. Freeze executable commit,
model/effort, work orders, private expected-bundle digest/size/count (no values),
judge, projection/approval/scan, source image, schedule, runner parity and
analysis implementation. Keep public operator trust, current trusted journal
and key IDs explicit; no trust provisioning or signing is performed here.

Publish every arm, including null/negative outcomes, losing trials, refusals,
pilots, missingness and stopped campaigns, as dated public records with an
immutable Release asset manifest. Never commit large traces or private data.
Pre-register the release schema and sanitization checks before execution.
Post a new dated amendment and obtain approval before changing frozen analysis;
never silently edit this dated plan.

Plain-language reporting template, usable only after approved complete runs:
'Across [N] matched public-application trials per mode, on-demand graph achieved
[rate], packed graph [rate] and plain search [rate] first-attempt passes.
The on-demand differences were [effects and intervals]; [superiority finding
with adjusted p-values, or no demonstrated superiority]. Costs were [all-arm
totals] and elapsed times [summaries]. [Missingness/precision/generalizability
limits]. These engineering results do not establish production acceptance.'
Publish the same template for a null or negative result. No investor benefit
claim is available before the measured evidence.
