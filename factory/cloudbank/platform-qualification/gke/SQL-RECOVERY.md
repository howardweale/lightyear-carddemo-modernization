# Isolated Cloud SQL recovery drill

`cloudbank-sql-recovery.sh run` (PowerShell twin available) exercises an on-demand
Cloud SQL backup and point-in-time recovery against the signed, deployed MS64
images and a passed shared-journey observation. Run it from Cloud Shell or another
host with the same explicit GKE context, Google Cloud CLI, kubectl and Python 3.11+.
The client-only PostgreSQL probe must already be approved, scanned and published
under an immutable image digest. No image rebuild is required.

The operator must have the existing nonproduction project/namespace authorization,
Cloud SQL backup/clone/restore/delete access, Kubernetes deployment scale and
temporary pod/network-policy create, read, replace and delete access, read access to the evidence signing key and
application Secret metadata, and access to the private evidence bucket. The runner
does not grant permissions or change project, database or network configuration.

## What runs

1. Verify the signed current MS64 receipt, bound image lock, all 18 passed shared
   journeys, namespace identity, all eight deployed images/readiness, source
   private PostgreSQL 16 instance and enabled backup/PITR configuration.
2. Discover each application's JDBC database from synchronized Kubernetes Secrets
   in memory. Reject other hosts, embedded credentials and unsupported JDBC options.
   Prepare a temporary read-only client pod for each configured database and hash
   source state before stopping services,
   so missing SQL permissions fail early. A credential must be able to read every
   persistent application table and sequence in its configured database.
3. Save signed recovery intent before scaling each of the eight applications to
   zero. Wait for all writer pods, including Checks, to exit. Hash the stable state,
   create an on-demand backup, then repeat the state comparison. After that slow
   preparation, poll for a Cloud SQL recoverable timestamp after the checkpoint
   whose age is between zero and 60 seconds. Use that accepted response directly
   for the PITR clone, revalidating source identity immediately before submission.
4. Create a fresh `ly-sql-restore-*` instance at that timestamp. Restore the original
   application replica counts and readiness while the clone provisions. Probe the
   isolated instance and compare its state to the checkpoint.
5. Restore the explicit backup ID into that same isolated instance, then repeat the
   comparison. The source is never a restore or delete destination.
6. Restore applications and remove temporary pods, policies and the owned validation
   instance. The on-demand source backup is retained and identified in the evidence.
   Instance ownership is checked against the recorded clone operation and creation
   time. Uncertain submissions or changed identities stop automatic deletion and
   produce a failed result with recovery instructions.
7. Sign the bounded result and recovery journals, write SHA256SUMS, upload to the
   private GCS prefix, download every file independently and compare the bytes.

Expect a service interruption during the stable checkpoint and backup preparation,
and temporary Cloud SQL charges for the validation instance. Progress prints every
20 seconds. Per-operation waits are bounded; reaching a wait limit records failure
and invokes recovery. A Cloud SQL operation can continue after a local timeout.

The client pods are prepared before the incident timestamp and reused for source,
PITR and backup-restore comparisons. Image pulls and pod deletion are not repeated
for every snapshot. The client pool is removed during final cleanup, with a
one-second termination grace period for these read-only clients and a two-hour
active lifetime as a fallback. This does not pre-create the restored database.
PITR still creates a fresh isolated Cloud SQL instance within the timed recovery.

Source applications resume in four dependency groups while the clone provisions:
Authorization; Customer, Account, CreditScore and Chatbot together; Transfer and
Checks together; then TestRunner. Each group's scale-up requests are submitted
before waiting for its members, so independent pods can initialize concurrently.
Deployment UID, locked image and replica preconditions still apply, and a service's
signed stop intent is cleared only after readiness is observed. Recovery journal
writes remain serial. Failed members retain their intent; cleanup attempts the
remaining groups and reports failure, allowing `recover` to retry safely.
The existing shared business journey restart behavior is unchanged.

`application_restoration_checks` records bounded per-service restoration timings
and failure stages. These measure scale-up request through readiness observation
and checkpointing; observation can lag actual pod readiness. All eight application
HTTP readiness checks still run after restoration, inside the PITR recovery timer.
Neither the 600-second RTO limit nor the 60-second recovery-point-age limit changes.
Cloud SQL clone duration can still cause a live run to exceed RTO.

The pool starts with no network ingress or egress. Before each snapshot the runner
checks the policy UID and current rules, then replaces its single PostgreSQL /32
destination using the observed resource version. Only the current validated source
or restore address is allowed. Client UID, image, credential references and readiness
are checked before execution. Credentials stay in secretKeyRef-backed pod environment
variables; only the private destination address is supplied to `env PGHOST=...`.
The read-only snapshot transaction may be attempted up to three times to allow
network-policy propagation. All attempts count toward the same recovery timer;
backup, clone, restore and delete submissions are never retried automatically.

## Execute

Set the existing input paths in the original authenticated shell. `JOURNEYS` points
to the successfully verified full execution's `journeys.json`, not its preflight.

