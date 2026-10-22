# INTCALC release plan — 22 October 2026

**Document for Howard's review only. No run, model spend, signing or release is
authorized.** The current retained verdict remains **not releasable**. This plan
is additive and preserves the original measurements and decisions.
[Retained verdict](intcalc-releasability-2026-10-21.md) ·
[source bindings](intcalc-release-source-bindings-2026-10-22.json) ·
[Howard's planning inputs](intcalc-release-planning-inputs-2026-10-22.json).

## Qualified oracle and the mandatory z/OS gate

For this release, a qualified oracle means the pinned GnuCOBOL twin and the
Python reference, checked against each other and confirmed **record by record
against a matched-source z/OS capture**. The public twin alone remains an
engineering answer key. Existing limitations include indexed-file/VSAM behavior,
collation, runtime status and abnormal termination; approval cannot erase those
limitations. [Oracle memo](twin-oracle-decision-memo.md) ·
[twin limits](twin-limits.md) ·
[Python reference](../../src/carddemo_oracle/oracle.py).

Howard's 22 October instruction reports that Maintec's 21 October delivery was
job logs only. No delivery contents were accessed in preparing this plan. Logs
alone do not meet the newly required release gate. A qualifying delivery must
provide before and after record images for every in-scope dataset, including
created/deleted records and exact keys, together with matched source/copybook
identities, processing date/parameters, runtime/compiler and encoding information,
job/dataset provenance, record counts, return/file statuses and integrity hashes.
The independent comparison must report every record/field/status difference,
not only totals, sample rows or a successful job return code. Missing datasets,
empty or ambiguous captures and unexplained differences block qualification.
[Gate and delivery-status source](intcalc-release-planning-inputs-2026-10-22.json).

The authorized operator handles native material privately. This plan does not
authorize Codex to inspect Maintec contents or `work/mainframe/arrivals/`, nor
to publish native record images. A separately reviewed typed verifier and
permitted digest/summary receipt must bind the comparison. The existing release
consumer supports twin scope and refuses native-facing claims; therefore a
matched capture alone cannot silently expand its supported claim scope.
[Current gate definition](release-grade-evidence-2026-10-18.md) ·
[current implementation](../../src/lightyear_factory/release_grade.py).

## Release run class and exact main snapshot

Development runs may explore fixtures, diagnose faults and produce provisional
engineering evidence. The release campaign must instead be prospectively
designated `run_class: release` in the trusted judge's signed verdict, with
`oracle_status: qualified`, exact scenario/source/threshold bindings, externally
designated production review trust and `fixture_only: false` plus
`disposable_ci_signatures_only: false`. Existing engineering verdicts must not
be relabelled or supplemented with an unsigned assertion of release status.
[Release-grade checklist](release-grade-evidence-2026-10-18.md).

The planning source snapshot is protected main
`577a777fd68ecceacc5c9b54be7ae2c0bb74fd5e`. It is **not a measured release
campaign** and is not approved in advance as the future run's head. Immediately
before any separately authorized campaign, bind its actual immutable main SHA,
workflow YAML and tool/compiler/runtime/source hashes. Retain the complete
paginated inventory of applicable main-push workflows, child jobs and applicable
steps on that exact head; a lone green `required-ci` result is insufficient.
Bind this snapshot and the durable retention manifest/verification receipt into
the judge-reviewed verdict. [Snapshot evidence](intcalc-release-source-bindings-2026-10-22.json) ·
[campaign validator](../../src/lightyear_factory/release_grade.py).

**Unresolved policy mismatch:** the existing release-grade consumer requires
`protection.strict=true`; the current approved branch policy is `strict=false`.
This plan preserves the current policy and the consumer. Howard must choose a
separately reviewed resolution before a release campaign can satisfy that gate.
Do not change protection or weaken the validator as part of this document PR.
[Observed policy](intcalc-release-source-bindings-2026-10-22.json).

## Production review and the real kill-count gap

The retained raw result is **311/424 = 73.35%**. Howard's release floor is **at
least 90% of all injected faults killed**; a conditional projection, accepted
equivalence argument, timeout, uncovered mutant or error never becomes a kill.
With the same 424-fault denominator, at least **382 actual kills** are needed:
**71 additional kills** beyond 311. If the reviewed fault inventory changes,
recompute the requirement as `ceil(0.90 × all injected faults)` and report the
new denominator explicitly. No survivor may disappear through reclassification.
[Raw result](intcalc-releasability-2026-10-21.md) ·
[release floor](intcalc-release-planning-inputs-2026-10-22.json).

Closing the gap requires source-behavior-derived scenarios or implementation
repairs, each reviewed independently and tied to the exercised COBOL lines.
Do not tune cases to a threshold or adjust expected answers to match the
candidate. Complete original/candidate comparisons and all actual injected
fault outcomes must survive into the retained evidence. A later successful
mutation result still needs the matched z/OS gate and every release-grade gate.
[Retained evidence provenance](intcalc-releasability-2026-10-21.json) ·
[fixture rule](intcalc-release-planning-inputs-2026-10-22.json).

Production review must verify exact contracts, evidence hashes, ordered
predecessor decisions, typed conditions, the externally designated public review
key and independently trusted current journal head. Disposable CI signatures
test refusal behavior only. The six existing INTCALC requests are unsigned;
request 06 still refuses until its real conditions are satisfied. The historical
seven-record Factory acceptance is not an approval of these requests or this
release. [Selected APPL-RESULT contract](appl-result-contract-selection-2026-10-18.json) ·
[ordered packet and blockers](intcalc-signing-order-2026-10-17.json) ·
[production trust requirement](release-grade-evidence-2026-10-18.md).

## Cost and time proposal

These are planning allowances, **not measured durations or approved budgets**.
They exclude the engineering work needed to find 71 further kills and the
external wait for a qualified Maintec capture. Those durations are currently
unknown. The retained verdict publication was a verification/retention step,
not a timing benchmark for a new release campaign.
[Estimate assumptions](intcalc-release-planning-inputs-2026-10-22.json).

| Resource | Proposed initial allowance | Boundary |
|---|---|---|
| Model spend | USD 0 | Deterministic verification only; any model-assisted work requires a separate estimate and approval. The COPAU USD10 cap does not transfer. |
| CI execution | 4 runner-hours total | Planning assumption: up to two clean verification campaigns at two runner-hours each. Sum all concurrent jobs, not just elapsed wall time. Stop at the approved allowance; no automatic retries. |
| Howard's review | 2–3 hours | Approximately 60–90 minutes for evidence/gates, 45–60 for the six-request review and 15–30 for final binding review; additional findings require a revised estimate. |
| External native delivery and gap closure | Unestimated | No completion-date promise before the required capture and source-derived fixes are available. |

CI dollar cost is not priced here: runner type, included minutes and account
billing must be confirmed before approval. Howard should approve a concrete
runner/cost cap and one campaign first, then review measured usage before any
second campaign. No spending or campaign is launched by accepting this plan.
[Estimate assumptions and approvals still required](intcalc-release-planning-inputs-2026-10-22.json).

## Stop conditions and partial results

Stop on any changed head or binding, unsafe/private-material boundary, missing
or mismatched signature/current head, incomplete applicable-job inventory,
failed/cancelled/skipped mandatory validation, oracle disagreement, native
record mismatch, insufficient kill count, unqualified oracle, unsupported
claim scope, policy mismatch, absent predecessor/typed condition, or cost/time
cap. Keep the original evidence and every produced partial artifact with its
head/run/attempt/hash and explicit failed or incomplete status. Never reuse a
partial result as a release pass; a restart needs reviewed inputs and remaining
budget authorization. [Release checks](release-grade-evidence-2026-10-18.md) ·
[ordered-request constraints](intcalc-signing-order-2026-10-17.json).

## Questions for Howard before any release spend

1. Who owns the private record-level z/OS delivery and the separately reviewed
   verifier, and what approved public summary may establish the match?
2. Which production review public key and independent current journal head will
   be designated for this campaign?
3. How should the `strict=true` release-consumer requirement be reconciled with
   the approved `strict=false` branch policy?
4. Are the proposed zero-model, four-runner-hour and 2–3-hour review allowances
   suitable, and what runner billing/cost cap applies?
5. Which exact green protected-main snapshot and campaign definition should be
   approved after the source-derived kill gap and native gate are closed?

The 90% floor, no conditional kill credit, and mandatory record-level z/OS match
are already decided; these questions do not reopen them.
