# MS #67 GKE live qualification runbook

This runbook creates real, chargeable, non-production effects. Use a dedicated project labelled
`environment=non-production`. Keep the evidence key and every secret outside the repository. The
scripts use an IAM-authenticated GKE DNS endpoint and refuse mutable base-image tags, production-labelled projects,
missing chart versions, and missing mutation acknowledgements.

## 1. Account and DNS

- Confirm billing, quota, and the exact project with `gcloud config get-value project`.
- Confirm the active principal with `gcloud auth list`.
- Copy `qualification.env.example` outside the repository and source it.
- Run `bootstrap.sh`. Delegate the printed Cloud DNS name servers from the parent DNS zone.
- Add one JSON secret version to each of the eight Secret Manager containers. Use only synthetic
  credentials and configuration. Do not pipe values through shell command-line arguments.
- If the operator-held MS #54 through MS #64 execution receipts are unavailable, create one
  Secret Manager value named `cloudbank-ms67-evidence-key` and run
  `submit-prerequisite-chain.sh SIGNER`. The asynchronous Cloud Build job executes the complete
  signed dependency chain and exports only minimized receipts to the private evidence bucket.
  Do not substitute committed readiness receipts for these execution receipts.

## 2. Build and deploy

- Retain the signed MS #61 and MS #64 prerequisite receipts; MS #65 and MS #66 live execution
  follows deployment and uses the same evidence key.
- Materialize the exact MS #64 eight-service target into a fresh directory.
- Run `render-site-inputs.sh`, then `build-push-images.sh`, then `deploy.sh`.
- Sign every digest with the configured Cloud KMS key and attach a content-addressed provenance
  predicate. Verify both before continuing. Record only result hashes and aggregate counts.
- Confirm all 16 service Pods are ready and every running image ID equals the image lock.

The deployment supplies the same PostgreSQL dialect override used by the native qualification
lane, above the imported Oracle defaults. Account and Transfer use the `cloudbank-oauth` profile;
Authorization disables sample human-user
bootstrapping for this client-credentials lane. OAuth client secrets and the persistent signing key
remain in External Secrets; this setting does not provision or qualify customer human-user login.

Checks and Transfer explicitly set `CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED=true` in their
deployment environment. The imported common configuration otherwise defaults it to false, which
prevents Checks' `AccountService` from receiving its required `CloudBankServiceTokenProvider`.
The Checks deployment context regression runs the actual configuration import and verifies both
the missing-provider failure and successful startup with this override. It isolates database I/O
and scheduling; it does not establish live token exchange or queue processing. This deployment
correction can reuse the existing signed images and MS64 receipt.

Kubernetes health probes remain HTTP liveness/readiness checks on the application port. If probes
return 401, rebuild from the corrected MS64 target rather than changing probes to TCP or exposing
all actuator endpoints. Refresh the MS64 receipt and image lock after application patch changes.

## 3. TLS, secrets, and telemetry

The GKE add-ons include `cloudbank-acme-http01-ingress`. MS65's namespace-wide default deny
also selects cert-manager's temporary HTTP-01 solver pods, which do not carry the CloudBank
application labels. This policy permits TCP 8089 only from the `ingress-nginx` controller pods
in the `ingress-nginx` namespace to pods labelled `acme.cert-manager.io/http01-solver=true`.
Both source selectors apply together; application isolation, solver egress isolation and the
application HTTPS redirect remain in force. The rule also covers subsequent certificate renewals.

If the issuer is Ready but a Challenge remains pending with a self-check timeout, inspect its
Reason, the solver pod readiness, this policy and the ingress controller labels. Confirm public
DNS resolves to the ingress address and test the exact challenge URL externally. A timeout alone
does not distinguish missing network access from DNS, ingress or load-balancer issues. Apply the
corrected policy to an existing deployment without rebuilding images or deleting the Certificate,
Order or Secret; cert-manager retries a pending self-check. Observe Certificate Ready and externally
verify trust and hostname before recording TLS success. Keep the applied policy and resulting
bounded certificate status with the deployment evidence.

- Use OpenSSL and curl from an external network to prove certificate trust, SAN equality, at least
  30 days remaining, TLS 1.2 or newer, and HTTP rejection or redirect to HTTPS.
