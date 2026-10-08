# Graph review r3 — prospective routing and live revocation repair

Operator review, not independent attestation. Zero model calls. No evaluation or routing promotion is authorized by this implementation.

## Routing

Howard selected a Wilson 95% lower bound of at least **80% on every workload**. The compiler additionally requires an actual paired binary outcome map, a Newcombe paired-Wilson difference interval whose lower bound is no less than the approved negative margin against every peer, 35 or more matched runs, zero false acceptance and measured finite cost. Marginal totals cannot reconstruct pairs. Two 3/35 models get no route; tied 34/35 models can qualify. Admission recomputes the exact policy, including its floor, from the approved matrix.

`evaluation-plans.json` separates 560 single-model trials from 280 escalation trials. Both remain drafts, without provider prices or model-call approval. Escalation cells cannot enter the single-model policy compiler. The paired interval uses the actual discordant pairs; identical constant outcome vectors use the limiting correlation of one. It is a per-comparison interval, not a simultaneous family-wise guarantee.

Mined abbreviations remain review proposals. None enter the index or query expansion automatically. Independent review and a benchmark are still pending.

## Host deployment and migration

1. Install the package in the host service environment. Keep the ledger/signing key and revocation watermark outside projections and agent-writable directories. Run guidance through the host service identity; do not give an agent the watermark's write identity.
2. Configure an **absolute** `revocation_state_directory` in the host-owned trust configuration. On Linux, directory mode must be 0700 and database mode 0600, owned by the service user; the reader checks this. On Windows, administrators must apply and verify equivalent ACLs before deployment. No Windows ACL attestation is claimed by the Linux service template.
3. Existing current-schema ledgers keep all signed events unchanged. Subscribe each projection using `lightyear_factory annotate ... subscribe-revocations --projection <directory>`, and refresh the channel. Enroll that current signed head/list with `lightyear_toolkit.revocations.provision_state`; this is an explicit administrator operation, never reader recovery. Existing rows are not overwritten. Verify the reader once as the host service, then verify the agent cannot open or delete the state.
4. For an incompatible legacy ledger, run `python tools/migrate_graph_annotations.py --ledger <old> --public-key <old-public-key> --output <new-proposals.json>`. It verifies every signature and chain link and leaves the old bytes intact. It transfers only downgraded proposals, never approvals, portability or outcomes. Add them to a fresh ledger and obtain fresh leak checks, named-owner review and Tower decisions. A malformed chain is refused.
5. Configure the fixed paths in `deploy/graph-revocations/lightyear-revocations.service`, install the service/timer as administrator and enable the timer. It refreshes every five minutes; the signed validity remains 15 minutes. The supplied template is **not installed or activated** by this change. Check service exit status and perform an expiry/readiness test before enabling agent guidance.

Expiry now advances a date-derived signed sequence even without a ledger append. Heartbeats within a day can extend freshness without changing the revoked set. A missing, empty or deleted watermark fails closed; readers never silently enroll an old projection. Clock rollback or list changes at an unchanged sequence are rejected. An administrator able to roll back both the clock and host state remains outside this boundary.

Provider credentials must come from the approved broker lease; the two environment-variable fallbacks were removed. Howard previously approved provider-only Anthropic/Gemini leases. Builders and verifiers gain no leases. Gemini numbered snapshots are accepted, with exact response-version binding. Graph CI again checks B05/B06 isolation; graph and B06 changes must be published as separate PRs.
