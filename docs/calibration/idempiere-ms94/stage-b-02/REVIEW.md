# Stage B 02 human review — decisions recorded

On 29 September 2026 Howard Weale explicitly accepted cohort-05 and cohort-06,
and confirmed that completed reversal allocations may have no facts and that all
six candidate-owned assertions justify execution-failure. These are Stage B review
decisions, separate from the earlier Stage A source approvals.
His Category B clarification, “Approve retention rule for next run”, is preserved
in [the review intake](human-review.json). It approves a prospective requirement;
it does not identify an existing frozen clause or retroactively justify the five
rejections. [NEXT-CONTRACT.md](NEXT-CONTRACT.md) records the approved rule.
This is a record of his conversation statement, not a cryptographic signature
by Howard or a claim of independent third-party attestation.

Read [CLASSIFICATION.md](CLASSIFICATION.md) and [classification.json](classification.json).
All evidence paths in the JSON are relative to the preserved local execution root:
`work/ms94/execution-snapshots/stage-b-02` in the development workspace.
The index identifies exact candidate and assembled-source SHA-256 hashes and
native gates. Full native captures have not been republished with this summary.

Classification JSON SHA-256:
`33b2afb200df487f1a58fea93e267561847c7b012e5172e9ddd782973159d2e1`.

## Pass 1 — cohort-05

Open the [local candidate source](../../../../work/ms94/execution-snapshots/stage-b-02/work/ms94/stage-b-02/trials/cohort-05/calls/001-builder/build/model-source.java)
and [local complete native gate](../../../../work/ms94/execution-snapshots/stage-b-02/factory/idempiere/ms86-journeys/runs/journey-d384af497ec7460587f7c45eb2157879/gate.json).
These links require the preserved local workspace; captures are not hosted in Git.
Candidate: `work/ms94/stage-b-02/trials/cohort-05/calls/001-builder/build/model-source.java`.
Assembled source: the adjacent `workspace/LightyearOperationsTest.java`.
Native run: `factory/idempiere/ms86-journeys/runs/journey-d384af497ec7460587f7c45eb2157879`.
Inspect the candidate's complete journey, not just assertions or the passing flag.
The invoice constructor is at assembled line 239; it preserves the order-derived
type and does not add the generic ARI override implicated in category B.

Machine checks: both exits zero; public structure passes; zero unresolved row or
trace differences; both engines witness rollback and lock wait. One builder call,
one compilation, one native attempt; first-try pass, no analyst or repair.
Full archived publication replay passed. The reversal allocation has zero facts,
as permitted by the pinned application; candidate does not abort on that condition.

Human decision: **ACCEPTED by Howard Weale, 29 September 2026**, in response to
this packet. His statement accepts the pass; it does not supply additional
line-by-line findings beyond the evidence and scope presented here.
Candidate SHA-256: `319d30ee48a6aa0d0172d281948cf0ab10a855d096caf9036fb91a388a2f5498`.

## Pass 2 — cohort-06

Open the [local candidate source](../../../../work/ms94/execution-snapshots/stage-b-02/work/ms94/stage-b-02/trials/cohort-06/calls/001-builder/build/model-source.java)
and [local complete native gate](../../../../work/ms94/execution-snapshots/stage-b-02/factory/idempiere/ms86-journeys/runs/journey-9ab263e7087340bba7940e8d5be0814b/gate.json).
Candidate: `work/ms94/stage-b-02/trials/cohort-06/calls/001-builder/build/model-source.java`.
Assembled source: the adjacent `workspace/LightyearOperationsTest.java`.
Native run: `factory/idempiere/ms86-journeys/runs/journey-9ab263e7087340bba7940e8d5be0814b`.
The invoice constructor is at assembled line 357; it likewise preserves the
order-derived type. Independently inspect this candidate; the first pass's review
does not cover it.

Machine checks: both exits zero; public structure passes; zero unresolved row or
trace differences; both engines witness rollback and lock wait. One builder call,
one compilation, one native attempt; first-try pass, no analyst or repair.
Full archived publication replay passed; its posted reversal allocation also has
zero facts. Human decision: **ACCEPTED by Howard Weale, 29 September 2026**, in
response to this packet, without additional line-by-line findings in his statement.
Candidate SHA-256: `20f50344b7e537c0216c3f413471f3c43c942817b787a8ff18e477833cc6b39f`.

## Required scope for each pass

Review model/workflow writes, declared customer/product/order/shipment/invoice
shapes, invoice/payment/allocation posting, credit/reversal links and accounting,
rollback/retry uniqueness and actual lock interleaving. Check that trace values
are observed rather than predicted, support is used without bypass, and no private
answer, prohibited write, hardcoded expected result or unobserved assertion is
substituted for business behavior. Compare the complete gate's accepted-difference
ledger and footprint with the intended public contract. Engine witnesses are
bounded table/session observations, not per-row undo or crash-recovery proof.

## Failure and contract adjudication

Category A: **CONFIRMED by Howard Weale, 29 September 2026**, for pilot-01,
pilot-02 and cohort-01, cohort-02, cohort-04, cohort-08. Legitimate zero-fact
reversal allocations do not invalidate the native posting; the six generated
assertions justify the recorded execution failures.

Category B: **PROSPECTIVE RETENTION RULE APPROVED** for the next run. Pilot-03
and cohort-03, cohort-07, cohort-09, cohort-10 retain their original business-failure
verdicts and public-contract-gap caveat. Howard did not claim that the frozen
public inputs already contained the rule. Contract clarification and matching
acceptance-boundary qualification take precedence over the smoke-run intervention.
No historical failure is relabelled passed or treated as a proven model logic error.

The following was the review scope supplied before Howard's decisions; it is
retained to distinguish the questions asked from the findings he actually supplied.

For category A, confirm that a completed/posted reversal allocation may have no
facts and that the six candidate-owned assertions justify execution-failure.
For category B, decide whether the public contract rules out either eligible ARI
type or mandates deterministic retention of the order-derived invoice type.
If yes, cite the exact builder-visible clause. If not, decide whether the rejection
is an equipment defect or a public-contract gap requiring correction, and state
the intended business rule. Do not infer the rule solely from the reference code.

Review all eleven per-trial rows, not just the category totals. Any disagreement
must identify the trial, evidence and corrected *assessment*; signed outcomes stay
unchanged. Any confirmed wrong judge requires requalification before measurement.

Record reviewer name, review date, the classification JSON's SHA-256, both candidate
hashes, separate pass decisions, each disputed failure decision and the selected
single next intervention. No signature or approval may be generated on a person's
behalf. The decisions above complete the review intake. Integration and qualification
of the approved contract rule remain outstanding before a new 20-trial measurement.
