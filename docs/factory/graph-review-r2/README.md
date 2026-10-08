# Graph memory, search and routing: review revision 2

October 7, 2026. Operator review; not independent attestation.

This increment implements the code changes requested by the review of PRs 264
and 267. It does not start the proposed evaluations or activate a routing policy.
The default remains keyword plus graph-proximity search and the routing policy
still has no promoted routes. No live provider call or embedding inference ran.

| Review issue | Implemented change |
| --- | --- |
| Hashed vectors and query-specific vocabulary | Removed; optional local ONNX adapter verifies model/tokenizer hashes before loading. Literal nodes are excluded; explicit source-comment abbreviations replace the hand-written list. |
| Weak search acceptance | Held-out evaluator measures recall@5 and MRR; 75-query full-graph labelling pack prepared for a reviewer who did not tune search. No measured semantic improvement yet. |
| Stale flagged guidance | Signed, projection-bound revocation channel checked on every read. Pending heads make interrupted publication fail closed. |
| Customer outcomes | `customer-factory` admitted only with the same signed judge/replay/customer/context checks; sealed holdouts refused. |
| Slow flagging | At least two failures and at least 40% failure rate. |
| Missing descendant pitfalls | Descendant pitfalls ranked by graph distance within the existing 4 KB guidance cap. |
| First-attempt undercount | Any non-false-accept `passed` result on attempt 1 counts, for both task types; attempts must match its receipt. |
| Small routing samples | Ten distinct paired runs per cell minimum, Wilson 95% intervals, exact model versions and expiry on version change. |
| Search cost | Precomputed term sets and top-K selection before explanation construction; maximum 1,000 results. |
| Hardened provider credentials | Work-order-scoped secret broker leases; no environment fallback after a denied lease. |

The policy compiler proposes the cheapest single model whose Wilson lower bound
is at least the best observed pass rate minus a predeclared margin on every
workload, with zero false accepts. No qualifying model means no route. The Tower
card carries the rule, cell-level decision output and model versions. In
particular, 10/10 does **not** satisfy a 90% lower-bound criterion: the floor is a
minimum sample, not sufficient evidence by itself.

The escalation implementation is a separate declared evaluation arm: cheap
first, strong only for subsequent builder invocations carrying a closed
diagnostic. It shares the judge's original attempt and model budgets, never
initiates a retry, records failed calls and has no automatic provider fallback.
Matrix replay verifies the declared model and attempt sequence. Its results
cannot be promoted by the single-model compiler as if they described one model.
Production ladder activation remains a separate reviewed policy change after
measurement; this increment supplies the evaluation arm only.

## Prepared review material

- [16 inferred seed proposals](memory-seed-proposals.json), four per public
  factory workload, bound to real repair categories and graph anchors. They are
  unsubmitted drafts, not Tower decisions or successful run evidence. No campaign
  artifacts were used and no missing historical decisions were invented.
- [Local embedding asset manifest](local-embedding-manifest.json): public
  `sentence-transformers/all-MiniLM-L6-v2` at revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Model and tokenizer bytes are retained
  locally, excluded from Git. No model inference ran. The implementation follows
  the publisher's attention-mask mean pooling and normalization contract.
- [Search plan](search-plan.json) and [blank label pack](search-label-pack.json)
  bind all 11,336 nodes and 13,491 edges of the repository graph. An external
  reviewer must supply 75 queries/relevant-node labels and freeze their hashes
  before evaluation. Promotion requires at least 0.05 absolute recall@5 gain
  and no MRR loss. This is a prospective rule, not a measured result.
- [Matrix and memory A/B drafts](evaluation-plans.json): proposed caps of $100
  for 240 matrix trials (two models plus a separately measured ladder, two task
  types, four workloads, ten paired cases per cell) and $50 for 80 memory A/B
  trials. Neither budget is approved. Exact provider versions/prices, catalogues,
  per-cell limits, source commit and Howard's Tower decision are required first.
  Existing repair cases are not relabelled as implementation tasks.

Before seeding an authority ledger, obtain leak certificates against the correct
inventory and exact Tower decisions. Five independently replayed passes are
still required before proposing `verified` trust; observed correlations never
establish causation. No model matrix, memory A/B or customer-data run is authorized
by these files. Live provider compatibility and savings remain unmeasured.

## Deployment and validation limits

Follow the updated [operator guide](../graph-memory.md) to subscribe a projection
to the authority's live revocation channel. Deploy the authority writer and
reader together. Existing annotated projections without a channel now fail
closed; rebuild and reapprove them. Protect channel files and subscription
registry from agent writes. A signature does not protect against a host
administrator rolling back both head and list. The ordinary unannotated context
schema remains byte-compatible with the historical implementation.

Validation uses synthetic providers, a synthetic ONNX session/tokenizer and
disposable signing authorities. It checks masked pooling and hash refusal,
signature/projection/sequence failures, interrupted publication, retirement,
early flagging, customer/holdout isolation, task-independent first-attempt counts,
Wilson/pairing eligibility, version expiry, secret-lease refusal and ladder
budgets/replay. These are software tests, not independent attestation or native
model qualification. No B05, frozen B06 evidence, template-r1, J1 predicates or
`work/ms94` was changed.

Local regression results: 61 graph-memory/review tests, 77 T-SQL tests,
37 launcher/factory tests, 53 Verify tests and 51 Tower tests completed
successfully (279 total; 16 environment/platform skips). The synthetic pooling
test ran using the existing NumPy-enabled Python; no ONNX session loaded a real
model. Remote CI and live provider compatibility have not been evaluated for
this revision. The T-SQL VM qualification is reported separately from these
offline software tests.
