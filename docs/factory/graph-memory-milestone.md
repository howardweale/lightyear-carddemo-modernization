# Verified graph memory, search and routing

Implemented on 2026-10-06 from main `990369c1`, on
`codex/verify-graph-memory`. Operator review; not independent attestation.
Zero Docker and zero model calls. No live authority roles or routing policies
were granted. Publication and merge were requested by Howard on 2026-10-06.
The delivery PR records the reviewed source commit, CI checks and merge status.

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
