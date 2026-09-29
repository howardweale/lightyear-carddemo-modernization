# Stage B 02 human review packet — pending

Howard Weale agreed on 29 September 2026 to review this packet. His assessment of
**each** passing candidate and all eleven failure classifications remains pending.
Agreement to review is not approval; no reviewer has signed this packet yet.
Stage A source approvals do not approve these generated candidates.

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

Human decision: **PENDING**. Record accept/reject, concrete source/native evidence,
any missing or forbidden behavior, and whether the gate's acceptance is justified.
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
zero facts. Human decision: **PENDING**, with the same explicit evidence requirements.
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
behalf. This review must complete before the next 20-trial measurement is frozen.
