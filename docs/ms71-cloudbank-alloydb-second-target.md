# MS71 — CloudBank AlloyDB Second Target

Status: complete — both live 18-scenario comparisons passed on 2026-09-12.
The [managed-target runbook](../factory/cloudbank/alloydb-second-target/README.md) describes the
implemented commands. MS71 is the explicitly selected number; MS68–70 are not renumbered or marked complete.

Campaign `ms71-20260912a` ran on controller commit `1fad7e6ee03d9e6b5f5c12f2dca67a57771b75d8`.
Oracle to Cloud SQL and Oracle to AlloyDB each passed all 18 business scenarios using the same
eight target service images and unchanged comparator. Both comparisons used fresh Oracle baselines;
all recovery checks passed and both managed target deployments were restored.

- [Final signed acceptance receipt](receipts/ms71-20260912a/ms71-alloydb-second-target.receipt.json)
- [Cloud SQL comparison](receipts/ms71-20260912a/sql-managed-comparison.json)
- [AlloyDB comparison](receipts/ms71-20260912a/alloydb-managed-comparison.json)
- [Signed export manifest and original-byte hashes](receipts/ms71-20260912a/publication-export.json)

The operator verified signatures and storage readbacks before exporting these original bytes.
Durable acceptance: `gs://lightyear-ms67-nonproduction-ms67-evidence/ms71/ms71-20260912a/ms71-alloydb-second-target.receipt.json`.
The receipt records `ms71_complete: true`, `production_ready: false`, and
`alloydb_platform_qualified: false`: this acceptance covers bounded synthetic business equivalence.

The separately authorized [AlloyDB platform follow-up](cloudbank-alloydb-platform-qualification.md)
completed on 2026-09-13: all 29 operational scenarios passed for the same eight services.
Its [new signed platform receipt](receipts/alloydb-platform-20260912a/alloydb-platform.receipt.json)
records `alloydb_platform_qualified: true` for synthetic nonproduction. The original MS71 receipt
above remains unchanged; production readiness and customer certification remain false.

The first Cloud SQL runtime execution passed, but receipt assembly rejected source files converted
to CRLF by the Windows checkout. Restoring exact pinned Git bytes allowed the unchanged comparator
to reassemble the original signed runtime observations. The [original failure](receipts/ms71-20260912a/sql-original-assembly-failure.json)
and [signed reassembly record](receipts/ms71-20260912a/sql-reassembly.json) preserve that history.
The CLI now checks source bytes before cloud preflight; this closeout guard postdates the recorded
live controller commit and does not change its evidence.

## Outcome

CloudBank can select managed AlloyDB for PostgreSQL as a second target alongside Cloud SQL for
PostgreSQL. Both targets run the same eight generated services and pass the existing whole-application
dual-lane comparison against the governed Oracle source. One milestone delivers the additional
target, both comparison runs, and their signed acceptance evidence.

| Comparison | Source | Target | Required result |
|---|---|---|---|
| Oracle → Cloud SQL | Pinned Oracle source plus the existing governed hardening | Cloud SQL PostgreSQL | All 18 existing scenarios pass |
| Oracle → AlloyDB | Same source revision, hardening, and source image lock | Managed AlloyDB PostgreSQL | All 18 existing scenarios pass |

The two target deployments coexist in separate namespaces with distinct database resources,
credentials, synthetic datasets, and queue ownership. Run the two comparisons sequentially by
default, retaining the MS66 isolated sequential source/target execution inside each comparison.
“Alongside” means both are supported and evidenced in the same campaign; it does not require
simultaneous fault injection. Each comparison gets a fresh Oracle lane and fresh fixture identities.

## Fixed application and comparison scope

The service set is exactly `azn-server`, `customer`, `account`, `transfer`, `checks`, `testrunner`,
`creditscore`, and `chatbot`. Use one immutable target image digest per service across both targets,
the same schema migrations and synthetic seed contract, and the same OAuth and model-boundary
contracts. Provider connection settings and deployment resources may differ; business behavior may
not. If a compatibility correction changes an application image or migration, rerun both target
comparisons with the new shared inputs.

Reuse the MS66 comparator, normalized outputs, scenario identifiers, and restart requirements from
[`cloudbank_whole_application_equivalence.py`](../src/lightyear_data/cloudbank_whole_application_equivalence.py)
and the shared harness in [`cloudbank_journeys.py`](../src/lightyear_data/cloudbank_journeys.py).
The [existing execution plan](../factory/cloudbank/whole-application-equivalence/execution-plan.json)
enumerates all 18 scenarios: readiness, authorization and rejection, reads, successful and rejected
transfers, Checks once-only processing and redelivery, duplicate suppression, credit and chatbot
boundaries, dependency failure, concurrency, targeted restarts, and full-stack recovery.

AlloyDB does not get a relaxed comparator, additional normalization exceptions, skipped scenarios,
or a reduced service set. PostgreSQL durable messaging and atomic transactions retain the same
existing intentional differences from Oracle AQ and MicroTx LRA.

## Implementation and execution steps within this milestone

1. **Introduce explicit managed-target identity.** Define a target profile with provider
   `cloud-sql-postgresql` or `alloydb-postgresql`, project, region, managed resource identity,
   observed engine version, cluster/context and namespace identity, database/schema mapping,
   connection mode, secret references, and configuration digest. Resolve identity through the
   provider control plane and bind it to the actual application and probe connection. Reject a
   profile whose declared provider cannot be verified or whose two targets resolve to the same
   database resource. Persist references and hashes, never credentials.
