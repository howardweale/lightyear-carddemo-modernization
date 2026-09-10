# Finish MS67 from the retained evidence

Run `python3 tools/ms67_finish.py --execute` from a clean checkout of the reviewed
commit on the existing Mac CLI. It uses `howard.weale@gmail.com`, project
`lightyear-ms67-nonproduction`, region `us-west1`, cluster and namespace
`cloudbank-ms67`. The default evidence root is `~/ms67-evidence`.

The launcher verifies and retains the existing MS65 receipt, matching MS66,
passed regional 300-second/10-VU load, and approved 630-second SQL reassessment.
It has no execution path that submits MS65, MS66, SQL recovery or sustained load.
The original measurements, signatures and failed attempts remain intact.

## Remaining execution

1. Create eight signed OCI packaging revisions in Cloud Build using the existing
   successful image build's account and resolved builder digests. Each revision
   changes only one image label. The runner saves each baseline image, copies its
   complete image configuration with that label added, streams unchanged layers
   into a load archive, then loads and pushes it. It does not rebuild a Dockerfile,
   which can rewrite inherited configuration. Docker inspection must prove identical layers,
   platform and execution configuration, with a distinct image/config digest.
   Both baseline and candidate signatures/provenance are verified. Fresh Trivy
   scans cover OS and Java packages with zero high/critical findings. Baseline
   vulnerability coverage is explicitly derived from the identical filesystem,
   not described as an independent baseline scan.
2. Run the canonical CreditScore secret rotation/restoration, eight-service
   log/trace correlation, synthetic alert/recovery, network enforcement and
   runtime UID/GID checks. Identity enforcement converges to 65532:65532 and
   skips patches when already configured. Completed phase evidence is reused.
3. Roll all eight deployments to the candidate digests and back, while sampling
   deployment availability. Then evacuate a node and a separate failure domain
   using cordon/drain and PDB-respecting evictions. Compare normalized database
   table/sequence fingerprints and restore node scheduling.
4. Create two candidate replicas per service, expose equal baseline/candidate
   endpoint capacity, positively probe candidates, route all eight Services
   exclusively to candidate endpoints, execute the unchanged 18 shared journeys,
   then route back and remove the candidates. Compare database state immediately
   before and after rollback, retaining acknowledged target transactions.
5. Read current runtime identity, image and replica state; scan deployment
   policies; verify TLS, External Secrets, and fresh metrics for all sixteen
   current application pods. Assemble all 28 scenarios, run the canonical
   platform admission, upload and read back the signed receipt and evidence index.

Only a verified final platform receipt produces `MS67_CLOSEOUT=YES`. It qualifies
this bounded nonproduction environment; it does not claim production readiness.

## Resume and recovery

### Customer fixture reset on restart

The PostgreSQL customer `data.sql` contains `customer:3 runAlways:true`, truncates
the customer table, and reinserts fixtures. The fourth fixture receives a new
default timestamp. Repeated Liquibase initialization also updates its changelog
record. The recorded failure changed exactly `cloudbank_customer.customers` and
`public.databasechangelog` with equal row counts. These changes remain failures;
neither table nor any timestamp is excluded from the database comparison.

For the restored failure recorded by controller `9595747e91c75ad33607512932d65d9a6cff7ef6`,
the reviewed correction supports:

```sh
python3 tools/ms67_finish.py --execute \
  --retry-candidate-build 43bee3ac-7b44-4407-bafe-bdfedca5bd8e \
  --resume-drills --repair-customer-startup
```

This verifies the signed controller history, candidate provenance, existing
controls and exact two-table failure. It archives the preceding signed parent
and failed drill state. It then checks that all three expected customer
changesets were applied and the migration lock is free, and changes only the
customer Deployment's `LIQUIBASE_ENABLED` setting to `false`. This is a persistent
runtime correction for the **already initialized nonproduction database**.
Fresh databases and future schema upgrades still require an explicit migration
step before serving replicas start. This does not rewrite the fixture source,
rebuild images, modify database rows or change any acceptance threshold.

The guarded patch has a signed intent before mutation, retains the exact before
and after spec hashes, and can recover an interrupted response by accepting only
the expected old or new spec. Cleanup keeps the corrected serving configuration;
it does not re-enable the destructive fixture. A whole-database comparison and
zero-unavailable rollout must pass. Seven unchanged service rollouts are reused;
the customer rollout and both evacuation measurements are refreshed under the
new configuration, followed by cutover/rollback and final admission. Prior
measurements are retained in the archive and the configuration observation.
MS65, MS66, accepted SQL and sustained load are retained with their original
scope; the runtime correction concerns initialization, not request handling.

CI starts the actual materialized Customer JAR against isolated PostgreSQL,
reproduces the two-table difference with initialization enabled, then edits and
adds customer rows and verifies two corrected restarts preserve every table and
sequence. This is regression coverage, not live MS67 acceptance.

