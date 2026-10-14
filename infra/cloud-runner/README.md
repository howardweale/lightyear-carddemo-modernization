# Cloud runner — Phase 1

**Status: implementation for offline review, not a deployed runner.** Google Cloud
is the primary design. AWS remains a later, once-per-release reproduction target.
No project, billing link, bucket, retention lock, key, VM or image has been created.
The B06 merge hold and its separate go process remain in force.

The October 13 proposal's checked decision boxes are design context, not evidence
of a selected billing account or authorization to spend $200. The proposed
`us-west1` region and 365-day retention are defaults for review. Phase 2 requires
a named project/customer account, budget approval, irreversible-lock approval and
a deployment review. Billing alerts are not a hard spending cap.

## What is implemented

| Component | Phase 1 implementation | Execution boundary |
| --- | --- | --- |
| Admission | Exact commit, request seal, attempt, window, project, object generation, image ID/build record, digest-pinned containers and independently signed cloud memory witness | Produces a plan only |
| Signer | Injected GCP KMS REST transport; numeric key version; PureEdDSA raw bytes; request/response CRC32C and local signature verification | No credentials, operational keys or network client are loaded by the module |
| Infrastructure | GCP storage, scope-separated worker identities, nine KMS keys, restricted WIF, private network and Google API DNS | Terraform requires explicit Phase 2 acknowledgement; no VM resource or VM-create/signing grant |
| Image | Packer recipe, verified offline JDK 21/Docker/Python dependencies and wheelhouse, base image ID check | Build script is for a separately approved cloud builder, not this laptop |
| Launcher | Manual GitHub workflow, protected-environment policy hash, offline signed-go admission, retained public plan | No OIDC permission, cloud authentication, apply, build, create or sign operation |
| Cleanup | Complete paginated VM/disk inventory and successful delete-operation contract | Provider observation, not independent attestation |
| Tests | Tampering, scope confusion, mutable references, resource floors, incomplete cleanup, image payload integrity, mocked infrastructure plans | Ephemeral fixture keys and no cloud APIs |

The existing Tower is not changed. A cloud request uses a new, versioned envelope
with `body`, `content_sha256` and `signature`; it shares Tower canonical JSON
and Ed25519 conventions but is **not** a drop-in replacement for existing B06
authorization formats. No existing request, key pin or laptop witness migrates
implicitly.

## Repository map

- `src/lightyear_cloud_runner/`: admission, signing, cleanup contract and plan-only CLI.
- `gcp/`: Terraform 1.13.3 / Google provider 8.6.0 with committed provider checksums.
- `image/`: Packer 1.14.2 / googlecompute 1.2.7; no floating base image family.
- `tools/check_cloud_image_bundle.py`: exact, complete offline bundle verification.
- `.github/workflows/cloud-runner-offline.yml`: no-cloud CI, including Terraform mock provider tests.
- `.github/workflows/cloud-runner-launch.yml`: manual admission planning only.
- `docs/cloud-runner-design.md`: lifecycle, trust boundaries and activation checklist.

## Offline verification

From the repository root, in an existing Python environment with cryptography
and PyYAML:

```sh
PYTHONPATH=src:.:tests python -B -m unittest test_cloud_runner test_cloud_image_bundle test_cloud_runner_workflows -v
terraform -chdir=infra/cloud-runner/gcp fmt -check -recursive
terraform -chdir=infra/cloud-runner/gcp init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/cloud-runner/gcp validate
terraform -chdir=infra/cloud-runner/gcp test
packer fmt -check -recursive infra/cloud-runner/image
packer validate -syntax-only infra/cloud-runner/image/runner.pkr.hcl
```

Terraform init downloads the provider but does not contact a cloud account.
`terraform test` uses `mock_provider "google"`; no real apply is tested or permitted.
Do not replace the mock with live credentials. Local Windows Application Control
blocked provider execution during development; Linux CI supplies schema/mock
validation. No machine policy was changed.

## Admission bundle and trusted policy

The dispatch input is JSON with exactly `request`, `go`, and `witness`.
It contains public metadata and signatures, never source assets or credentials.
Private request metadata must use a future customer-account ingress instead of
GitHub dispatch. Protect the `cloud-runner-admission` environment with Howard as
reviewer and branch restrictions before using dispatch. Its public
`CLOUD_RUNNER_POLICY_JSON` and exact file-byte `CLOUD_RUNNER_POLICY_SHA256` must
be established independently of the submitted bundle.

The policy names project, input bucket, region/zones, reviewed image identities,
machine types, commits, maximum duration, memory/disk floors and witness age.
It contains six distinct public PEMs: go and witness authorities for each of
engineering, qualification and factory. Terraform creates a third, separate
ledger key per scope for later cleanup countersigning. No worker or launcher has
permission to sign with any key. Phase 2 must separately approve the authenticated
operator signer, witness verifier and cleanup controller grants. The signer adapter
does not decide who is allowed to approve a run.

