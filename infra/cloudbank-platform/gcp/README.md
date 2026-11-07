# CloudBank infrastructure — offline implementation

Not yet applied or live-qualified. Terraform and Google provider versions and
the provider lock file match `infra/cloud-runner/gcp`. Only CI executes format,
schema validation and `command = plan` tests with `mock_provider "google"`.
Mock success is not evidence that Google accepted or ran these resources.

## Ownership split

Terraform declares the bootstrap cloud resources: enabled APIs, VPC/subnet and
secondary ranges, router/NAT, private service access, regional three-zone GKE
with private nodes/DNS-only control plane/Dataplane V2/Workload Identity,
Artifact Registry, private regional PostgreSQL with backup/PITR, private and
delegated public DNS, ingress address, eight empty Secret Manager containers,
secret-reader Workload Identity IAM and telemetry IAM/APIs/managed Prometheus.
The bootstrap image-signing KMS key remains P-256 for image compatibility. It
is NOT a platform-receipt signer. New platform receipts require Ed25519 only.
No secret versions, service-account private keys or receipt signing keys exist
in this module. GKE's bootstrap node-service-account default is preserved;
review its existing IAM before any live adoption, rather than granting Editor.

Existing bootstrap Kubernetes namespace/security labels, service account and
pinned Helm releases (External Secrets, cert-manager, ingress) remain an
operator-controlled add-on boundary. Application/observability/model manifests,
NetworkPolicy default-deny and bounded allow rules, service rollout and the
ExternalSecret refresh policy remain owned by the unchanged `deploy.sh` and
its renderers. Terraform supplies cloud prerequisites and hashes the retained
add-ons template; it does not apply or silently take over Kubernetes objects.
No model is run by this module or its workflow.

Do not run the entire legacy bootstrap after Terraform adoption: it still owns
the same cloud names. A separately approved adoption packet must inventory and
import existing cloud resources, compare a real reviewed plan, then execute only
the existing add-on portion. No adoption or apply is authorized by this draft.

## Parity and evidence limits

The static parity checker enumerates every bootstrap cloud mutation, compares
Terraform resource families/counts and API/service instances, and rejects any
bootstrap/common source change until reconciliation. The mock plan checks the
critical settings. The exact source binding is intentionally stricter than
resource names alone; a shell flag change also fails. Helm/Kubernetes objects
are excluded from CLOUD parity only, with their ownership stated above.
Cloud SQL/GKE deletion protection is explicit; KMS destruction is prevented.
This is not a destroy script or a claim that all resources are disposable.

`platform_infrastructure` exposes declared resource attributes for plan-derived
drill expectations. It always reports `live_drills = "NOT RUN"` and never claims
qualification. A future live packet needs exact source/plan digest, credentials
held by Howard, cost ceiling, expiry, resource import/ownership inventory and a
destroy/retention plan covering SQL backups, KMS, DNS delegation, NAT/IPs,
registry images and secret containers. That packet needs separate approval.

Provider documentation: https://registry.terraform.io/providers/hashicorp/google/8.6.0/docs/resources/container_cluster
Mock semantics: https://developer.hashicorp.com/terraform/language/tests/mocking
