# Verified graph memory, search and routing

Implemented on 2026-10-06 from main `990369c1`, on
`codex/verify-graph-memory`. Operator review; not independent attestation.
Zero Docker and zero model calls. No live authority roles or routing policies
were granted. Publication and merge were requested by Howard on 2026-10-06.
[Delivery PR #264](https://github.com/howardweale/lightyear-carddemo-modernization/pull/264)
records the reviewed source commit, CI checks and merge status.

## Delivered

| Area | Result |
| --- | --- |
| Memory | Signed, content-addressed annotation events with chain replay; proposals, Tower approval, retirement and supersession; customer isolation and reviewed portable publication |
| Governor | Five independently replayed passing outcomes establish eligibility; only Tower can promote; conflicting outcomes and expiry exclude retrieval; attribution is correlation |
| Sources | Operator CLI, verified Tower decision imports, generic closed-category repair proposals, factory-only inferred proposals and commit/line-bound GitHub review import |
| Context | Opt-in schema 1.1 with approved projection and 4 KB annotation cap; exact schema 1.0 regression; sixth read-only Verify tool `graph_guidance` |
| Search | Projection-only deterministic BM25, local feature-hash vectors and graph-distance ranking; lexical default retained; external confidential embeddings refused |
| Providers | Configured Anthropic/Gemini adapters with offline HTTP fixtures, shared limits and failed-call evidence |
| Evaluation/routing | Commit-specific Tower matrix approval, clean-source and complete-cell admission, run/call/catalog bindings, measured run wall time; reviewed expiring routing, provider-error-only fallback |
| Tower | Annotation health, safe text/anchor review, bulk signed decisions, routing and search status cards |
| Parallel seam | Queue interface and in-memory lease/fencing/conflict tests; durable design note, no production runner |

The implementation retains the existing projection leak-check and approval
boundary. Search indexes and annotations are inside the projection's bound
bytes. Inferred annotations never enter the search index or Verify guidance.
The no-values z/OS workspace does not expose the knowledge status route.

## Verification

- Focused feature suite: 34 tests passed.
- Verify, Tower and factory regression suite: 240 tests completed successfully;
  18 skipped by environment/platform guards. The focused suite was rerun after
  the final governor and configuration checks were added.
- Chromium browser acceptance passed, with no external requests.
- Protected-path guard, CLI help, JavaScript syntax and `git diff --check` passed.
- The existing Explorer SSE teardown emitted a background connection/database
  closure trace after its temporary fixture closed; the suite reported no
  failures. No Explorer implementation was changed.
- Initial full Ubuntu CI found that the historical MS70 triage artifacts bind
  `providers.py`. The original provider file was restored byte-for-byte and
  new failed-call accounting moved to the opt-in `AccountedModelProvider`
  subclass. Historical calibration artifacts were not regenerated or changed.

Offline verification includes synthetic signed Tower decisions and judge
attestations, tamper/chain/freshness/role boundaries, leak refusal, outcome
attribution, expiry/customer isolation, provider budgets/fallback evidence,
matrix admission and aggregation, queue fencing, and context compatibility.
The public CardDemo query “monthly interest on account balance” returns the
CBACT04C interest paragraph within the first three hybrid results.

The browser acceptance test uses a disposable synthetic authority and loopback
server. It checks health, leak-checked proposal text, graph links and a bulk
signed decision, and rejects any external browser request.

The protected-path check includes tracked and untracked changes. B05/B06,
`template-r1`, `work/ms94`, campaign builder tools and J1 remain unchanged.

## Limits and deployment

The local vector implementation is a transparent feature-hash baseline, not a
pretrained model. Live provider compatibility and routing effectiveness remain
unmeasured. Matrix execution still requires Howard's exact commit, models and
dollar-budget decision. The configured-provider CLI refuses the existing
hardened executor until a dedicated secret-store adapter exists.

Annotation projection snapshots are immutable. Subsequent flags/expiry require
revocation or rebuilding/reapproving the projection; current-date expiry is
also checked on retrieval. Host-owned trust configuration, separate keys,
protected-value inventories and an explicit Howard knowledge-approver grant
are deployment steps. No customer ledger or key is committed.

See the [operator guide](graph-memory.md), [source specification](specs/verified-graph-memory-and-routing.md)
and [parallel queue design](specs/parallel-work-queue.md).


## October 7 review follow-up

The implementation state above is historical. See [review revision 2](graph-review-r2/README.md)
for the live signed revocation channel, earlier flagging, customer-factory
outcomes, descendant pitfalls, first-attempt correction, sample floor/version
expiry, local hash-pinned ONNX adapter, scoped secret leases, policy compiler and
separately declared escalation arm. The default is keyword plus graph proximity.
No live matrix, memory A/B or semantic benchmark has run; no effectiveness or
model-arbitrage claim has been established.


## PR274 completion increment — October 8 UTC

Live revocation heads now expire after at most 15 minutes. A durable host-owned SQLite watermark outside the projection detects rollback across fresh readers; a missing subscription registry blocks retirement propagation instead of silently losing it. Host ACLs and the real host clock remain part of this boundary.

Routing admission recompiles the exact approved matrix policy. The sample floor is 35 paired cases per cell, including correct no-change first attempts. Only eligible models can become the primary or provider-error fallback. Dated model snapshot IDs and provider response identities are required before matrix execution. The separately declared cheap-first/strong-repair arm runs through the matrix controller. The provider-only OpenAI/Anthropic/Gemini credential scope was explicitly approved by Howard; builder and verifier roles gain no leases.

CardDemo mining now uses public identifiers and removes the 82 misparsed metadata headings. The recorded 31 abbreviation hypotheses are lexical proposals, not validated synonyms or retrieval-quality evidence. The benchmark computes actual local search rankings and requires a Tower-bound label owner independent of the search tuner. Customer outcomes have an executable INTCALC Verify replay producer with separate executor/judge bindings; unsupported judge families remain refused.

Graph CI now runs for relevant changes on all PR branches and main. No model evaluation, memory A/B, policy promotion or semantic benchmark was launched. The 840-trial draft has no approved cost: the previous USD100 cap cannot be reused, and the USD350 linear placeholder is not a quote. Exact model snapshots/prices, per-cell limits, independent labels and a new Tower budget decision are still required.

Publication CI caught a historical MS70 source-hash coupling. The base provider bytes remain unchanged; prospective graph runs now use a separate response-verifying adapter. Matching response snapshots pass, and missing/mismatched raw response identities fail. The historical triage artifacts were not regenerated.
