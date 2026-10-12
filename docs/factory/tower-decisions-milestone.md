# Factory signed decision migration

The unsigned backfill is ready for Howard: `tower-backfill-request-2026-10-12.json`
binds both dated decision documents completely at commit
eb5987517266fe71d9e565533a57d1f3583f102c. Its SHA-256 is
fb2c60065fbb9792bfe7765409fcb3e9097cd1a61fd46f785832088873f18e0e.
No signature, live authority, service, grant, native run or model call was made.

Factory has seven operational decision kinds and one explicit backfill kind.
Contracts bind public Git bytes, scopes, reviewer roles, plans and engineering
caps; per-record review is mandatory. Later keep-to-fix decisions invalidate
dependent equivalence reviews. MCP drafts remain propose-only. Existing intake
and B06 registries remain unchanged.

The operator-controlled activation setting fails closed after signed backfill.
Scenario release, POSTTRAN budget and human review consume signed proofs at an
externally supplied journal head. The shared verifier covers future B07 spend,
legacy register resolution and engineering approval without dispatch. Conditional
thresholds remain pending until an explicitly effective approval. Historical
files and the old frozen POSTTRAN plan remain unchanged. The new dedicated
transport bytes require a separately approved amended pin before use.

Validation: 53 focused Tower, isolation, HTTP, scenario, POSTTRAN and business-rule
tests passed; 15 offline mocked transport tests passed. Tests cover all eight
kinds, wrong role, tamper, stale head, foreign scope, changed plan, incomplete
review, dependency invalidation, backfill byte equality and activation refusal.
Final-head GitHub CI is tracked separately; these local checks do not assert it.

Manual differences from the supplied draft: an explicit eighth backfill kind;
all three approving roles for backfill; unsigned migration remains inactive;
conditional policy text is not automatically evaluated; no deployment implied.
Programs and Business rules are the next stacked delivery; Status and Unresolved
and the regenerated Word edition follow it. No threshold, Phase 2 or release
approval follows from this implementation.
