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
   delegated test domain, administrator CIDR, and digest-pinned Java base image.
2. Run `gke/bootstrap.sh` from Google Cloud Shell. It creates chargeable resources and prints the
   DNS delegation that must be installed at the parent zone.
3. Add secret versions directly to Secret Manager. Never put secret values in this repository,
   shell history, an observation, or a receipt.
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
