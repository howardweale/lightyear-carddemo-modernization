# CloudBank AlloyDB platform qualification

Status: implementation and live campaign in progress. Authorized on 2026-09-12.

This follow-up qualifies the synthetic nonproduction AlloyDB deployment created by MS71.
It preserves the original MS71 business-equivalence acceptance and MS67 Cloud SQL evidence.
The new platform receipt must bind the actual AlloyDB resource, namespace UID, eight immutable
application images, signed platform profile, controller commit, and all operational evidence.

The acceptance thresholds remain those of the existing MS67 platform contract: 28 operational
controls, at least three Kubernetes nodes across two failure domains, two ready replicas of each
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

Provider operations follow Google's [backup and recovery documentation](https://docs.cloud.google.com/alloydb/docs/backup/overview),
[point-in-time recovery instructions](https://docs.cloud.google.com/alloydb/docs/backup/restore-pitr),
and [primary failover procedure](https://docs.cloud.google.com/alloydb/docs/instance-primary-secondary-failover).
