# Cloud SQL HA failover and application reconnection

This runner collects a separate, bounded operational observation. It does not
admit MS65, MS66 or MS67, or change the isolated PITR requirement. The independent
HA recovery limit is 600 seconds from before failover submission through provider,
application process, data, and business validation, including polling overhead.

Google documents that [regional Cloud SQL failover](https://docs.cloud.google.com/sql/docs/postgres/high-availability)
promotes the standby, closes existing database connections, and retains the
connection endpoint. The promoted zone remains primary. This drill submits one
[`gcloud sql instances failover --async`](https://docs.cloud.google.com/sdk/gcloud/reference/sql/instances/failover)
request. It does not automatically fail back.

## What the drill establishes

| Check | Required evidence |
| --- | --- |
| Admission | Signed current MS64 receipt, matching immutable eight-image lock, signed complete shared journeys, same nonproduction project/namespace identity |
| Source | Private PostgreSQL 16 native primary, REGIONAL, distinct primary/standby zones, backups and PITR enabled, no active SQL operation |
| Application baseline | Eight ready services, two replicas each, all five OAuth roles, five application datasources bound to the source and matched to the environment in both running containers |
| Failover | One saved operation, matching source/project/type, DONE without error, serving zone changed to the former standby, same instance creation identity and endpoint |
| Process continuity | All 16 pod/container/start-time/restart-count fingerprints unchanged; no scaling, rollouts or configuration changes by this runner |
| Data and replay | Marked customer and three synthetic account balances/journals match the acknowledged checkpoint; processed Checks messages survive; transfer replay causes no extra ledger effects |
| Reconnection | Fresh OAuth tokens, a new transfer, a new Checks deposit/clearance, Credit Score and Chat responses, final readiness and datasource bindings |
| Cleanup | Owned probe deletion observed, local tunnels closed, application readiness recorded; marked fixtures retained |

HTTP requests use service port-forwards and exercise selected application paths.
This does not establish reconnection of every replica's connection pool. It does
not measure continuous traffic downtime, continuous-write RPO, real zone failure,
GKE node recovery, or the remaining operational gates. It does not fabricate or
combine MS65/MS66 prerequisite receipts. Cloud SQL may reject failover when the
standby is unavailable; an explicit unavailable flag blocks admission.

## Prepare and preflight

Use the original Cloud Shell repository and environment. Finish other database
recovery operations first and run one operator drill at a time. Avoid simultaneous
application deployments, secret rotation or other database operations. Keep the
evidence directory on the persistent home volume. Run the longer `run` action in
your existing tmux session; switch to that session instead of nesting tmux.

```bash
cd "$HOME/lightyear-carddemo-modernization"
source "$HOME/ms67-qualification.env"

export MS67_POSTGRESQL_PROBE_IMAGE="$(cat "$HOME/ms67-evidence/ms67-client-probe.s68tTb/publish.rsSbVM/probe-image.txt")"
ms67_ha_inputs=(
  --project lightyear-ms67-nonproduction
  --region us-west1
  --cluster cloudbank-ms67
  --namespace cloudbank-ms67
  --source-instance cloudbank-ms67-postgres
  --image-lock "$HOME/ms67-evidence/ms67-deployment-fixes.n077woa6/image-lock.json"
  --journeys "$HOME/ms67-evidence/ms67-live-journeys-4396046fcdec/journeys.json"
  --probe-image "$MS67_POSTGRESQL_PROBE_IMAGE"
  --evidence-bucket gs://lightyear-ms67-nonproduction-ms67-evidence/sql-ha
  --signer howard.weale@gmail.com
)
./cloudbank-sql-ha.sh preflight "${ms67_ha_inputs[@]}"
```

Use receipt/image/probe paths for your deployment if they differ. The default
MS64 receipt is `cloudbank-edge-ai.receipt.json` next to the image lock; use
`--ms64-receipt` to supply another path. Admission rejects stale or mismatched
contracts instead of silently accepting an earlier build. Preflight reads cloud
resources, obtains OAuth tokens, and uploads private signed evidence. It creates
no application fixtures, probe pods or failover operations.

The signing key comes from `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` or Secret
Manager `cloudbank-ms67-evidence-key` in memory. Never print or paste it.
The approved service images need `printenv`; the runner reads only
`SPRING_DATASOURCE_URL` into memory to reject stale pod environments. SQL probe
credentials are supplied by Kubernetes `secretKeyRef` and never passed on the
command line.

## Run after a passed preflight

The run action performs a deliberate database failover and creates retained
synthetic fixtures. It requires the explicit existing nonproduction acknowledgment:

```bash
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
./cloudbank-sql-ha.sh run "${ms67_ha_inputs[@]}"
```

The runner repeats admission before mutation and reports progress every 20 seconds.
A pass requires `MS67_SQL_HA_RUN=PASSED`, signed `sql-ha.json` status
`passed-cloud-sql-ha-failover`, and successful evidence upload and independent
readback. The result retains `ms65_complete`, `ms66_complete`, and `ms67_complete`
as false. An upload failure returns nonzero even if the local observation passed.

The SQL operation wait is bounded to 30 minutes; readiness and read-only
reconnection waits are separately bounded to 10 minutes each. These observation
allowances let the runner record slow recovery and attempt cleanup. They do not
extend the 600-second pass criterion. Status reads may retry twice per wait with
2/4-second backoff; the original operation and deadlines remain fixed. Business
writes are not retried after an uncertain response. Partial fixture IDs and a
unique marker are retained for later operator review; no cleanup deletes accounts.

## Recover an interrupted run

Use the original printed `MS67_SQL_HA_ROOT`. Do not start a new run to resume a
saved intent: that could submit another failover. Recovery verifies signed state,
current environment/owners/images, waits for the known operation, checks readiness,
and deletes the owned probe. It never submits failover/failback, repeats business
writes, restores a backup, changes connection strings, or restarts applications.

```bash
./cloudbank-sql-ha.sh recover \
  --project lightyear-ms67-nonproduction --region us-west1 \
  --cluster cloudbank-ms67 --namespace cloudbank-ms67 \
  --source-instance cloudbank-ms67-postgres \
  --recovery-root "$MS67_SQL_HA_ROOT" \
  --evidence-bucket gs://lightyear-ms67-nonproduction-ms67-evidence/sql-ha \
  --signer howard.weale@gmail.com
```

Set `MS67_SQL_HA_ROOT` in your shell to the printed directory first; a child process
cannot export it into its parent shell. A successful recover emits
`MS67_SQL_HA_RECOVER=PASSED` and a separate `ha-cleanup.json`. It preserves the
original drill observation and cannot turn a failed or interrupted drill into
qualification success.

If the failover submission response was lost before its operation name was saved,
recovery reports `ha-submission-uncertain-inspect-source-operations`. Inspect source
operations read-only and reconcile the incident; do not resubmit blindly or edit
signed state to invent an operation binding. Application restarts by Kubernetes or
another operator fail process continuity even when services eventually recover.

Only `sql-ha.json`, `sql-ha-state.json`, `recovery-state.json`, `ha-cleanup.json`
when present, and their SHA256SUMS are uploaded. No credentials, raw database rows,
HTTP response bodies or raw provider errors are persisted. Application data and
process identities are represented by hashes and bounded synthetic identifiers.

## Local validation

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_cloudbank_sql_ha.py -v
```

Tests use explicit business and provider doubles to exercise safety and evidence
semantics. They do not constitute live Cloud SQL HA evidence. The full repository
verification suites discover the same tests on Linux and Windows. The PowerShell
entrypoint is `cloudbank-sql-ha.ps1` with the same action and flags.