```bash
cd "$HOME/lightyear-carddemo-modernization"
git pull --ff-only origin main
source "$HOME/ms67-qualification.env"
gcloud config set account howard.weale@gmail.com
gcloud auth print-access-token >/dev/null
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS

bash ./cloudbank-sql-recovery.sh run \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --cluster "$GKE_CLUSTER_NAME" --namespace cloudbank-ms67 \
  --source-instance "$CLOUD_SQL_INSTANCE" \
  --image-lock "$MS67_IMAGE_LOCK" \
  --journeys "$JOURNEYS" \
  --probe-image "$MS67_POSTGRESQL_PROBE_IMAGE" \
  --evidence-bucket "$MS67_EVIDENCE_BUCKET/sql-recovery" \
  --signer howard.weale@gmail.com
```

Run inside an existing tmux pane or a detached tmux session to survive a browser
disconnect. Do not force a nested tmux session. If authentication has expired,
complete `gcloud auth login` before starting; no credentials should be pasted into
the terminal command, logs or GitHub.

## Recovery and interrupted uploads

Keep the printed `MS67_SQL_RECOVERY_ROOT`. After a process interruption, run the
following with the same project/region/cluster/source arguments. This validates both
signed recovery journals, restores any stopped applications and cleans up only the
run's owned temporary resources. It never resumes database mutations or converts a
failed drill into a passed observation.
Its success marker is `MS67_SQL_RECOVERY_CLEANUP=PASSED`; the original drill result
remains unchanged.

```bash
bash ./cloudbank-sql-recovery.sh recover \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --cluster "$GKE_CLUSTER_NAME" --namespace cloudbank-ms67 \
  --source-instance "$CLOUD_SQL_INSTANCE" \
  --recovery-root "$MS67_SQL_RECOVERY_ROOT" \
  --evidence-bucket "$MS67_EVIDENCE_BUCKET/sql-recovery" \
  --signer howard.weale@gmail.com
```

A submission with no returned operation ID is explicitly inconclusive. Inspect
the named target and Cloud SQL operations before any manual cleanup; do not simply
resubmit the clone or change the source instance. A protected validation instance
is retained for operator cleanup. No protection is disabled automatically.

`pitr_preflight` records the last five recovery-time observations, total attempt
count, API query durations, UTC observation times, checkpoint offsets and measured
ages. A point that is old, in the future, or before the checkpoint is retried within
the existing 600-second wait limit. The accepted response is not replaced by a
second unvalidated query. Timeouts preserve the final rejected observations and
restore applications. These diagnostics contain timestamps and durations only.

`phases` records up to 100 phase entries with UTC start/end timestamps, monotonic
elapsed seconds and running/completed/failed status. Nested phases are included in
their parent's duration; do not add all durations together. `failure_stage` identifies
the innermost failed phase, such as backup-restore polling or snapshot validation.
`application_restoration_checks` retains the last three restoration results with
bounded failure codes and stopped-service names. The signed SQL operation journal
also saves the latest observed operation status, provider timestamps and an error
presence flag. Arbitrary server error messages and database output are not recorded.
These diagnostics help separate provisioning, application recovery and validation
time without changing the 60-second recovery-point or 600-second recovery-time gates.

`validation_instance_state: not-requested` means this run never submitted a clone;
in that case `validation_instance_deleted: false` does not indicate a leaked clone.
The other states distinguish an uncertain submission, a requested creation, a
created instance and confirmed deletion. Check the signed operation journal when
a submission is uncertain.

The run writes `database-recovery.json`, `sql-recovery-state.json`,
`recovery-state.json` and SHA256SUMS. Recovery additionally writes
`cleanup-result.json`. A failed upload retains the signed local files; `recover`
can repeat cleanup and archive them without rerunning the drill. Do not edit the
signed observations or recalculate their signatures to change a result.

## Evidence scope and limits

The success marker is `MS67_ISOLATED_SQL_RECOVERY=PASSED`. This is an isolated
database drill, not an MS65/MS66/MS67 completion receipt.

- PITR recovery-point age is measured from the declared incident to the actual
  selected recoverable timestamp and must be between zero and 60 seconds. The
  source workload is quiesced; continuous-write RPO is not demonstrated.
- PITR database RTO includes the clone request, source service recovery, target
  provisioning and read-only state validation. Backup restore RTO covers restoration
  into the already provisioned isolated target and validation. Each must be no more
  than 600 seconds. These are database timings; application failover, endpoint
  redirection and business-journey recovery on the restored database remain open.
- State hashes preserve row values, duplicate counts, columns and sequence state
  in configured application databases. Table names/rows are not persisted. SQL
  snapshots use repeatable-read/read-only transactions and reject row-security
  filtering, foreign tables and unlogged tables. Roles, grants, large objects,
  nonconfigured databases and complete schema-object equivalence are outside scope.
- The managed backup's ID and metadata are bound to the evidence. A metadata hash
  is not a checksum of backup bytes. `managed_backup_bytes_sha256` is explicitly
  null; this runner does not populate the admission contracts' `backup_sha256`.
- Signed MS65/MS66 admission, continuous-load/correlated telemetry, alert recovery,
  secret rotation, failure-domain recovery and cutover/rollback remain separate
  gates. No acceptance contract is relaxed by this runner.

Provider references: [Cloud SQL PITR](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr),
[clone command](https://docs.cloud.google.com/sdk/gcloud/reference/sql/instances/clone),
[backup restore command](https://docs.cloud.google.com/sdk/gcloud/reference/sql/backups/restore).