- Confirm all ExternalSecret resources are Ready. Add a new Secret Manager version for one bounded
  synthetic value, wait for propagation, restart its workload, prove the new version is active, and
  disable the prior version. Record no value.
- Confirm Managed Prometheus metrics, Cloud Logging entries, and Cloud Trace spans for all eight
  services under one hashed correlation ID. Trigger one synthetic alert and prove it recovers.

Before the correlation and alert exercise, collect a reproducible read-only delivery baseline. The
operator needs Logs Viewer, Monitoring Viewer, and Cloud Trace User access; collector write roles do
not grant human read access. Run it immediately after fresh journey traffic so logs and traces fall
inside the selected window:

```bash
./cloudbank-operational-baseline.sh \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --cluster "$GKE_CLUSTER_NAME" \
  --namespace "$GKE_NAMESPACE" --lookback-minutes 60 \
  --evidence-bucket "gs://${GCP_PROJECT_ID}-ms67-evidence/operational-baseline"
```

The observer reads only resource identities, timestamps, metric headers and span labels. It hashes
entry and trace identities, retains structured API error identifiers without free-text messages,
and uploads the bounded observation outside the checkout. `OBSERVED-ALL-BASELINE-SIGNALS` means
delivery was seen; it does not prove correlation, alert behavior, rotation, MS65, MS66 or MS67.

## 4. Load and security

- Run the same 18 MS #66 business journeys through k6 for at least 300 seconds, 1,000 requests and
  concurrency 10. The gate requires zero errors and p95 latency no greater than 500 ms.
- Verify all eight image signatures and provenance statements with Cosign.
- Scan every digest with Trivy. The gate permits zero critical and zero high findings.
- Scan the rendered manifests and the live cluster configuration; prove zero critical/high findings,
  zero runtime policy violations, default deny, bounded PostgreSQL egress, and Chatbot-only model
  egress.

## 5. Backup, HA, rollout, cutover, and rollback

- Create an on-demand Cloud SQL backup and verify it. Restore/clone it into an isolated validation
  instance, run the normalized state query, and require the restored hash to equal the pre-backup
  hash. RPO must be at most 60 seconds and RTO at most 600 seconds.
- Cordon and drain one worker node, verify all eight services and business journeys, then uncordon.
  Repeat for all nodes in one failure domain. This is a controlled evacuation test, not a claim that
  Google Cloud suffered a zone outage. Require zero normalized data loss.
- Roll all eight services from baseline to separately signed candidate digests. Observe
  `maximumUnavailable=0` for every rollout and run the journeys during the change.
- Put one candidate behind the bounded canary path, then switch 100% target traffic, run all 18
  journeys, invoke the documented rollback trigger, restore the prior release, and rerun recovery.
- Complete all 28 scenario rows in a `platform-qualification-observation.schema.json` document, hash every source
  evidence item, sign the minimized observation, and admit it with the MS #67 launcher.

## 6. Evidence and teardown

- Independently run `verify-receipt` before removing infrastructure.
- Retain only signed profiles, observations, receipts, contracts, aggregate scan counts, and hashes.
- Set `LIGHTYEAR_MS67_DESTROY_ACK=DESTROY-CLOUDBANK-MS67-NON-PRODUCTION` and run `destroy.sh`.
- Verify billing-visible resources. KMS and service-networking remnants may require later manual
  cleanup; the destroy script reports this rather than claiming the project is empty.

Customer IdP integration, representative customer data volume, customer workload, the customer's
formal approval process, production deployment, and final production readiness remain MS #68.

## Shared business journey executor

After deployment and the read-only operational baseline are ready, use the
[shared journey runner](../../shared-journeys/README.md). Start with
`cloudbank-journeys.sh preflight`; it checks all eight live image identities and
five OAuth roles. The subsequent run exercises actual business state and process
recovery with signed bounded evidence. It does not replace the MS65/MS66 receipt
requirements or the remaining MS67 operational scenarios.

