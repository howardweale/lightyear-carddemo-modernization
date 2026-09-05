# CloudBank real non-production platform qualification

MS #67 turns the MS #65 deployment design into an executable real-platform qualification gate.
The first platform implementation is an ephemeral regional Google Kubernetes Engine environment.
It uses three zones, private nodes, Workload Identity Federation for GKE, Artifact Registry,
Secret Manager through External Secrets Operator, Cloud SQL for PostgreSQL, Cloud DNS, a public
trusted TLS endpoint, Managed Service for Prometheus, Cloud Logging, and Cloud Trace.

The committed readiness receipt is intentionally fail-closed. It says the contracts and harness are
ready; it does not claim a cluster exists or that any live drill passed. A passing receipt requires
signed MS #65 and MS #66 execution receipts plus a signed observation from one explicitly named,
authorized, non-production platform.

## Live sequence

1. Copy `gke/qualification.env.example` outside the repository and supply the project, region,
   delegated test domain and digest-pinned Java and model images. Cluster administration uses the
   IAM-authenticated GKE DNS endpoint rather than a source-IP allowlist.
2. Run `gke/bootstrap.sh` from Google Cloud Shell. It creates chargeable resources and prints the
   DNS delegation that must be installed at the parent zone.
3. Add secret versions directly to Secret Manager. Never put secret values in this repository,
   shell history, an observation, or a receipt.
   If the signed MS #54 through MS #64 execution chain is no longer available, store one generated
   evidence key in Secret Manager and run `gke/submit-prerequisite-chain.sh SIGNER`. The asynchronous
   Cloud Build job recreates the complete chain and exports only the 12 signed prerequisite receipts
   plus their signed chain manifest to a private, versioned evidence bucket.
4. Materialize the MS #64 target, run `gke/build-push-images.sh`, and render the exact MS #65 bundle.
5. Run `gke/deploy.sh` to install External Secrets, deploy all eight digest-pinned services, add
   TLS/ingress and telemetry resources, and wait for readiness.
6. Follow `gke/LIVE-RUNBOOK.md`. The site harness must hash and sign its minimized observation
   according to `platform-observation.schema.json`.
7. Run `./cloudbank-platform-qualification.sh admit ...` and independently verify the receipt.
8. Export only the signed minimized evidence, then run `gke/destroy.sh` after a second explicit
   acknowledgement. Destruction is intentionally separate and never automatic.

The GKE assets are an implementation profile, not evidence that this workspace contacted Google
Cloud. Customer IdP integration, representative customer volumes, the customer's formal approval
process, production deployment, and final production readiness remain for MS #68.

## Recover an existing telemetry collector

The collector's Google Cloud exporter receives `GCP_PROJECT_ID` explicitly. Its network policy
allows the Dataplane V2 metadata endpoint `169.254.169.254/32` on TCP 80 and 8080 for Workload
Identity credentials, alongside DNS and the restricted Google API VIP. These metadata ports follow
[the GKE network policy requirements](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/network-policy#network_policy_and_workload_identity_federation_for_gke).
The collector keeps its existing Kubernetes service account and bootstrap IAM grants.

After loading the qualification environment and non-production acknowledgement, run:

```bash
bash factory/cloudbank/platform-qualification/gke/repair-telemetry.sh \
  "$(mktemp -d "$HOME/ms67-evidence/ms67-telemetry.XXXXXX")"
```

This helper verifies the cluster uses Dataplane V2, renders and applies only the seven
observability resources, reports progress every 20 seconds while waiting, and requires two ready,
updated collector replicas. The pod configuration hash triggers a rollout when the collector
configuration changes. Startup, readiness, and liveness probes use its internal health extension.
The regular deployment script also waits for collector readiness before applying the services.

The helper saves configuration, checksums, and a small status record locally and under
`gs://PROJECT-ms67-evidence/telemetry-recovery/`. A failed render or rollout is recorded as a failure.
It does not modify application images, Cloud SQL, External Secrets, TLS, or the model deployment.
Collector readiness does not establish Cloud Monitoring or Cloud Trace delivery; those checks and
the remaining signed qualification gates still require live observations.
