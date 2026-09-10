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
   changes only one image label. Docker inspection must prove identical layers,
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

Repeat the same `--execute` command to resume an existing image build or reuse
completed phases. An uncertain submission is reconciled by its unique tag;
the launcher refuses to submit a duplicate when the outcome is unknown.

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
