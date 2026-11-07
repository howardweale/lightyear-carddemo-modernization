# Verified model bake-off

Status: Planned design and bounded router-loading change. No evaluation, model
call, spend, routing-policy activation or qualification is granted by this spec.
The qualified-run packet, freeze, admissions and eight gates remain unchanged.

## One work order, every candidate in evidence

Planned evaluation: N preregistered model snapshots independently produce a
target for the same immutable work order, starting source, public context,
tool permissions and attempt/token/cost limits. Each candidate gets an isolated
workspace and no access to another candidate's output or diagnostics. Record
provider-specific prompt serialization and tokenization differences. Keep the
judge, legacy reference and comparison rules fixed before generation.

The deterministic, zero-model Verdict Engine judges every output, including
unchanged, malformed and incomplete outputs. Record EQUIVALENT, NOT EQUIVALENT
or INDETERMINATE with the exact evidence scope. An EQUIVALENT result covers the
declared cases and oracle, not arbitrary programs, z/OS or unseen production
data. Static quality and price cannot convert a behavioral failure into a pass.

Retain every candidate, attempt, repair, timeout, cancellation and provider error
in the denominator and evidence manifest. Preserve request/response hashes,
physical-send receipts, model-returned identity, usage, unknown charge holds,
wall time, verdict and diagnostic category. Never retain credentials. Report
both total campaign cost and cost per verified task, including losing arms.
Keep full public evidence in Release assets with small content-addressed
manifests. Sealed evidence stays under its existing custody and disclosure rules.

## Selection and sealed confirmation

1. Preregister the candidate set, paired case IDs, source and catalog hashes,
   budgets, repair limits, ranking and stopping rules before seeing any output.
2. Use only public calibration cases to compare candidates. For a task policy,
   require the existing eligibility thresholds across every required workload,
   zero false acceptances and complete evidence. Do not silently lower the
   current paired-sample floor or confidence/non-inferiority requirements.
3. Lock one calibration winner and its exact configuration in a selection
   receipt before opening the sealed confirmation stage. No holdout data,
   category, score, prompt, seed or candidate result may enter selection.
4. Confirm only the locked winner on disjoint sealed cases. The operator and
   verifier keep holdout answers outside model context and selection memory.
   Require the preregistered holdout pass criterion and zero false acceptances.
5. On holdout failure, incomplete evidence or leakage, stop promotion. Do not
   select the runner-up using the revealed result. A new selection cycle needs
   a new preregistration and fresh sealed cases, with the old failure retained.

The intended precedence is **EQUIVALENT > holdout pass > fewer repairs >
static-quality signals > cost**. This is a two-stage eligibility and ranking
rule, not permission to rank N candidates using their holdout scores. Behavioral
eligibility comes first. Calibration ranking then compares equivalent coverage,
repair count (fewer), the frozen static-quality vector, and total charged plus
reserved cost (lower). A stable preregistered model-ID tie-break ends an exact
tie. Holdout pass is a mandatory promotion condition for the locked winner.
No amount of cheaper generation compensates for holdout failure.

Count repairs across the full attempted calibration population, including arms
that exhaust their allowance. Do not drop difficult cases when ranking repairs
or cost. The first matrix proposes one builder attempt and zero repair attempts,
so repair count is tied at zero there. Later repair comparisons need a separate
budget and fixed repair allowance for every arm.

## Candidate disagreement becomes a legacy test

For public calibration candidates that disagree, capture the smallest permitted
input exposing the disagreement. Candidate agreement is not the oracle. Run
that input against the pinned legacy reference, under a separate execution
admission, and record its actual output or defined error behavior. Check source
licensing, public-data scope, determinism and isolation first. Ambiguous legacy
behavior is INDETERMINATE and needs review, never a fabricated expected answer.

Add each reviewed legacy input/output pair to a versioned regression suite with
the originating candidate hashes and oracle receipt. Deduplicate by canonical
input and preserve failure provenance. Additions affect the next evaluation
cycle, not the frozen current comparison. No generation, legacy execution or
test-suite mutation is performed by this design-only request.

Sealed disagreements remain sealed. They cannot become public prompts, model
memory or current-cycle regression feedback. Any later declassification needs
its own custody decision and replacement holdout set.

## Reconciliation with no model-shopping

The [graph memory and routing spec](verified-graph-memory-and-routing.md)
distinguishes evaluation from operational routing. This bake-off is a separately
budgeted, preregistered evaluation whose complete candidate set exists before
results. It is not an adaptive retry loop that changes models after a bad judge
result, and is not a B05/B06 calibration-campaign router.

