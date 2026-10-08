# PR272–274 implementation and validation status

October 8, 2026 UTC. Operator review; not independent attestation. No model calls and no local Docker runs.

| Area | Implemented and tested | Remaining gate or limitation |
|---|---|---|
| PR272 B06 | Production generation records; full linkage adversaries; actual-runtime producer/worker/controller; bounded nested/folder extraction; broader CI; real saved JUnit pool checks | New modifier mapping approval, immutable runtime snapshot/publication and exact Tower window; native generated-class proof and five-path census remain unqualified |
| PR273 T-SQL | Ordering/dependency refusal, table types/error mapping, native module catalogues, Tower policy admission, 43 named typed procedures, generation/shrinking and versioned finalization | Full seed qualification is not green: ten procedure/variant outcomes remain unresolved. Customer/dynamic SQL readiness is not claimed |
| PR274 graph | Durable expiring revocations, 35-pair routing rule and recompilation, real mining/ranking, recorded outcomes, exact model-response checks, escalation, provider-only leases and branch-independent CI | Independent labels, exact models/prices, per-cell budgets and Tower approval before any evaluation spend |

Validation: 486 tests ran with 15 environment-dependent skips and no failures. The subsequently added finalization test passed in the 111-test T-SQL rerun. The production observer and runtime agents compile on the host JDK. No CI result is claimed before publication.

Native T-SQL evidence: nine coverage-v2 controls passed; the full seed run completed 108 pairs but failed finalization, which remains preserved; 92 generated/shrink pairs completed separately. All 347 available pair archives across the full-run attempts and generated run independently replayed. Read-only checks confirmed absence of each run's owned containers, networks and volumes. These counts are evidence verification, not equivalence or qualification success rates.

See [B06 milestone](b06-provenance-review-milestone.md), [T-SQL milestone](tsql-procedure-m0-milestone.md), [native limitations and hashes](../data-modernization/tsql-procedures/native-review-r2.md), and [graph milestone](factory/graph-memory-milestone.md). Historical failures, B05, work/ms94, template-r1 and J1 predicates remain unchanged. The implementation is published for review in PRs #275 (B06), #276 (graph), and #277 (T-SQL and this milestone). Their live GitHub status is authoritative for merge/CI completion; no new Docker or model authority is implied.

## Publication milestone

- [PR #275](https://github.com/howardweale/lightyear-carddemo-modernization/pull/275): B06 runtime provenance and closure implementation.
- [PR #276](https://github.com/howardweale/lightyear-carddemo-modernization/pull/276): graph routing, revocations, provider admission and evidence.
- [PR #277](https://github.com/howardweale/lightyear-carddemo-modernization/pull/277): typed T-SQL validation, preserved outcomes and this combined milestone.

The expanded Windows B06 CI exposed PowerShell Utility autoload replacing a test hash mock. The test now imports that module before installing its mock and verifies the hash boundary was exercised. All five pinned-transport tests passed locally; production pinned-path and byte checks are unchanged. CI must pass before each PR is merged.
