# P9 public technical diligence pack

Backlog lane - draft for Howard's review, 30 October 2026.

## What is proven, with receipts

These are public, dated observations available on 30 October; each receipt link
contains its full SHA-256, with a short hash shown for reading.

- POSTTRAN matched the COBOL twin in **29 of 29 scenarios**, while separate fault evidence identifies the unresolved defect where a transaction can be saved after its account update fails: [comparison receipt / SHA-256 b15b224b768a](receipts/posttran-comparison.json#sha256=b15b224b768acc754b1496c35d7ca4529c52e8b78c381e57140f76b574552923) and [fault record / SHA-256 f2f8a3fa162b](../../../docs/factory/fault-posttran-review311.json#sha256=f2f8a3fa162b1602767a514c77d0d3b34a36e4562b7981d7eaf00333cf71ffbc).
- INTCALC's retained assessment caught **311 of 424 deliberate defects**, leaves **113 evidence gaps**, and says **not releasable**: [evidence index / SHA-256 9ca919221377](receipts/evidence-index.json#sha256=9ca9192213779d17f2d03c5e74f0cbc95afd3e757f881f5d398405cae2add14d).
- The six-screen proof caught **701 of 768 deliberate defects (91.28%)** and matched **678 of 678 screen interactions** across 120 cases: [screen receipt / SHA-256 958741da798d](../../../docs/modernization/carddemo-slice-1-2026-10-18.json#sha256=958741da798d0e30e1527afbd88236f3a999dc6fe5952f00e925092f1ce09cc4).
- The corrected equivalence scorecard records **8 of 227 unresolved cases resolved**, with the original denominator intact: [scorecard / SHA-256 e097d978f5e5](../../../docs/factory/equivalence-scorecard-2026-10-22.json#sha256=e097d978f5e5035f4113b970b3f8e40d7a1469ab901003c3ab7135c5b81a2140).
- Main's CI completed the **4,238-test suite on Windows (105 skipped) and Linux (96 skipped)**: [CI receipt / SHA-256 ecea7e0f9691](receipts/main-ci.json#sha256=ecea7e0f96919f196eeea3a3b8cd5b06d7eee92542b0b949372c78ab057402c3).
- Discovery covers CardDemo (**55 COBOL programs; 11,336 graph nodes and 13,491 relationships**), iDempiere (**4,520 Java source units and 36,819 dependency links**) and CloudBank (**70 Java source units across 10 modules**) at separate pinned scopes: [evidence index / SHA-256 9ca919221377](receipts/evidence-index.json#sha256=9ca9192213779d17f2d03c5e74f0cbc95afd3e757f881f5d398405cae2add14d).
- POSTTRAN's human-signed approval was checked end to end in CI before its single permitted comparison: [decision receipt / SHA-256 60f421e30a6f](receipts/posttran-human-decision.json#sha256=60f421e30a6f98d99ba99d6ae44a3a65d36a349520a2d4a13083e85dd46d961e).

## Limits that travel with these results

The POSTTRAN answer key is a provisional COBOL twin, with no z/OS confirmation
or release authority; the 29 scenarios do not demonstrate the rewrite-failure
path, and KF-005 remains open. Its separate fault/source evidence does not close
the account-rewrite/transaction consistency question.

INTCALC's 424-mutant campaign and the 768-mutant screen proof have different
scopes. The screen total includes 49 survivors, 17 with no coverage and one
timeout, none counted as caught. The scorecard's 185-of-227 projection depends
on pending signatures and is not the completed count. Compiler identities and
held-out TRANREPT observations add no executable campaign-resolution credit.

The suite counts describe the exact main snapshot in the receipt, not this
documentation branch or a later head. Discovery is structural: CardDemo's graph,
iDempiere's dependency inventory and CloudBank's source inventory are separate,
with runtime behavior and target equivalence outside those inventory claims.
The human decision proof covers one historical operator-review path and bears
a service countersignature of authenticated operator intent, not independent
third-party assurance or blanket factory qualification.

This pack is a reading and proof index for public repository material. It is not
a customer acceptance report, a current-service health check or a run approval.
No investor deck is a source. No result from the proposed 5 November COPAU run
is filled in here. All backlog PRs remain draft and unmerged until that run ends.

## Start here

1. Read the evidence above, then the [scope and proof map](#scope-and-proof-map).
2. Match the exact source bytes against the [source index](source-index.md).
3. Follow the original records and artifact links before evaluating a result.
4. Use the [review worksheet](review-checklist.md) to record gaps and questions.

## Scope and proof map

| Topic | Public source or proof entry | Interpretation and limit |
| --- | --- | --- |
| Product boundary | [Repository orientation](../../../README.md), [architecture](../../../ARCHITECTURE.md) | Package responsibilities and target layering. The architecture explicitly retains incomplete boundary enforcement. |
| Comparator and evidence model | [Verify operator guide](../../verify/README.md), [implementation acceptance record](../../verify/acceptance.md) | Historical implementation documentation and its original public-fixture scope. No native customer equivalence follows from these records. |
| Historical worker packaging | [F8 receipt](../../factory/copau-f8-release-receipt-2026-10-21.json), [source CI result](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/39536105114), [retained public assets](https://github.com/howardweale/lightyear-carddemo-modernization/releases/tag/f8-worker-run39536105114-attempt1) | Packaging and isolation evidence for the declared public fixture. No configured factory-run qualification or present-day whole-repository CI inference. |
| Historical test results | [Verify acceptance](../../verify/acceptance.md), [T-SQL review results](../../../data-modernization/tsql-procedures/review-results.md) | Follow each record's original result/capture/replay links and denominator. Counts and platforms from different runs must stay separate. |
| Equivalence accounting | [Corrected scorecard](../../factory/equivalence-scorecard-2026-10-22.json), [correction rationale](../../factory/equivalence-scorecard-2026-10-22.md) | Compiler identities, argued equivalence and executable campaign kills are different quantities. The TRANREPT correction gives no held-out generality credit. |
| Security posture | [Verify trust and leakage bounds](../../verify/README.md#leakage-bound), [architecture boundaries](../../../ARCHITECTURE.md#data-and-trust-flow) | Local OS and result-channel limits, protected operator inputs and explicit exclusions. No independent security audit, certification or universal leak-resistance claim. |
| Point-in-time operator installation record | [Public installation record](../../factory/first-install-accepted-2026-10-23.json) | The record has an installation-only scope. It cannot establish current service state, another signature, a later journal head or run authority. |
| Retention and replay | [Public retention design](../../engineering/proof-retention.md), [F8 raw workspace map](../../factory/copau-f8-workspace-manifest-2026-10-21.json) | Inspect actual release bytes, per-file bindings and retention availability for the relevant evidence. A design description alone is not a fresh availability check. |
| Third-party provenance | [License scope](../../../LICENSES/README.md), [notices](../../../THIRD_PARTY_NOTICES.md) | Third-party notices do not grant a licence to original LIGHTYEAR source. Customer redistribution and commercial terms need separate review. |
| Customer-facing wording | [Authoritative eight-row wording draft](https://github.com/howardweale/lightyear-carddemo-modernization/issues/436#issuecomment-6502384245), [P3 evidence policy](../../platform/p3-operational-claims.md#sha256=57ad661029a58c3205bd3dd29f748f357b2f6835014464e0be0d9ee1885d2aa3) | The wording draft is the source for the separate Thursday 5 November register. Every outcome, receipt, digest and observed-status slot stays blank pending that run's original receipts. |

The source index binds the exact Git-object bytes inspected for this draft.
Relative links are convenient reading paths and may later show different bytes.
Compare the hashes before relying on a source. The PR's base identifies the
inspection snapshot; later changes need a new review rather than a silent update.

## Claims discipline

Planned: use the eight-row Thursday 5 November register for the run report.
Preserve the wording draft's individual case, configured-route, accounting,
isolation, worker-control, evaluation and strict-qualification boundaries.
The historical P3 inventory is hygiene only, not a curated claims register.

Planned: each eventual factual operational sentence needs the P3 clause-local
public JSON receipt link, exact byte SHA-256 and matching evidence category.
Record supported, contradicted, unresolved or not-applicable findings with reasons.
Keep failures, skips, indeterminate outcomes and missing observations visible.
Do not replace an original receipt with a rewritten summary or a new wrapper
and infer independent verification from the wrapper alone.

## Evidence gaps for this review

| Gap | Disposition |
| --- | --- |
| 5 November run results and exact package | Not yet: all result rows remain unfilled. The critical-path owner supplies the eventual original evidence. |
| Configured-route and per-case qualification | Not yet: this pack supplies no new execution or acceptance evidence. |
| Later-head test/CI status | The opening receipt binds the inspected main snapshot only. Planned: full CI before merge after the run, with no new workload for this draft. |
| Independent security/compliance assurance | Not yet: no external audit, penetration-test report or certification is supplied. |
| Customer-scale generality and production fitness | Not yet: public fixture and twin results do not establish these properties. |
| Source repository visibility transition | Hybrid: this repository stays public. Option A full transition is deferred until after the seed round; a small private engagement repository is proposed, with customer data excluded from both repositories. Names, plan and window remain Howard's decision in [#464](https://github.com/howardweale/lightyear-carddemo-modernization/pull/464). No settings change accompanies this pack. |
| Final customer wording | The Thursday register wording has Howard's approval in [#473](https://github.com/howardweale/lightyear-carddemo-modernization/pull/473). Every run outcome and receipt slot stays UNFILLED. |

## Investor materials (provided privately)

Placeholder for Howard outside this repository. No investor slides, raise,
financial charts, valuation, revenue/runway plan, use-of-funds figures or partner
commercial-status assertions belong in this pack. This placeholder contains no
commercial claim and grants no permission to copy private materials into Git.

## Review disposition

Draft only. Reading and static byte/link inspection are the preparation method.
No model call, workload, test suite, signing, operator action or source change is
part of this pack. Review readiness is separate from CI, merge and disclosure
decisions. Keep the critical-path lane's code, gates and run package untouched.
