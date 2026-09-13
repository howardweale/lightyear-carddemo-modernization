# CloudBank AlloyDB platform qualification

Status: implementation and live campaign in progress. Authorized on 2026-09-12.

The active campaign is `alloydb-platform-20260912a`. Current controls (TLS, manifests,
External Secrets synchronization and metrics for all 16 current pods), runtime identity,
retained immutable-image security and synthetic alert fire/recovery have passing evidence.
The corrected recovery run also passed: PITR 507 seconds, backup restore 451 seconds, RPO
30 seconds, exact coverage of 7,999 rows, eight tables and three sequences. Both isolated
restore targets were deleted. Its receipt content hash is
`a5ad6a27c21d83d76f5e699724867aab0f4e9452faf7cf0c2fbec870de3d7e3b`.
The corrected rotation run verified the new and restored values on both replicas, restored
the original template/version policy, disabled temporary version 8 and retained restored
version 9. Its receipt content hash is
`f1cdaa7e4d0507560db2e464cbc77979d38d064dae48d11fe3fc39a6173acb62`.
The first measured load completed 5,314 requests with zero errors but failed the unchanged
500 ms aggregate p95 limit at 589.44 ms. The first completed backup and PITR restore had
matching table data but advanced sequence counters; that failed evidence remains retained.
The isolated load rerun passed the same unchanged workload and limit: 5,428 requests,
zero errors, 458.91 ms aggregate p95, 300 seconds and ten users. All 207 cycles completed;
final balances and journal effects matched. No application image, resource limit, workload,
comparator or performance threshold was changed to obtain that result.
The isolated network rerun passed 130 TCP checks, including two denied rounds and restored
allowed traffic; all 18 owned resources were removed. AlloyDB primary failover passed in
333 seconds, moving from `us-west1-c` to `us-west1-b` with the same primary identity and
private address. Acknowledged data, idempotent replay, new business operations and all 16
application process identities passed their checks. The failover observation content hash is
`c1b0e5e802647a03b2359aefc4879665f8e985120aa0e375723241d1668fde01`.
Nine of eleven operational phases have passing evidence. The application drill passed all
eight forward and return rollouts and the single-node evacuation, with exact database state
preservation. Its subsequent concurrent failure-domain evacuation failed the existing readiness
timeout: sixteen replacement JVMs from the two database namespaces concentrated on one 4-vCPU
node, reached 101% reported CPU and repeatedly failed startup probes. Each AlloyDB service
retained one ready replica. All eight subsequently recovered; the failed observation remains
retained. The cleanup retry restored all selectors, removed the probe and released the owned
drill lease with no errors. Two rejected recovery eviction attempts were reconciled against
the exact original pod UIDs; those pods recovered without an observed eviction.
The paced failure-domain continuation passed all eight service recoveries, final evacuation,
exact database-state comparison and scheduling restoration. Canary, business-journey cutover
and rollback still require completed evidence, as does trace correlation.
Qualification is still pending the remaining operational results and complete admission.

The corrected planned-evacuation procedure uses Kubernetes
[`drain --pod-selector`](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_drain/)
to pace cold starts by service on this shared cluster. It waits for that AlloyDB service to
recover before evicting the next service, then performs the original full drain for remaining
workloads. Disruption budgets, availability sampling, readiness checks, database-state equality,
application images, resource settings and acceptance thresholds remain unchanged. This qualifies
the paced maintenance procedure; simultaneous unplanned node or region loss is not established.
Continuation requires the exact signed, fully restored failure checkpoint and revalidates the
retained eight rollouts and node evacuation before collecting the unfinished evidence.

Run network enforcement after all restore probes and their policies are removed, and without
overlapping another configuration or pod change. Its baseline deliberately includes all observed
policies; a concurrent isolated-restore policy change caused the first network attempt to fail
closed and remove its owned probes. The guard must remain strict.

The first correlation attempt found 16 request-log records but no exported trace spans. The
shared collector reported `ResourceExhausted` and the project had a 3,000,000-span daily Cloud
Trace ingestion quota. The original logging configuration was retained and recovery completed.
A quota increase request is prepared locally; it has not been submitted. Correlation still
requires a fresh passing live observation after trace ingestion is available.

This follow-up qualifies the synthetic nonproduction AlloyDB deployment created by MS71.
It preserves the original MS71 business-equivalence acceptance and MS67 Cloud SQL evidence.
The new platform receipt must bind the actual AlloyDB resource, namespace UID, eight immutable
application images, signed platform profile, controller commit, and all operational evidence.

