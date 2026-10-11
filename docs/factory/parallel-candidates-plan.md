# Parallel candidates: plan for Howard

Priority 4, after the three preceding workstreams. Design only. Before coding,
Howard reviews the scheduler, aggregate budget and selection policy below.

Create independent candidate workspaces from identical pinned public inputs.
Each candidate has a unique attempt identity, input boundary and append-only
usage ledger. A parent ledger reserves aggregate tokens, dollars, compilation
slots and time before dispatch; per-candidate limits do not multiply the approved
budget. Failed and cancelled attempts keep their full actual usage and evidence.

Pre-register candidate allocation and comparison rules. Builders cannot inspect
other candidates, twin outputs or judge results beyond their approved feedback.
Do not select a winner from an incomplete or selectively reported cohort. Publish
all attempted candidates, refusals, disagreements, usage and selection rationale.

First prove scheduler concurrency, double-reservation refusal, cancellation,
timeout and isolation with fake transports and deterministic public fixtures.
Then request the exact model/call/token/dollar budget for a bounded experiment.
No model calls, customer data or native run are authorized by this design note.
