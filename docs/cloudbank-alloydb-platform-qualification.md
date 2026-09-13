# CloudBank AlloyDB platform qualification

Status: implementation and live campaign in progress. Authorized on 2026-09-12.

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

Windows Modern Standby interrupted early attempts. Live control and recovery entry points now hold
a [temporary system and display execution request](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate)
while running, and release it on exit. They use one storage worker for small evidence checkpoints.
These process-scoped settings do not change the saved power plan or gcloud configuration. Failed
attempts and their subsequent recovery records remain retained separately from passing evidence.

Provider operations follow Google's [backup and recovery documentation](https://docs.cloud.google.com/alloydb/docs/backup/overview),
[point-in-time recovery instructions](https://docs.cloud.google.com/alloydb/docs/backup/restore-pitr),
and [primary failover procedure](https://docs.cloud.google.com/alloydb/docs/instance-primary-secondary-failover).
