# MS71: CloudBank on Cloud SQL and AlloyDB

The eight application images and MS66 business comparator are shared. MS71 adds explicit managed
database identity and requires both Oracle → Cloud SQL and Oracle → AlloyDB comparisons to pass.
Read the [milestone scope](../../../docs/ms71-cloudbank-alloydb-second-target.md).

## Configure the two targets

Copy the two `*.profile.example.json` files and `campaign.example.json` into a local work directory.
Replace `your-project`, resource names, namespaces, model name, and the pinned probe image. Paths
inside the campaign file resolve relative to that file. The `databases` mapping must describe the
actual deployed application: `null` means that service has no direct datasource. Both target
profiles must use the same mapping and PostgreSQL major version.

Seal each edited profile. Profiles contain resource identifiers and database names, never passwords:

```bash
./cloudbank-ms71.sh seal-profile work/ms71/cloud-sql.input.json work/ms71/cloud-sql.profile.json
./cloudbank-ms71.sh seal-profile work/ms71/alloydb.input.json work/ms71/alloydb.profile.json
```

On Windows, use `./cloudbank-ms71.ps1` with the same arguments. The launchers use the repository's
Python 3.11+ runtime selector. Live commands also require authenticated `gcloud`, `kubectl`, and
the selected GKE context. Every cloud operation includes its project and every Kubernetes operation
includes its context; the active global gcloud project is not used as an implicit target.

The implemented AlloyDB connection mode is direct private PostgreSQL over TLS, using
`jdbc:postgresql://PRIVATE_IP:5432/DATABASE?sslmode=require`. The probe carries `PGSSLMODE=require`.
The managed instance is created with `ENCRYPTED_ONLY`. Localhost proxies and arbitrary JDBC options
are rejected by MS71's target profile checks. PostgreSQL database-image hashes in the MS61/MS64
prerequisites retain their historical meaning; managed resource identity is recorded separately.

## Provision and deploy

Set the existing nonproduction acknowledgement:

```bash
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
```

The provisioning command creates a separate admin credential in Secret Manager, then a private
AlloyDB cluster and regional primary. It validates the nonproduction project label and existing
resource identity before proceeding. It returns promptly while creation is underway; repeat the
same command until it reports `primary-ready`. The 2-vCPU instance is a chargeable cloud resource.
It does not enable the AlloyDB API implicitly; enable `alloydb.googleapis.com` in the selected project first.

```bash
./cloudbank-ms71.sh provision --profile work/ms71/alloydb.profile.json \
  --network cloudbank-ms67 --admin-secret cloudbank-ms71-alloydb-admin --cpu-count 2 --execute
```

Use the accepted target image lock to materialize a fresh AlloyDB namespace:

```bash
./cloudbank-ms71.sh deploy-target \
  --source-profile work/ms71/cloud-sql.profile.json \
  --target-profile work/ms71/alloydb.profile.json \
  --target-image-lock work/ms71/target-image-lock.json \
  --admin-secret cloudbank-ms71-alloydb-admin \
  --probe-image REGISTRY/POSTGRES_TOOLING@sha256:DIGEST \
  --output-root work/ms71/deployment --execute
```

This copies the bound service specifications, configuration, service accounts, disruption budgets,
and network rules from the synthetic Cloud SQL deployment. Database egress is replaced with the
AlloyDB address. New Secret Manager objects feed External Secrets in the isolated namespace;
database credentials are distinct, while the application OAuth/model contracts are retained.
Both Spring and Liquibase datasource settings point to AlloyDB. The namespace's secret-reader
receives access only to the eight new secrets, including direct Kubernetes workload identities.
The existing `cloudbank-model` namespace receives a narrowly selected Chatbot ingress rule.
The `observability` collector receives a scoped ingress rule, with telemetry attributed to MS71
and the new namespace.