Cutover preserves the existing public OAuth boolean flags. They are not token
credentials; other literal password, secret, private-key and token values remain
rejected. Candidate provenance is checked against its original controller even
after the final runner advances to a reviewed corrective controller.

Repeat the same `--execute` command to resume an existing image build or reuse
completed phases. An uncertain submission is reconciled by its unique tag;
the launcher refuses to submit a duplicate when the outcome is unknown.

For the confirmed failed candidate build `43bee3ac-7b44-4407-bafe-bdfedca5bd8e`,
use the reviewed corrective commit and run:

```sh
python3 tools/ms67_finish.py --execute \
  --retry-candidate-build 43bee3ac-7b44-4407-bafe-bdfedca5bd8e
```

This verifies the original signed checkpoint, unchanged retained inputs, exact
build configuration, and terminal build failure. It requires that no live phase
started or completed. The failed session remains unchanged; a separate signed
session records its build ID, controller, checkpoint generation and hash. The
retry uses a new run ID and image tags. Repeat this same command to resume it;
include the same `--retry-candidate-build` argument with `--recover` if a later
live phase needs recovery. Never manually edit or delete either session's state.

### Continue the restored failure-domain attempt

The `evacuation-normalized-database-state-changed` failure on controller
`9c159d2b87d411a23b7dbb4e7cc8c41e3398d532` retained a passed rolling test and
single-node evacuation. Its old aggregate snapshots cannot reveal which table
or sequence differed, and this correction does not retrospectively pass it.

From the reviewed corrective checkout, use:

```sh
python3 tools/ms67_finish.py --execute \
  --retry-candidate-build 43bee3ac-7b44-4407-bafe-bdfedca5bd8e \
  --resume-drills
```

The continuation verifies the restored signed checkpoint, candidate security,
completed controls, rolling evidence and node evacuation. It archives unchanged
copies of the old parent and failed drill checkpoint before recording a signed
controller transition. Existing image provenance keeps its original controller
commit; no images or prerequisite receipts are rebuilt. Repeating the command
resumes that same continuation.

The runner skips the completed rolling and node tests. It chooses an occupied
failure domain different from the passed node's domain, since uncordoning alone
does not repopulate evacuated nodes. It records the new target and requires two
surviving workers. Existing deployment identities, specifications and Service
identities/selectors must still match the retained baseline.

New snapshots preserve table/sequence names, row counts and digests, plus the
schema digest. Both snapshots and their differences are checkpointed before an
equality failure is raised. No row values or credentials are included. Every
table, sequence and schema comparison remains mandatory; no object is excluded
or normalized away. A new difference prints `MS67_FINAL_DATABASE_DIFFERENCE` and
stops after cleanup, with the actual reason and signed result URI exposed.

After an interrupted live phase, stop the original CLI process and run:

```sh
python3 tools/ms67_finish.py --recover
python3 tools/ms67_finish.py --execute
```

Recovery reads the latest signed child checkpoint, restores only the recorded
resources, and refuses identity/spec drift. Runtime identity uses its canonical
forward-convergence continuation. A failed phase gets a fresh attempt after
recovery; completed rolling/resilience/cutover groups remain reusable. Do not
delete the state directory or restart from an unrelated checkout to bypass an
active or failed phase. If no durable child checkpoint exists, the runner stops
for inspection instead of guessing whether a mutation occurred.

The local operator lock prevents overlapping processes on this Mac. Cloud
checkpoints use generation preconditions; child tools retain their own locks,
and final drills acquire a cluster Lease. Intent is uploaded and read back before
the next mutation. Failed checkpoint readback blocks that mutation. Keep other
operators and writers out of this synthetic environment during the drills:
concurrent writes make exact state comparison inconclusive.

## What these measurements establish

Node/failure-domain drills measure controlled evacuation, not power loss or an
unplanned regional outage. Availability samples requested every second can miss
short interruptions; gaps over 45 seconds fail the observation. The intentionally
disruptive business journey scenarios run outside those sampling windows.

The canary percentage is 50% of ready endpoint capacity, not a measured assertion
that exactly half of requests used each release. Positive candidate health
requests and exclusive target endpoint readback accompany the traffic switch.
The revisions prove rolling and cutover mechanics with identical application
code; they do not claim validation of a new application implementation.

Metrics evidence covers GKE container CPU samples tied to each current pod name,
UID, container, cluster, namespace and creation time. It does not claim JVM- or
business-specific metric coverage. Raw logs, traces, database rows, secret values
and registry credentials are not uploaded. Temporary manifest inspection files
are removed when the scan exits.

The runner installs checksum-verified cosign 3.1.2 and Trivy 0.74.0 assets and the
repository's pinned distlib wheel. It requires Python 3.11+, Git, gcloud and
kubectl. It uses the existing GKE context and existing operator permissions; it
does not change IAM or enable APIs. Any denied permission or failed control is a
recorded blocker, never an inferred pass.