A request's inputs and witness each use
`{bucket, name: "sha256/<hash>", generation: "<numeric>", sha256, size}`.
The witness object bytes are canonical JSON of its signed envelope, without an
extra newline. Its signature binds provider `gcp`, project, region, image,
machine type, observation time, free memory and free disk. It cannot be replaced
with a laptop witness. The go signs the complete request hash plus scope, attempt,
commit and UTC window. Minimum free-memory/free-disk policy is operator-owned;
the Phase 1 tests use 30/60 GiB, not a measured cloud result.

Use the tests' generated fixtures to study the complete structures. Fixture keys
are never admitted as production trust. A successful plan includes
`execution_enabled: false`, the policy hash, and a proposed create-only attempt
claim. Producing a plan neither consumes an attempt nor proves that its cloud
objects or retention policy exist.

## Image supply chain

Prepare an approved base Ubuntu image with Python 3 available, identified by exact
project/name and numeric image ID. Supply a reviewed directory containing:
`jdk21.tar.gz`, `docker-static.tgz`, `requirements.lock`, all needed `debs/`
and a `wheels/` wheelhouse. Pin every file in `manifest.json`:

```json
{"schema":"lightyear.image-bundle.v1","files":{"jdk21.tar.gz":"<sha256>","docker-static.tgz":"<sha256>","requirements.lock":"<sha256>","debs/<package>.deb":"<sha256>","wheels/<package>.whl":"<sha256>"}}
```

The manifest's own SHA-256 is an independently reviewed Packer variable.
Missing, extra, altered or symlinked files fail verification. Requirements use
exact versions and pip hashes; installation uses no index or live package update.
Select exact JDK 21, Docker and Python patch versions in that manifest during
stand-up rather than inventing unverified pins now. Capture version outputs,
all package hashes, the Packer manifest, output image numeric ID, source commit
and builder provenance in the image build record before registering an image.
A VM image ID is a provider identity, **not** a cryptographic digest of all disk
bytes. The request separately pins the reviewed build record hash.

The wrapper checks the base image ID against the Compute API before Packer
starts. Use a restricted builder service account/network with IAP SSH; no default
Compute service account. The sealed-run subnet intentionally denies ingress.
A build only bakes tools; it does not start Docker or a campaign. Boot agent
installation and full builder/live-image validation are Phase 2 integration work.

## Phase 2 prerequisites (not authorized or performed here)

1. Resolve project/account ownership, enabled APIs, region, quotas and billing.
   Review a cost model based on measured VM hours, image disks, retained bytes,
   object operations, logs and key versions. Do not use the proposal's unverified
   “under $1/hour” or “cents/month” estimates as a budget.
2. Review Terraform in a canary project. Use a remotely protected state backend
   with restricted access and recovery; no private state in Git. Explicitly approve
   retention locking after canary checks. Locking cannot be undone or shortened.
3. Register operator/witness/ledger trust and narrowly scoped service permissions.
   Keep go signing outside the launcher and worker. Add a protected deployment
   workflow using WIF; the current workflow intentionally cannot authenticate.
4. Build and inspect the pinned image. Test customer-account isolation, private
   Google API access, generation-bound downloads, digest-pinned offline container
   imports, scoped evidence uploads and heartbeat alerts. No public registry
   access from the sealed worker subnet; inputs include approved container bytes.
5. Implement and review the live controller/boot agent: atomic attempt claims,
   all object/retention checks, measured startup resources, hard deadline,
   heartbeat, crash recovery and complete teardown inventory. See design document.
6. Run explicitly approved unsealed twin/factory smoke campaigns, measure cost/time,
   then obtain a newly reviewed cloud memory witness.
7. Only then request a new sealed campaign go. AWS reproduction remains Phase 5;
   there is no AWS deployment module or live reproduction claim in this PR.

## Sources checked October 13, 2026

- [GCP algorithms](https://docs.cloud.google.com/kms/docs/algorithms): software Ed25519/PureEdDSA.
- [KMS signing REST](https://docs.cloud.google.com/kms/docs/reference/rest/v1/projects.locations.keyRings.cryptoKeys.cryptoKeyVersions/asymmetricSign): data/checksum and response validation fields.
- [GitHub WIF](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines): federated identity restrictions.
- [Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock): retained generations and irreversible lock.
- [Packer GCE builder](https://developer.hashicorp.com/packer/integrations/hashicorp/googlecompute/latest/components/builder/googlecompute): image and builder configuration.
- [AWS EdDSA announcement](https://aws.amazon.com/about-aws/whats-new/2025/11/aws-kms-edwards-curve-digital-signature-algorithm/): future signer portability; no AWS adapter exercised here.
