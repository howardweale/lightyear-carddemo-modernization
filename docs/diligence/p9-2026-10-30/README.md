# P9 public technical diligence pack

Backlog lane — draft for Howard's review, 30 October 2026.

This pack is a reading and proof index for public repository material. It is not
a customer acceptance report, a current-service health check or a run approval.
No investor deck is a source. No result from the proposed 5 November COPAU run
is filled in here. All backlog PRs remain draft and unmerged until that run ends.

## Start here

1. Read the [scope and proof map](#scope-and-proof-map).
2. Match the exact source bytes against the [source index](source-index.md).
3. Follow the underlying records and their own source/artifact links before
   evaluating a result. A link to code or a test is not a measurement.
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
| Current whole-repository test/CI status | Not yet: historical entries do not establish a fresh all-platform pass. No new full Windows workload is requested by this documentation draft. |
| Independent security/compliance assurance | Not yet: no external audit, penetration-test report or certification is supplied. |
| Customer-scale generality and production fitness | Not yet: public fixture and twin results do not establish these properties. |
| Source repository visibility transition | Planned: Howard's separate post-run decision and access/disclosure review. No settings change accompanies this pack. |
| Final customer wording | Draft register and trust-page wording await Howard's review. |

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