A temporary, digest-pinned PostgreSQL pod takes a consistent `pg_dump` snapshot from the synthetic
source database and imports it over TLS into AlloyDB. The existing CloudBank deployment uses one
shared database with service-specific schemas/tables; this materializer rejects multiple database
names. The target services stay at zero replicas until initialization succeeds. Initialization
creates the application role, grants the admin membership for database ownership, and grants the
application role access to `public`, accounting for AlloyDB's managed-admin privilege boundary.
Replay refuses existing application tables; it never drops them. Empty `cloudbank_customer` and
`user_repo` schema cleanup uses no `CASCADE`. The import is one transaction. Temporary source/admin credentials and the transfer policy are removed
after the seed attempt. The eight services then start in dependency order with two replicas each.

`deploy-target --resume` checks the saved namespace UID, target profile, and database identity,
reuses existing application credentials, and resumes supported setup phases. It does not rotate
credentials or rebuild images. A partially populated target database requires inspection instead
of automatic overwrite. Provisioned AlloyDB, service secrets, namespace, and IAM bindings remain
available for the campaign; the command does not remove these durable target resources.

## Run the single milestone gate

Supply the signed MS61 and MS64 receipts, the signed governed Oracle source image lock, the target
image lock, and the two sealed profiles in the campaign input file. Existing source images can be
reused when their signed pinned-source and hardening contracts still validate. Their original build
commit and signer remain in the original lock. MS71 records the current clean, committed controller
separately and signs the new runtime evidence as the executing operator; original receipts are not
rewritten. The MS66-only execution path retains its existing same-controller/signer checks.

```bash
./cloudbank-ms71.sh preflight --inputs work/ms71/campaign.json
# Supply LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY through the existing secret mechanism.
./cloudbank-ms71.sh run --inputs work/ms71/campaign.json \
  --campaign-id ms71-YOUR_UNIQUE_RUN --output-root /path/outside/repos/ms71-evidence \
  --evidence-prefix gs://YOUR_EVIDENCE_BUCKET/ms71/YOUR_UNIQUE_RUN \
  --signer YOUR_OPERATOR_ID --execute
```

Use lowercase letters, digits, and hyphens for the campaign ID (the portion after `ms71-` has at
most 35 characters). Preflight reads both providers and the actual deployment configuration,
rejects shared database addresses/namespaces, and checks the probe's datasource. It does not prove
equivalence. Application and probe configuration is read from the actual namespace's Kubernetes
secrets, and auxiliary JDBC settings must resolve to the same database. Each comparison creates a separate temporary Oracle lane, executes the unchanged
18 scenarios, recovers it, and executes the same scenarios on its managed target.

The signed managed comparison envelope embeds both journey records and the unchanged comparator
receipt. The verifier reconstructs the comparator's lane observations from those journeys, checks
their hashes against the receipt, validates all eight image identities and scenario evidence hashes,
and verifies the managed database/profile bindings before and after execution. The SQL probe also
records its database, engine major version, and encrypted connection status.

`run --resume` retains completed comparisons only when the campaign, controller, prerequisites,
image locks, profiles, and current target configuration still match, and their GCS readback verifies.
Each new attempt uses a fresh directory and run ID. Interrupted attempts retain the existing MS66
Oracle and target recovery journals; the runner refuses unfinished mutations until recovery is complete. No failed result
or changed-input result can count toward the two-target gate.

Only after both comparisons and durable readbacks pass does the command emit:

```text
"MS71_COMPLETE": true
```

It publishes `ms71-alloydb-second-target.receipt.json`, embedding both verified comparison envelopes.
Check the complete receipt offline with `./cloudbank-ms71.sh verify RECEIPT`. A valid receipt
establishes bounded synthetic business equivalence on both targets; `production_ready` and
`alloydb_platform_qualified` remain false. It does not inherit the MS67 Cloud SQL platform drills.

The CI workflow runs MS71 and the unchanged comparator/journey regression suites on Windows and
Linux. Local test fixtures, provisioned infrastructure, successful deployment, and preflight are
never reported as completed MS71 qualification.
