# CreditScore secret rotation

`cloudbank-secret-rotation.sh` produces bounded evidence for MS67's
`external-secret-rotation-propagated` scenario. It uses the already deployed
images and existing signed MS64 receipt and MS67 platform profile. No application
rebuild, prerequisite regeneration, MS65 rehearsal or MS66 rerun is needed.

The runner checks all eight locked deployments and ExternalSecret readiness,
then rotates **only** `CLOUDBANK_CREDITSCORE_SYNTHETIC_PEPPER` inside the provider
secret `cloudbank-creditscore-external`. The synthetic marker is preserved. It
authenticates as the existing CreditScore OAuth client and checks each owned
replica separately against the application's subject/date HMAC scoring contract.
Pod readiness and the presence of an unused marker cannot pass this drill.

The operator needs the existing Kubernetes read and port-forward permissions,
patch access to the CreditScore Deployment and ExternalSecret, get/create/patch
access to coordination Leases, Secret Manager access to the evidence key,
CreditScore and authorization-server secrets, add/list/get/disable version
permissions for CreditScore, and object read/create/update access to the private
evidence prefix. This runner does not grant IAM roles.

## Run

Supply durable local paths for the three already approved inputs. From Cloud
Shell, use the active account explicitly and acquire the configured context:

```bash
export CLOUDSDK_CORE_ACCOUNT="${MS67_SIGNER:?Set MS67_SIGNER to the authenticated operator account}"
export CLOUDSDK_CORE_PROJECT="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
gcloud container clusters get-credentials "$GKE_CLUSTER_NAME" --region "$GCP_REGION"

bash ./cloudbank-secret-rotation.sh preflight \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --cluster "$GKE_CLUSTER_NAME" --namespace "$GKE_NAMESPACE" \
  --image-lock "$MS67_IMAGE_LOCK" --ms64-receipt "$MS67_MS64_RECEIPT" \
  --platform-profile "$MS67_PLATFORM_PROFILE" \
  --evidence-bucket "gs://${GCP_PROJECT_ID}-ms67-evidence/secret-rotation" \
  --signer "$MS67_SIGNER"
```

After preflight passes, use the same arguments with `run` and
`LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS`. A typical
Cloud Shell launch is:

```bash
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
MS67_SECRET_LOG="$HOME/ms67-evidence/secret-rotation-$(date -u +%Y%m%dT%H%M%SZ).log"
nohup bash ./cloudbank-secret-rotation.sh run \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --cluster "$GKE_CLUSTER_NAME" --namespace "$GKE_NAMESPACE" \
  --image-lock "$MS67_IMAGE_LOCK" --ms64-receipt "$MS67_MS64_RECEIPT" \
  --platform-profile "$MS67_PLATFORM_PROFILE" \
  --evidence-bucket "gs://${GCP_PROJECT_ID}-ms67-evidence/secret-rotation" \
  --signer "$MS67_SIGNER" >"$MS67_SECRET_LOG" 2>&1 < /dev/null &
printf 'MS67_SECRET_PID=%s\nMS67_SECRET_LOG=%s\n' "$!" "$MS67_SECRET_LOG"
```

`nohup` survives a terminal disconnect, not loss of the Cloud Shell VM. The log
prints the local evidence directory and the private `MS67_SECRET_ROTATION_RECOVERY_STATE`
URI before mutation. Every checkpoint is signed, uploaded with a generation
precondition and independently read back before the next mutation. Secret
values, OAuth credentials, tokens, raw scores and response bodies are never
written to evidence. Provider version numbers, hashes and pod identities are
retained. Secret Manager payloads are passed to `gcloud` via stdin.

## Rotation and restoration

1. Acquire the fixed CreditScore rotation Lease. An active holder is never
   automatically expired or stolen by a new run.
2. Pin the existing ExternalSecret extraction to the original **numeric**
   provider version before adding a new one. This protects propagation against
   a lost `addVersion` response.
3. Add a cryptographically random pepper, pin that version, observe exact Secret
   synchronization and roll CreditScore with its existing zero-unavailable
   strategy. Check the authenticated score from **both new pods**, requiring
   a different result from the original pepper on the same UTC date.
4. Restore the original complete JSON payload and scoring behavior, retain it
   as a new enabled provider version, restore the exact original extraction
   version policy and remove the runner's pod-template annotation. Verify both
   restored pods. Disable only the temporary version created by this run using
   its provider ETag. Leave all pre-existing versions as found.
5. Release the owned Lease and sign/upload/read back the observation.

This is a reversible propagation drill, including retirement of its temporary
version. It does not claim permanent production credential replacement or full
MS67 completion. The original pepper remains recoverable in its prior version.
Avoid concurrent deployment, secret or other disruptive qualification work in
this namespace while the drill runs.

## Recover after a lost process

Stop or confirm exit of the original process first. Obtain the recovery URI
from its log, or from the Lease's nonsecret `lightyear.ai/recovery-state`
annotation. Download that state and run:

```bash
gcloud storage cp "$MS67_SECRET_RECOVERY_URI" "$HOME/ms67-evidence/secret-rotation-recovery.json"
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
bash ./cloudbank-secret-rotation.sh recover \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --cluster "$GKE_CLUSTER_NAME" --namespace "$GKE_NAMESPACE" \
  --recovery-state "$HOME/ms67-evidence/secret-rotation-recovery.json" \
  --evidence-bucket "gs://${GCP_PROJECT_ID}-ms67-evidence/secret-rotation" \
  --signer "$MS67_SIGNER"
```

Recovery loads the latest signed checkpoint from its original URI and fences
old writers using object generations and the Lease executor identity. It only
restores; it cannot resume the qualification or award a passing drill result.
Completed cleanup is checked without repeating the rotation.

If `addVersion` was interrupted, recovery looks for one positively identified
version matching the recorded intent. It does not retry an ambiguous creation.
If the outcome remains unknown, original behavior is restored under a numeric
pin, the Lease stays held, and the result remains `recovery-required`. Inspect
the provider version metadata and retry recovery after the operation is resolved.
Changed resource UIDs, unrelated configuration, another operator's version or
an invalid signature also block cleanup rather than overwriting that state.
Do not remove the Lease or edit/sign a recovery record to bypass those checks.

## Verify evidence

Only `passed-secret-rotation-and-restoration` with two fresh replicas for both
the changed and restored scoring contract is eligible. Independently verify the
downloaded observation with:

```bash
bash ./cloudbank-secret-rotation.sh verify \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --cluster "$GKE_CLUSTER_NAME" --namespace "$GKE_NAMESPACE" \
  --observation "$MS67_SECRET_ROTATION_ROOT/secret-rotation.observation.json" \
  --evidence-bucket "gs://${GCP_PROJECT_ID}-ms67-evidence/secret-rotation" \
  --signer "$MS67_SIGNER"
```

Retain the observation alongside the TLS and operational evidence for eventual
MS67 admission. The prior independently verified MS65 and MS66 results remain
valid; this helper does not reopen them.