Planned operational routing retains the existing Tower `model-routing-policy`
decision, exact matrix/policy hashes, trusted journal head, snapshot identity and
review expiry. Missing, invalid or expired policy means the configured default
only. Fallback remains provider-error-only within one shared budget. Bad business
results remain subject to the fixed repair allowance on the selected model.
Historical campaign builders keep their fixed client/model and cannot use
TaskRouter. This spec does not add bake-off or escalation to qualified runs.

The current `routing_policy.compile_policy` chooses the cheapest eligible model
using its paired confidence rules. It does not implement the new lexicographic
bake-off ranking or winner-lock/holdout protocol. Planned promotion of a future
bake-off result therefore needs a separately reviewed compiler/evidence change
and exact policy decision. Do not feed a hand-written ranking into the existing
gate or claim this document changes its executable semantics.

## Factory integration and admission boundary

Source basis: main `6c496ce3b232443a8ba62be4baaed56e655108e7`.
The existing path is `cli.run --provider configured --model-config ...` ->
`model_config.load_router` -> `ModelAgentSet` -> `FactoryOrchestrator` ->
`TaskRouter.bind_order` -> `AccountedModelProvider`.
The CLI requires factory admission and hardened execution context for nonlocal
providers. The orchestrator binds the order, runtime verifier and model admission
before a model call. Routing rechecks policy on each call, and the accounted
provider checks the concrete provider/role against runtime and model admission.

Planned CLI loader change: use `routing_config.load_router` to validate the
existing policy before leasing any optional provider credentials. The original
`model_config` provider constructors and all bound prompt/context source bytes
remain unchanged; the new loader only selects which configured providers to
construct, without changing prompts or per-call admission. Without a valid
policy, construct only the default. With a valid policy, construct the default
and named primary/fallback providers, not
unused configured providers. Keep per-call expiry and version checks intact.
A policy becoming valid after loading needs an explicit configuration reload,
not automatic acquisition of additional credentials during a run. An expiring
policy falls back to the default only if runtime/model admission permits it.

Configuration loading grants no execution or spend authority. Default-only is
not a bypass of factory approval. This change does not extend the separate
candidate-signing production path, change supported provider identity checks,
or establish native/P5 readiness.

Planned CI regressions cover default-only credential leases, missing default,
valid proof with only named routes, missing proof, policy tampering, model drift,
expiry and refusal of an unbound agent. Existing routing/runtime tests cover
per-call admission, provider-error fallback and shared accounting. Tests remain
synthetic and CI-only, with no live provider requests.

## First matrix and approval boundaries

Planned selection matrix: task `implement`, three models, INTCALC / POSTTRAN /
CREASTMT / ACCTPL1, 35 matched case IDs per workload and model. This is 12 cells,
140 distinct calibration case IDs and **420 model-work-order executions**.
It is not 420 independent paired comparisons, and 35 is not a general proof of
adequate statistical power. Reuse the existing paired analysis and disclose
uncertainty and missing coverage.

Planned confirmation allowance: 35 fresh sealed cases per workload for the one
locked winner, **140 additional executions**, separately gated after selection.
Total prospective maximum: 560 executions, not 420 with hidden holdout costs.
The named workloads identify the routing evaluation set, not completion of the
19-case qualified run. Catalog readiness, snapshot compatibility, exact source,
runtime admission, custody and a complete cost bound are required before a
launch packet can be executable. There is no automatic policy promotion.

Planned later PREVIEW only: after the one-case $10 preview has a verified success
receipt, prepare a separate exact packet for the same public-disposable case,
one builder attempt each from OpenAI, Anthropic and Gemini, and a zero-model
Verdict on all three outputs. Propose a $30 aggregate cap including all attempts,
counting and unknown holds. No repairs, retries, cross-provider fallback or
automatic dispatch. The final packet needs Howard's exact approval and a slot.
It cannot alter the qualified packet, freeze, admissions or select a production
route. Before that success receipt, this remains a conditional design only.

Not approved: the full routing matrix or its spend. Planned repricing must wait
for the one-case $10 preview and the $30 three-provider mini bake-off to supply
observed per-call usage and costs for all three providers. Retain failed attempts
and unknown-charge holds alongside observed charges, rather than treating missing
billing evidence as zero. A new exact matrix packet must reconcile those receipts
with workload-specific input sizes and caps before any spend decision.

Planned full matrix readiness remains on hold behind critical-path chunks. The
20–32 engineering-hour estimate is a decision, not work in progress. Propose it
only as bounded, draft-only, no-spend overnight filler when capacity remains,
with its own explicit task approval. Unused capacity is not dispatch authority.
