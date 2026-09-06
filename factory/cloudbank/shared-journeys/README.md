# Shared live CloudBank journeys

`cloudbank-journeys.sh` executes the 18 business assertions shared by the
whole-application contract against the running GKE PostgreSQL target. It checks
HTTP results against actual balances, journals, durable queue state, and new pod
identities. No supplied observation or simulator can be selected through this CLI.

The output type is `lightyear-cloudbank-shared-journey-execution`. A passing run
means these target journeys passed. It does **not** complete MS65, MS66 or MS67,
and it is deliberately not accepted as their signed execution receipt. Native
Oracle/TEQ/MicroTx execution and a matching PostgreSQL lane remain necessary for
MS66 equivalence. Backup/restore, load, secret rotation, telemetry correlation,
alerts, failure-domain recovery, cutover and rollback remain separate work.

## First command: preflight

Run from the repository in Cloud Shell, after sourcing the qualification env.
No application image rebuild is needed to install this Python harness.

```bash
source "$HOME/ms67-qualification.env"
./cloudbank-journeys.sh preflight \
  --image-lock "$MS67_IMAGE_LOCK" \
  --signer "$MS67_SIGNER"
```

Set `MS67_IMAGE_LOCK` to the existing eight-image lock and `MS67_SIGNER` to your
signer identity. `GCP_PROJECT_ID`, `GCP_REGION` and `GKE_CLUSTER_NAME` select the
explicit kube context. The default namespace is `cloudbank-ms67`; override with
`--namespace` for another authorized target. Refresh that context's credentials
with the existing qualification runbook if needed.

Preflight validates the signed MS64 receipt (by default beside the image lock),
its binding to all eight immutable images, both ready replicas for each service,
live HTTP readiness, nonproduction project/namespace labels, and OAuth grants.
It issues tokens but does not create fixtures, change grants, restart workloads,
or create a database probe. It reports all five token roles together:

| Role | Existing authorization-server client | Required scopes |
|---|---|---|
| owner | DEFAULT | `cloudbank.read cloudbank.write cloudbank.transfer` |
| account | SERVICE | `cloudbank.internal` |
| test | SERVICE | `cloudbank.test` |
| credit | CREDITSCORE | `cloudbank.read` |
| chat | CHATBOT | `cloudbank.read` |

Credentials come from the existing `cloudbank-azn-server-external` Secret Manager
record, into memory only. The default client must be dedicated to synthetic
journeys, have an ID of at most 20 letters/digits/underscores/hyphens, and have no
internal/admin privilege. An existing Customer with this ID is reused only if
marked `lightyear-synthetic-journey-owner`; otherwise execution stops before
creating accounts. Configure missing grants through the established secret and
authorization-server workflow, then repeat preflight. The harness never expands
a client's authorization automatically.

## Run

Reserve the nonproduction namespace for this run. Run only one journey executor
at a time, without concurrent deployments or autoscaling changes. The recovery
logic refuses changed deployment UIDs, images, unexpected replica counts, or
Checks configuration changed by another operator.

Supply an approved immutable PostgreSQL client image in `MS67_POSTGRESQL_PROBE_IMAGE`
(`registry/repository@sha256:<64 hex characters>`). It must contain `psql` and
`sleep` and support UID/GID 70, a read-only root filesystem, and no Linux
capabilities. The pinned image must be available to the cluster. This is a
short-lived read-only queue probe, not a replacement database. Do not use a tag.

```bash
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
./cloudbank-journeys.sh run \
  --image-lock "$MS67_IMAGE_LOCK" \
  --probe-image "$MS67_POSTGRESQL_PROBE_IMAGE" \
  --signer "$MS67_SIGNER" \
  --evidence-bucket "gs://YOUR_PRIVATE_EVIDENCE_BUCKET/shared-journeys"
```

Run inside the established persistent shell session. Progress prints every 20
seconds. The signing key is read from
`LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY`, or from the existing Secret Manager
secret `cloudbank-ms67-evidence-key`. Override the secret reference with
`--evidence-key-secret`; never pass key material as an argument.

Execution creates three synthetic accounts through the Account API, with a unique
run marker, and retains their bounded records for inspection. Transfers require
exact balance/journal deltas and rejection without mutation. Check deposit and
clearance require a processed queue record plus their precise journal effects;
replaying producer keys must not change state. CloudBank's declared check
clearance changes PENDING to DEPOSIT; this test does not invent a balance-credit
settlement behavior. Credit-score and chatbot checks validate their declared
response boundaries, not real credit decisions or model answer quality.

The disruptive checks:

- Restart Account and verify the same durable state.
- Temporarily override Checks' journal endpoint with an unavailable TEST-NET
  address, observe a real PROCESSING queue claim, stop and force-delete the
  owned Checks pods, restore the endpoint and replicas, then require a higher
  delivery-attempt count and exactly one journal effect. The probe never writes
  queue rows or manufactures leases. Failure to observe the claim fails the test.
- Scale Account to zero, require Transfer dependency failure without mutation,
  restore Account and Transfer, then prove a successful transfer.
- Run two opposite transfers concurrently and check conservation and all four
  journal entries.
- Stop all eight deployments, restore them in dependency order, obtain fresh
  OAuth tokens and repeat the state and business checks.

All services are unavailable during the full-stack restart. SIGINT/SIGTERM and
ordinary failures trigger restoration. Force deletion is confined to the owned
Checks pods after its deployment is scaled to zero. A failed recovery prevents a
passing result. The harness uses Kubernetes API tunnels, so this evidence does
not itself prove ingress, TLS policy, service-mesh routing, or distributed trace
correlation.

## Evidence and recovery

Small JSON files go to a fresh directory under `~/ms67-evidence` (or a fresh
`--output-root` outside the checkout). `journeys.json` is HMAC-signed with the
existing evidence key. `SHA256SUMS` covers it and the signed restoration state.
Raw HTTP responses, tokens, passwords, SQL output and chatbot text are not
persisted. Upload failure has a nonzero exit code and retains local evidence;
it cannot change a failed journey into a pass.

Restoration intent is saved **before** scale-down or configuration changes in
`recovery-state.json`. If the shell is killed or disconnects during a mutation,
run this in a recovered session using the exact printed evidence directory:

```bash
./cloudbank-journeys.sh recover \
  --recovery-state /absolute/path/to/recovery-state.json \
  --signer "$MS67_SIGNER" \
  --evidence-bucket "gs://YOUR_PRIVATE_EVIDENCE_BUCKET/shared-journeys"
```

The same explicit context, evidence key and mutation acknowledgment are required.
Recovery verifies the saved signature and current deployment identities before
restoring the recorded replica counts and Checks setting. It also removes the
run's probe pod. Recovery produces its own result in a fresh directory; it cannot
complete an interrupted journey run. Inspect the retained synthetic fixtures
before running again. Never publish operational evidence or credentials to Git.

## Local verification

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_cloudbank_journeys.py'
```

Tests exercise a stateful test double and a local HTTP server, including false
HTTP success, duplicate effects, failed clearance, missing redelivery evidence,
interruption, recovery failures, credential redirect rejection and mutation
preconditions. These are harness tests, not claims that a native GKE run passed.