For an execution host that may disconnect, use `submit-shared-journeys.sh` as
documented by the shared journey runner. It launches the same fail-closed executor
as an asynchronous Cloud Build using a pinned source commit and private,
content-addressed inputs. Do not run the Cloud Shell and Cloud Build launchers at
the same time; the submission script refuses another tagged active build.

### Durable MS65 rehearsal

After the shared journey build passes all 18 scenarios and the isolated Cloud SQL
recovery drill passes, admit those separately signed observations into a live MS65
rehearsal. This executor does not infer business or recovery success from Pod
readiness. It verifies both prior signatures and requires the same environment and
eight-image binding. It then checks all eight deployed controls, creates one
isolated CreditScore canary from the locked digest, switches only the CreditScore
Service selector, runs a 60-second/100-request credit-contract SLO window, restores
the original selector, deletes the owned canary, and invokes the existing MS65
admission controller against the pinned CloudBank source.

Download the successful journey observation if it is not already local, and use
the `database-recovery.json` from the passing isolated recovery root. The journey
file must be the exact signed observation named by that recovery receipt. Confirm
the content hashes before submission:

```bash
BUILD_ID=REPLACE_WITH_SUCCESSFUL_SHARED_JOURNEY_BUILD
MS65_JOURNEYS="$HOME/ms67-evidence/shared-journeys-$BUILD_ID.json"
gcloud storage cp \
  "gs://${GCP_PROJECT_ID}-ms67-evidence/shared-journeys/ms67-journeys-$BUILD_ID/journeys.json" \
  "$MS65_JOURNEYS"
jq -e --arg journey "$(jq -r .content_sha256 "$MS65_JOURNEYS")" \
  '.bindings.journeys_content_sha256 == $journey' \
  "$MS67_SQL_RECOVERY_ROOT/database-recovery.json"

export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
bash factory/cloudbank/platform-qualification/gke/submit-ms65-rehearsal.sh \
  "$MS67_IMAGE_LOCK" \
  "$MS67_MS64_RECEIPT" \
  "$MS67_SITE_INPUTS/ms65-environment.json" \
  "$MS65_JOURNEYS" \
  "$MS67_SQL_RECOVERY_ROOT/database-recovery.json"
```

The launcher requires local, bounded JSON inputs so it can hash and upload an exact
content-addressed set, and a clean `main` checkout tracking `origin/main`. It runs
asynchronously and prints `MS65_REHEARSAL_BUILD_ID`. Cloud Shell disconnects do
not stop the build. Follow it with:

```bash
gcloud beta builds log --stream "$MS65_REHEARSAL_BUILD_ID" \
  --region "$GCP_REGION" --project "$GCP_PROJECT_ID"

gcloud builds describe "$MS65_REHEARSAL_BUILD_ID" \
  --region "$GCP_REGION" --project "$GCP_PROJECT_ID" \
  --format='yaml(id,status,createTime,startTime,finishTime,failureInfo,logUrl)'
```

Only `status: SUCCESS` is eligible. Inspect the signed admitted receipt rather
than inferring completion from the final build step:

```bash
MS65_EVIDENCE_URI="gs://${GCP_PROJECT_ID}-ms67-evidence/ms65-rehearsal/ms65-rehearsal-${MS65_REHEARSAL_BUILD_ID}/"
gcloud storage ls "$MS65_EVIDENCE_URI"
gcloud storage cat "${MS65_EVIDENCE_URI}cloudbank-production-readiness.receipt.json" |
  jq '{receipt_type, rehearsal_status: .rehearsal.status,
       scenario_count: .rehearsal.scenario_count,
       production_like_rehearsal_complete, cutover_rehearsal_complete,
       rollback_rehearsal_complete, production_ready,
       whole_application_equivalent, migration_complete, signature}'
```

Before every mutation, `ms65-recovery-state.json` is signed and persisted under
the printed private evidence prefix. Normal failure handling restores the exact
recorded Service selector and deletes only the run-labelled canary. If the build
is forcibly terminated between checkpoints, download that state and recover with
the same explicit project, region, cluster and namespace:

