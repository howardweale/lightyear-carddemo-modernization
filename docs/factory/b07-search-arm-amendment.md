# B07 plain-search arm amendment — draft, workstream 6

This is an amendment to Parts 3 and 4 of Howard's supplied
`codex-b07-graph-arm.md` (SHA-256
`cde059a89d8e8593540dcd9d4910f919f1182a6e3c46e7caa07d05a0ee4508cf`).
It implements the planning deliverable in `SPEC-factory-sota-upgrades.md`.
It is not sealed, runnable, a spending approval, or an amendment to B06 evidence.
Parts 1, 1.5 and 2 retain all their original coverage, audit and approval gates.

## Part 3 replacement: context arms

The historical B06 curated arm remains the baseline. New arms are graph (G) and
plain search (S, the requested Arm C). Howard selected these two new arms.
A fresh curated drift-control arm (D) is not selected; its alternative estimate
is retained below for transparency only. This selects the draft design, not runs
or spending. No inference that historical B06 is complete or nonvoid is made.

Both G and S remove the curated `api_reference` block. G gets its mechanically
assembled graph block; S gets only the public contract, pinned source identity,
and neutral search/read tool instructions, never a curated list of target symbols.
Publish byte-level prompt diffs; all non-context prompt bytes must match B06.
The analyst and diagnostic path are unchanged and receive neither new tool set.

S exposes `search_code` (literal ripgrep query over pinned, allowlisted public
upstream paths) and `read_file` (bounded line range). No shell, arbitrary regex,
network, writes, working-directory escape, symlink traversal, credentials,
historical candidates, Lightyear support code, expected values or campaign data.
Tool implementations must accept structured arguments, not shell fragments.
Paths resolve inside a verified source tree at commit
`731515dcdd5278b843db33b9d3109d155b881951`. Pin the ripgrep version too.
Return sorted path/line results, source SHA-256, truncation flags and deterministic
response bytes. Source hash mismatch or a leak canary fails closed.

G and S use identical total retrieval-call, response-byte, input-token, model-call,
compilation and wall-clock caps. The exact retrieval caps must be declared during
Part 3 implementation and measured by the zero-model audit before sealing; this
document does not invent an approved cap. A truncated response consumes its real
budget. No hidden retry or free response. `public_api`, if retained in both arms,
must have identical hash-verification and access scope; document its confounding
role separately. S has no graph tools or graph-derived hints. B06 policy is unchanged.

Record every request, completion order, response hash/size/token count, source
revision and refusal. Record application symbols actually used by the candidate,
with provenance separating graph retrieval, search/read retrieval and prior prompt
context. Losing attempts and budget failures remain in the trial record.

Required tests before Part 3 acceptance: exact single-block prompt diff; B06
refusal of new tools; deterministic search order and bounded reads; traversal,
symlink, canary and digest-mismatch refusal through both tools; aggregate budget
accounting across tool calls; zero graph access in S; unchanged analyst/diagnostic.
These implementations are gated by Part 1.5 runtime coverage and Part 2 audit.
This amendment does not claim those tests or coverage gates have passed.

## Part 4 replacement: preregistration

Use the same J1/J2/J3 public contracts, two excluded pilots and 24 analysis slots
per journey in each new arm: 78 trials, of which 72 enter analysis. Match each
slot to its B06 inputs and seed. Interleave G/S within slot using a frozen seeded
allocation; retain the schedule and RNG implementation/hash before any outcome.
If D is approved, insert six matched curated repeats per journey at preassigned
random positions. D's 18 repeats estimate drift; they cannot fully remove
noncontemporaneous B06 bias or replace a complete contemporaneous control cohort.

Pre-register these three per-journey comparisons: G minus B06, S minus B06, and
G minus S. Report pass-rate differences with the requested Newcombe hybrid-score
95% intervals (label their marginal construction), plus exact paired McNemar
results and the full paired discordance tables. Declare all nine journey/comparison
hypotheses; Holm-adjust the nine confirmatory p-values. Report raw p-values too.
Intervals remain unadjusted descriptive intervals and are not simultaneous claims.
Do not pool with B03/B05 or treat pilots as cohort outcomes. Missingness, stopping,
void rules and diagnostic policies apply separately to each arm exactly as in B06.
Prespecify first-try pass, repair conversion, calls/compiles/time/cost per pass,
retrieval calls/tokens, and candidate symbol use as secondary endpoints.
Howard still chooses the noninferiority margin and any sample-size amendment.

Claim template when G does not show superiority over S:
"On this public reference application, graph retrieval did not demonstrate a
higher final cohort pass rate than bounded plain search under the preregistered
budgets. The estimate was [difference], with [interval] and [paired counts].
This is not proof of equal performance; [precision, drift and missingness limits].
These nonproduction results received operator review, not independent attestation."
Use this wording only after complete, nonvoid results and the declared analysis.
A positive G-vs-B06 result alone does not establish graph-specific value.

## Additional limits and cost options

| New work only | Trials including pilots | Model-call cap | Compile cap | Serial full-limit trial hours |
|---|---:|---:|---:|---:|
| G only (original proposal) | 78 | 390 | 234 | 155.7833 |
| G + S | 156 | 780 | 468 | 311.5667 |
| Optional D addition | 18 | 90 | 54 | 35.9500 |
| G + S + D | 174 | 870 | 522 | 347.5167 |

Each trial retains 5 model calls, 3 compilations and 7,190 seconds. The original
96-hour campaign cap cannot cover even one arm if all trials consume their full
serial allowance. No cap is silently increased: sealing requires an explicit
calendar/campaign-budget reconciliation and cleanup reserve. Do not promise a
completion date from these maxima or authorize concurrent native evidence runs.
Historical B06 costs are excluded from this incremental estimate.

The matching JSON uses the observed per-call token mix and historical price table
in B05's `cost-estimate.json`, plus an explicit 4,000 additional uncached retrieval
input tokens per model call as a planning assumption, not an approved token cap.
It reports short-context, long-context and no-cache sensitivities. These are
API-equivalent estimates at historical rates, not current pricing, a Codex bill,
a forecast, or a spending cap. Reprice the frozen client/model and measured tool
responses before requesting a specific model budget. No model call is authorized.

## Gate and milestone status

Delivered: a reviewable search-arm design, pairwise analysis/negative-claim
template and calculated options. No model, Docker or native run occurred.
B06 is not yet a complete nonvoid baseline, and B07 static/runtime coverage and
audit are not complete. Therefore no B07 sealing date is available. Howard selected G + S with no fresh curated drift arm. Later gates require the actual coverage proof, audit, merged
implementations, frozen client/model/images/context, zero-model preflight,
approved budget/window and full-plan review lead. None is bypassed here.
