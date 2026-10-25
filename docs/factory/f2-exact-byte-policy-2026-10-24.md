# Exact-byte F2 fence policy proposal — 24 October 2026

This policy recognizes one operator-approved source delta in PR #455. [operator-chat record](f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e) It does
not approve a merge, signing, a factory run, spending or any other exception.
Planned: it becomes usable only after its own exact green head is approved and merged
into main. The candidate cannot supply its own exception manifest or validator.

The original `tools/check_java_quality_fence.py` remains byte-identical with
SHA-256 `e520d6a7290a949839c38ae2407c20e67c3bc8fe9ea4a75fc9489737ba063339`.
Its raw failed report is retained. The separate validator reconstructs that
complete report from trusted base objects, checks its exit status, and then
validates every reported violation against the trusted-base approval manifest.
Only the fence requirement may be satisfied by this policy; all other lint,
frozen-judge, selected workflow and strict P5 qualification gates still apply.

## The sole allowed entry

Repository: `howardweale/lightyear-carddemo-modernization`; PR: `455`.

Path: `src/lightyear_factory/budgeted_providers.py`; regular-file mode: `100644`.

- Base preimage: `7207e840edf4292026a909b7f4e992dfe682f9add36b0fff4d552b224015fb7b`.
- Approved final SHA-256: `12d195d37b6d7ed9e7ca8f290e61f8aead641c5ded2d3351db600def5816d928`. [operator-chat record](f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e)
- Approved source change: `81ddd1c77cfa013a88375e4e87609a5bc1ad321e`. [operator-chat record](f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e)
- Base anchor: `3bc468666be34faf69796a6cfece9fe59f9f8939`.

The manifest is
`docs/factory/f2-exact-byte-exceptions-2026-10-24.json`.
There is no orchestrator entry. Adding one requires a separate exact-hash
operator approval and a separately reviewed policy change. The old F2 records
are preserved; their bindings must be recomputed from the exact merged/frozen
main before any request becomes ready.

## Approval provenance and open identity limitation

Approved by Howard in the operator chat, recorded at `2026-10-24T15:23:34-07:00`, exact hash `12d195d37b6d7ed9e7ca8f290e61f8aead641c5ded2d3351db600def5816d928`. [operator-chat record](f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e)
The time is the recorded processing time for this approval, not an independently
authenticated message timestamp. The agent acts through Howard's GitHub account:
a comment or its author cannot authenticate the human decision. This limitation
remains an explicit after-run item. No identity infrastructure is added here.

## Refusal rules

No wildcards, branch-name approvals, automatic expiry or substituted `BASE_SHA`
are permitted. The base anchor must be an ancestor of the checked base, and the
base preimage must still match. The operator-bound source commit must contain exactly
the allowed final bytes. Every judge path, frozen test inventory addition and
POSTTRAN-bound path remains ineligible, even if it overlaps F2 engineering scope.

An extra fenced path, rename, mode change, wrong bytes, changed candidate
manifest/validator/checker/gate/workflow, modified `providers.py`, missing
provenance, wrong repository/PR, stale live head or incomplete checker report
refuses. The live PR must target this repository's main. A synthetic checkout
must have the expected parents and exact merge tree. Post-merge lint accepts the
exception only on the actual normal merge of PR #455, verified against live
GitHub metadata and both parents. API failure refuses rather than bypassing.

CI uses a read-only GitHub token already within the workflow's read permissions.
The new test suite uses temporary synthetic Git repositories and public code
only. It covers the refusal cases and normal PR/synthetic-merge/main-merge paths.
The default lint bootstrap remains the original checker until the trusted base
contains the new validator. No policy files are loaded from the candidate to
authorize an exception.

## Delivery and remaining blockers

This main-based PR must be green and on issue #436 by Sunday 25 October 14:00 PT
for Howard's exact-head approval. A missed gate moves the run to Friday under
the operator's schedule. The policy does not make #455 green by itself.
Orchestrator publication still needs its own approval; recovery and the other
controller drills must pass. Tower implementation is outside this PR. The
first-run human-attestation gap is accepted separately by Howard [operator-chat record](f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e); an interrupted
record still says `interrupted; awaiting human attestation`.

No judge unfreeze, history rewrite, private-store access or ten-minute monitor
is introduced.