The acceptance gate contains the 28 existing MS67 platform scenarios plus an explicit AlloyDB
primary-failover scenario, for 29 in total. Thresholds require at least three Kubernetes nodes
across two failure domains, two ready replicas of each
service, trusted TLS with at least 30 certificate days remaining, verified external-secret rotation,
metrics/logs/traces and alert recovery, zero high/critical image findings, and observed network policy.
Load must run for at least 300 seconds at 10 concurrent users, exceed 1,000 requests, have zero errors,
and meet the 500 ms aggregate HTTP p95 limit. Chat latency is reported separately.

AlloyDB-specific evidence must establish enabled scheduled and continuous backups, private encrypted
connections, regional availability, a completed on-demand backup, exact normalized backup restore
within 600 seconds, exact point-in-time restore within 630 seconds with recovery-point age at most
60 seconds, and a measured primary failover with zero observed data loss. Restore targets are fresh,
isolated temporary clusters; the source cluster is never overwritten by a recovery drill.

The application drills must measure controlled node and failure-domain evacuation, eight-service
rolling deployment with zero observed unavailable replicas, canary routing, 18 passing business
journeys, mandatory rollback, and final recovery. Shared nonproduction GKE nodes and the in-cluster
model are within this campaign's controlled-drill scope. Every temporary resource requires an
ownership-bound recovery record and verified cleanup.

Prior signed image/provenance evidence may be retained only for exactly identical immutable image
digests, with its original measurement time and scope disclosed. Cloud SQL runtime, load, database
recovery, secret rotation, and network observations cannot stand in for AlloyDB observations.

Only a verified, signed complete evidence chain may set `alloydb_platform_qualified: true`.
Production readiness, customer certification, and unplanned regional-failure qualification remain
outside this synthetic nonproduction campaign. Failed measurements remain recorded and cannot be
converted to passing results by changing a threshold after the run.

The first complete restore attempt exposed PostgreSQL sequence WAL allocation: account and journal
sequence counters restored 30 and 31 ahead, while replacing only those sequence hashes reconstructed
the exact original checkpoint hash. Backup preparation now records each sequence's existing value
and `is_called` state with `setval` while all application writers are stopped and no other application
role sessions exist. This changes neither counter values nor table data; the full before/after hash
must match. The resulting backup and PITR restores must still match the entire checkpoint exactly.
The qualification covers this quiesced procedure; it does not claim exact sequence counters during
continuous-write recovery. PostgreSQL's [sequence WAL implementation](https://github.com/postgres/postgres/blob/REL_16_STABLE/src/backend/commands/sequence.c)
documents the allocation and `setval` behavior used by this procedure.

The tracked `tools/cloudbank_alloydb_control.py` runner binds secret rotation, log correlation,
alert recovery, network enforcement, runtime identity and sustained load to the signed campaign
context and accepted MS71 receipt. `tools/cloudbank_alloydb_recovery.py` owns isolated backup/PITR
restores; `tools/cloudbank_alloydb_platform.py` admits the final complete evidence chain. The context
directory retains the signed platform profile, managed profile, accepted AlloyDB MS66 receipt and
target journey. All commands require the existing nonproduction acknowledgement for live mutations.

After complete admission, the platform runner's `export` action verifies the receipt again
and copies all 19 original signed input and receipt files without changing their bytes. Its
signed export manifest records both byte and content hashes. The public reader requires a
reviewed, committed manifest byte hash and verifies every file plus the original MS71 binding.
An incomplete gate cannot create an export. Export is local and does not claim a new cloud
readback or publish a website. The local publisher reads `docs/receipts/alloydb-platform.anchor.json`
only after that reviewed anchor is created from a complete verified export. Without it, current
projections remain unchanged. The anchor contains only the bundle path and export byte hash;
its loader rejects missing or altered evidence before projecting qualification.

Windows Modern Standby interrupted early attempts. Live control and recovery entry points now hold
a [temporary system and display execution request](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate)
while running, and release it on exit. They use one storage worker for small evidence checkpoints.
These process-scoped settings do not change the saved power plan or gcloud configuration. Failed
attempts and their subsequent recovery records remain retained separately from passing evidence.

An External Secrets status update raced with a rotation version patch during a later attempt.
The version-pinning adapter now permits at most three attempts only when a fresh read proves
that just status/resource-version bookkeeping changed. Each attempt rechecks lease ownership,
the original specification, UID and current resource version. Changed specifications, owners,
unchanged resource versions and ambiguous transport timeouts still fail closed. The failed
attempt restored the original values and version policy and disabled its temporary version.

Provider operations follow Google's [backup and recovery documentation](https://docs.cloud.google.com/alloydb/docs/backup/overview),
[point-in-time recovery instructions](https://docs.cloud.google.com/alloydb/docs/backup/restore-pitr),
and [primary failover procedure](https://docs.cloud.google.com/alloydb/docs/instance-primary-secondary-failover).