```bash
RECOVERY_PREFIX="gs://${GCP_PROJECT_ID}-ms67-evidence/ms65-rehearsal/ms65-rehearsal-${MS65_REHEARSAL_BUILD_ID}"
MS65_RECOVERY_STATE="$HOME/ms67-evidence/ms65-recovery-${MS65_REHEARSAL_BUILD_ID}.json"
gcloud storage cp "$RECOVERY_PREFIX/ms65-recovery-state.json" "$MS65_RECOVERY_STATE"

export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
bash ./cloudbank-ms65-rehearsal.sh recover \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --cluster "$GKE_CLUSTER_NAME" \
  --namespace "$GKE_NAMESPACE" \
  --recovery-state "$MS65_RECOVERY_STATE" \
  --evidence-bucket "gs://${GCP_PROJECT_ID}-ms67-evidence/ms65-rehearsal-recovery" \
  --signer "${MS67_SIGNER:?Set MS67_SIGNER to the active operator identity}"
```

If selector restoration cannot be proved, recovery deliberately preserves the
canary rather than deleting the Service's possible remaining endpoints. Never
start another rehearsal while the selector or canary requires reconciliation.

The canary deliberately uses the same approved locked digest. This qualifies the
bounded deployment and traffic-control rehearsal, not a software-delta rollout.
The signed receipt can close MS65 only. It cannot establish the native Oracle lane,
MS66 equivalence, the remaining MS67 operational scenarios, or production readiness.

### Durable MS66 governed dual-lane execution

Run MS66 only after the deployed PostgreSQL target is healthy and the signed MS61 and MS64
prerequisites are available. The Oracle lane does not edit the pinned checkout. Cloud Build checks
the exact upstream commit and both Git tree identities, copies it to a fresh workspace, applies the
reviewed hardening patch by its SHA-256, compiles eight source images, and resolves every source,
Oracle Free, and MicroTx image to an immutable digest before creating a namespace. The isolated
namespace is labelled with the build run ID and is removed before the PostgreSQL lane begins.

The launcher also requires the immutable Java 21 base image already approved for the MS67 image
build. The default native runtime candidates use explicit tags; override either candidate only with
another explicitly reviewed, non-`latest` tag that the Cloud Build worker can read. Submit from a
clean `main` checkout matching `origin/main`:

```bash
set +e
set +u
set +o pipefail

cd "$HOME/lightyear-carddemo-modernization"
source "$HOME/ms67-qualification.env"

export MS67_MS61_RECEIPT="$HOME/ms67-evidence/prerequisite-chain-$PREREQUISITE_BUILD_ID/ms61-equivalence.receipt.json"
export MS67_MS64_RECEIPT="$HOME/ms67-evidence/prerequisite-chain-$PREREQUISITE_BUILD_ID/ms64-edge-ai.receipt.json"
export MS67_IMAGE_LOCK="$HOME/ms67-evidence/ms67-image-build/image-lock.json"
export MS67_POSTGRESQL_PROBE_IMAGE="REGISTRY/PROJECT/REPOSITORY/journey-probe@sha256:REPLACE"
export JAVA_BASE_IMAGE="REGISTRY/PROJECT/REPOSITORY/java21-patched@sha256:REPLACE"
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS

bash factory/cloudbank/platform-qualification/gke/submit-ms66-dual-lane.sh \
  "$MS67_MS61_RECEIPT" \
  "$MS67_MS64_RECEIPT" \
  "$MS67_IMAGE_LOCK" \
  "$MS67_POSTGRESQL_PROBE_IMAGE"
```

The submitter prints and saves `MS66_DUAL_LANE_BUILD_ID`; it refuses a second active tagged build.
The job is asynchronous, so a Cloud Shell disconnect does not terminate it. Reconnect and monitor
without relying on shell-session variables:

```bash
set +e
set +u
set +o pipefail

MS66_DUAL_LANE_BUILD_ID="$(sed -n '1p' "$HOME/ms66-dual-lane-build-id" 2>/dev/null)"
echo "MS66_DUAL_LANE_BUILD_ID=$MS66_DUAL_LANE_BUILD_ID"

gcloud builds describe "$MS66_DUAL_LANE_BUILD_ID" \
  --region us-west1 --project lightyear-ms67-nonproduction \
  --format='yaml(id,status,createTime,startTime,finishTime,steps.id,steps.status,failureInfo,logUrl)'

gcloud beta builds log --stream "$MS66_DUAL_LANE_BUILD_ID" \
  --region us-west1 --project lightyear-ms67-nonproduction
```