2. **Provision and render the additional target.** Add an AlloyDB cluster and writable primary
   instance on the selected nonproduction private network. Reuse the existing GKE application
   renderer with target-specific database egress, secret references, and a separate namespace.
   Apply the same schema migrations and seed contract. Keep Cloud SQL resources available and
   prove that AlloyDB services, probes, and queue consumers cannot accidentally use their database.
3. **Adapt connection and probe plumbing.** Keep application images and PostgreSQL JDBC behavior
   common. Support the selected private, encrypted AlloyDB connection path for applications and
   database probes. Ensure health checks, startup migrations, database roles, queue inspection,
   and reconnect behavior work through that same path.
4. **Execute both dual-lane comparisons.** Extend orchestration around the existing
   [`execute_dual_lane`](../src/lightyear_data/cloudbank_ms66_dual_lane_gke.py) path to accept the
   verified managed-target profile. Use a fresh campaign ID, separate comparison run IDs, and
   separate evidence prefixes. Pin controller commit, source and target image locks, prerequisite
   receipts, schema/fixture hashes, and comparator contract across both comparisons. Retain
   checkpoints so a failed target can resume without silently reusing evidence for changed inputs.
5. **Admit and report one milestone result.** Verify both signed comparison results, their target
   identities, exact common inputs, all service/scenario evidence, and recovery results before
   issuing the MS71 acceptance receipt. Add target-labelled results and receipt links to the
   existing documentation and Control Tower evidence surfaces when actual runs are available.

These are implementation steps within MS71, not additional milestones.

## Existing contracts that need careful integration

The current runner accepts a target namespace, but its target evidence is labelled generically as
PostgreSQL. It also carries `postgresql_image_id_sha256` from the MS61/MS64 prerequisite chain.
That historical container identity must remain a prerequisite binding; it cannot stand in for an
AlloyDB managed instance identity. Add provider identity in an explicit MS71 evidence envelope
around the unchanged business-comparison result. Do not rewrite signed MS61–67 receipts or invent
a database container image digest for a managed service.

The current [site-input renderer](../factory/cloudbank/platform-qualification/gke/render-site-inputs.sh)
resolves its database address using `gcloud sql instances describe`. Extract target resolution so
AlloyDB uses its own verified resource and address. The [GKE journey adapter](../src/lightyear_data/cloudbank_journeys_gke.py)
creates a separate SQL probe from the Checks JDBC datasource. A localhost proxy in an application
pod is not reachable at localhost in that probe pod: the probe needs its own connector or another
explicitly supported private connection. Keep network policy and identity checks consistent with
the selected connection mode.

The AlloyDB Auth Proxy supports IAM-authorized encrypted connections; its backend connection uses
TCP 5433 and its API calls use HTTPS. A proxy deployment therefore needs target-specific network
rules and workload identity configuration, not only the existing PostgreSQL-port allowlist.
See Google's [Auth Proxy documentation](https://docs.cloud.google.com/alloydb/docs/auth-proxy/overview).
Check required extensions and their versions against Google's
[supported extensions](https://docs.cloud.google.com/alloydb/docs/reference/extensions) before
choosing the AlloyDB engine version. These are implementation preflight checks, not equivalence evidence.

## Single completion gate

MS71 is complete only when one verifier establishes all of the following:

- Exactly both requested target types are present, with separately verified managed resources
  and isolated application/database state.
- Both comparisons bind the same approved source, target application images, schema/fixture
  contracts, and unchanged comparator. The source is identified as governed-hardened Oracle.
- Every service starts, satisfies the existing restart requirements, and finishes ready in each
  source and target lane. Every one of the 18 scenarios passes with exact expected normalized results.
- Both comparisons contain signed, content-addressed runtime observations and successful recovery
  evidence. Missing observations, invalid signatures, changed inputs, wrong target bindings,
  incomplete cleanup, or a failure in either target blocks overall completion.
- A signed MS71 receipt identifies the campaign, both comparison receipts and their hashes, both
  target profiles and live identities, common input hashes, scenario counts, and final result.
  The evidence is read back and verified from its durable store before publishing completion.

Local validation must cover wrong-provider and wrong-endpoint rejection, cross-target database
aliasing, service-image drift, altered/missing scenarios, differing normalized results, signature
tampering, mismatched campaign inputs, and interrupted-run recovery. Run existing MS66 comparator
regressions too. Test fixtures and dry runs cannot satisfy the live completion gate.

## Scope boundary and execution inputs

This milestone establishes bounded eight-service business equivalence on a second managed target
using synthetic nonproduction data. The prior Cloud SQL MS67 platform qualification remains bound
to its original environment. It is not inherited as AlloyDB backup/PITR, HA, performance, security,
cutover, or production certification. Database performance comparisons, AlloyDB-specific analytics
or AI features, customer production certification, and broad platform requalification are separate
scope. Application fault/restart scenarios already in the shared comparator remain required here.

Before the live campaign, resolve the project, region, GKE context and namespaces, AlloyDB engine
version and primary sizing, private connection mode, existing Cloud SQL resource, service image
locks, signed prerequisites, signer, secret references, evidence bucket, and resource cleanup policy
from the actual nonproduction environment. Retain all accepted MS67 evidence. Generated commands,
profiles, and readiness checks must report pending until both live comparisons pass.
