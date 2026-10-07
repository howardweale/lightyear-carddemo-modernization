# Dedicated Google Cloud VM for T-SQL M0

**Prepared, not executed.** Howard selected Google Cloud on October 7, 2026.
No VM, firewall, network, API enablement or IAM change has been performed by Codex.
The exact project/environment still needs Howard's approval before native work.

Use a new VM named `ly-tsql-m0`, Ubuntu 24.04 amd64, `e2-standard-4`
(4 vCPUs / 16 GiB), 128 GiB balanced persistent disk, in `us-central1-a`.
This capacity is a proposed starting point, not a measured throughput requirement.

SQL Server's Linux containers require Intel/AMD x86-64; ARM emulation is not a
supported qualification environment. The Apple Silicon Multipass VM used for
Verify should not be used for this SQL Server run.
[Microsoft platform guidance](https://learn.microsoft.com/en-us/sql/linux/install-upgrade/setup?view=sql-server-ver16)

## Cost before creation

Budget approximately **US$0.16–0.20 per running hour**, or **US$2–2.40 for a
12-hour setup window**, excluding tax, outbound transfer and extra storage.
This is a planning estimate, not a project-specific quote. Confirm the current
E2 price in your Google Cloud console before creating the VM.

The calculation uses approximately $0.134/hour for E2 compute, about
$0.01753/hour for 128 GiB balanced disk, and $0.005/hour for its ephemeral IPv4.
The current general-purpose CPU table could not be retrieved in this session;
the compute rate is an estimate, not a newly verified quote. The disk and IP
rates were verified on Google's pricing pages. Disk storage continues to cost
about **$12.80/month while stopped**. The ephemeral external IP is released when
the VM stops.

[Compute pricing](https://cloud.google.com/products/compute/pricing/general-purpose) ·
[Disk pricing](https://cloud.google.com/compute/disks-image-pricing) ·
[IPv4 pricing](https://cloud.google.com/vpc/network-pricing)

The VM below stops after 12 hours and retains its disk. It does not auto-delete.
A later native plan must finish, including cleanup, before the remaining VM
deadline. Starting it again establishes another 12-hour limit; this is not
permission to resume a failed qualification slot.

## Create once, in Google Cloud Shell

Open [Google Cloud Console](https://console.cloud.google.com/), select the intended
existing billed project, and open **Cloud Shell** (the terminal icon).
These are Bash commands for Cloud Shell, not Windows PowerShell or the B06 host.

First identify the project:

```bash
gcloud config get-value project
```

Do not continue with a blank or unintended project. The account needs permission
to enable Compute/IAP, create compute/network resources, use IAP tunnels and
perform OS Login with administrator access. The commands make no IAM grants and
make no organization-policy changes. If a permission check fails, preserve the
output and stop rather than broadening permissions.

Review the estimate above. Running the following creates billable resources:

```bash
set -euo pipefail
LY_PROJECT="$(gcloud config get-value project)"
[[ -n "$LY_PROJECT" && "$LY_PROJECT" != "(unset)" ]] || exit 1
printf 'Project: %s\n' "$LY_PROJECT"
read -r -p 'Type that exact project ID to confirm creation: ' LY_CONFIRM
[[ "$LY_CONFIRM" == "$LY_PROJECT" ]] || exit 1

gcloud services enable compute.googleapis.com iap.googleapis.com --project="$LY_PROJECT"

gcloud compute networks create ly-tsql-m0-net \
  --project="$LY_PROJECT" --subnet-mode=custom

gcloud compute networks subnets create ly-tsql-m0-subnet \
  --project="$LY_PROJECT" --network=ly-tsql-m0-net \
  --region=us-central1 --range=10.198.0.0/24

gcloud compute firewall-rules create ly-tsql-m0-iap-ssh \
  --project="$LY_PROJECT" --network=ly-tsql-m0-net \
  --direction=INGRESS --action=ALLOW --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 --target-tags=ly-tsql-m0

gcloud compute instances create ly-tsql-m0 \
  --project="$LY_PROJECT" --zone=us-central1-a \
  --machine-type=e2-standard-4 \
  --image-project=ubuntu-os-cloud --image-family=ubuntu-2404-lts-amd64 \
  --network=ly-tsql-m0-net --subnet=ly-tsql-m0-subnet \
  --boot-disk-size=128GB --boot-disk-type=pd-balanced \
  --no-boot-disk-auto-delete --no-service-account --no-scopes \
  --tags=ly-tsql-m0 --labels=purpose=tsql-m0,owner=howard \
  --metadata=enable-oslogin=TRUE,block-project-ssh-keys=TRUE \
  --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
  --max-run-duration=12h --instance-termination-action=STOP \
  --maintenance-policy=TERMINATE --no-restart-on-failure

gcloud compute instances describe ly-tsql-m0 \
  --project="$LY_PROJECT" --zone=us-central1-a \
  --format='yaml(name,id,zone,status,machineType,disks,scheduling,networkInterfaces)'
```

This is intentionally create-once. Existing names or any failure stop the script;
do not delete or replace an existing resource to force it through. No changes
are made to the default network. The dedicated network has only IAP SSH ingress.
An ephemeral external IP permits outbound package downloads; ports 1433, 5432
and other database ports are not opened to the internet. Later database
containers must bind host ports to loopback only.

The OS image family resolves during creation; retain the instance/disk
description and bind the resolved image and machine identity before qualification.
No native run is authorized merely by an image-family name.

## Connect and identify the new environment

```bash
gcloud compute ssh ly-tsql-m0 \
  --project="$LY_PROJECT" --zone=us-central1-a --tunnel-through-iap \
  --command='hostname; uname -m; id -un; cat /etc/os-release'
```

Expected: hostname `ly-tsql-m0`, architecture **x86_64**, Ubuntu **24.04**.
OS Login supplies the actual username; do not guess it or share a password/key.
Give Codex the project ID and this output, then confirm this VM is the approved
dedicated T-SQL environment. The agent still needs an authorized connection from
its execution environment; Cloud Shell login alone does not grant it access.

[Google IAP guidance](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding) ·
[OS image families](https://docs.cloud.google.com/compute/docs/images/os-details) ·
[VM creation and runtime limit](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/create)

## First build, after VM approval and code transfer

Transfer only the reviewed T-SQL worktree/package to the VM. Do not transfer
B05/B06 private evidence, frozen roots, keys, customer data or work/ms94.
This branch is still local; there is no published commit to clone yet. A reviewed
source bundle or an approved publication must precede these repository commands.

Inside the approved VM, install build prerequisites (no database/container run):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates git python3 python3-venv dotnet-sdk-8.0
dotnet --list-sdks
```

Then, from the transferred repository:

```bash
export TSQL_VM_APPROVED=yes
bash tools/tsql_scriptdom/build-linux.sh \
  "$PWD/work/tsql-build-$(date -u +%Y%m%dT%H%M%SZ)"
```

The build script refuses Windows/ARM, uses a fresh result directory, retains build
logs, creates a package lock and tests all 42 public T-SQL procedures through the
real ScriptDom bridge. It writes `report.json`; a failed parse/build remains a
failure. There are zero model calls and zero native pairs in this step.

Next: implement/connect the actual driver call/reset backends, freeze exact
engine image digests and driver versions, and test capture/replay against real
engines. The added capture queries and replay verifier are currently tested only
with mock connections and ephemeral unit-test signing keys. They do not complete
native adapter qualification, error mapping, coverage collection or M0.