Only `status: SUCCESS` is eligible. Inspect and independently verify the signed MS66 receipt; build
success alone is not the qualification claim:

```bash
set +e
set +u
set +o pipefail

MS66_EVIDENCE_URI="gs://${GCP_PROJECT_ID}-ms67-evidence/ms66-dual-lane/ms66-${MS66_DUAL_LANE_BUILD_ID}"
MS66_RECEIPT="$HOME/ms67-evidence/ms66-receipt-${MS66_DUAL_LANE_BUILD_ID}.json"
gcloud storage cp "$MS66_EVIDENCE_URI/cloudbank-whole-application-equivalence.receipt.json" \
  "$MS66_RECEIPT" --project "$GCP_PROJECT_ID"

export LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY="$(gcloud secrets versions access latest \
  --secret cloudbank-ms67-evidence-key --project "$GCP_PROJECT_ID")"
./cloudbank-whole-application-equivalence.sh verify-receipt "$MS66_RECEIPT"
unset LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY

jq '{receipt_type,status,scenario_count,all_eight_services_observed_in_both_lanes,
     bounded_whole_application_equivalent,whole_application_equivalent,
     exact_internal_implementation_equivalent,oracle_source_image_lock_sha256,
     postgresql_image_lock_sha256,oracle_hardening_patch_sha256,
     migration_complete,production_ready,signature}' "$MS66_RECEIPT"
```

The workflow uploads a signed isolated `recovery-state.json` before every namespace or model-policy
mutation and a signed `postgresql-recovery-state.json` before every target scale or delivery-route
mutation. Normal error handling restores both lanes. If a build is forcibly cancelled or loses its
worker, download whichever state still records active work and submit the durable recovery job:

```bash
set +e
set +u
set +o pipefail

MS66_EVIDENCE_URI="gs://${GCP_PROJECT_ID}-ms67-evidence/ms66-dual-lane/ms66-${MS66_DUAL_LANE_BUILD_ID}"
MS66_RECOVERY_STATE="$HOME/ms67-evidence/ms66-recovery-state-${MS66_DUAL_LANE_BUILD_ID}.json"

gcloud storage cp "$MS66_EVIDENCE_URI/recovery-state.json" "$MS66_RECOVERY_STATE" \
  --project "$GCP_PROJECT_ID"
jq '{state_type,run_id,phase,cleanup_required,namespace,namespace_uid,
     model_namespace,model_policy_name,model_policy_uid}' "$MS66_RECOVERY_STATE"

export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
bash factory/cloudbank/platform-qualification/gke/submit-ms66-recovery.sh \
  "$MS66_RECOVERY_STATE"
```

If that isolated state says `cleanup_required: false`, it is already restored. If the failure
occurred in the PostgreSQL lane, download `postgresql-recovery-state.json` instead and pass it to
the same submitter. The recovery job verifies the state signature and refuses to delete or alter a
resource whose recorded UID, immutable image, run ID, or ownership labels no longer match. Resolve
identity drift manually; never bypass that refusal with an unscoped namespace deletion.

A passing MS66 receipt establishes only the declared bounded whole-application equivalence between
the governed Oracle source materialization and the exact MS64 PostgreSQL target. It explicitly keeps
unchanged-upstream identity, migration completion, production deployment, and production readiness
false.

### Isolated database recovery executor

See [SQL-RECOVERY.md](SQL-RECOVERY.md) for the signed Cloud SQL backup/PITR drill,
its recover command, and the limits of its database-only timing observations.

### Cloud SQL HA and application reconnection

See [SQL-HA.md](SQL-HA.md) for a separate controlled standby failover drill. Start
with `cloudbank-sql-ha.sh preflight`; the authorized run keeps applications running,
checks all 16 process identities and acknowledged business data, and measures
reconnection through new transactions. It does not close the PITR timing gate or
the GKE node/failure-domain, MS65/MS66 prerequisite, or full MS67 gates.
