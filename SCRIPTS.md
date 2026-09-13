# Entrypoint catalog

`scripts.catalog.json` is the machine-checkable source of truth for every top-level POSIX and
PowerShell entry point. `./lightyear.sh catalog` verifies that the catalog is hash-valid, that no
script is undocumented, and that every POSIX entry point has a PowerShell twin.

## Supported roles

| Role | When to use it | Release behavior |
|---|---|---|
| `aggregator` | Supported composite commands such as `lightyear` and `verify` | Delegates to named controls |
| `release-gated` | Deterministic evidence build and verification | Included in the complete verifier |
| `developer` | Interactive exploration, tests, benchmarks, and focused gauntlets | Covered by tests or dedicated CI |
| `operator` | Inputs that require a human-selected catalog or evaluation | Never started implicitly |
| `live-authorized` | Credentialed live collection or explicitly acknowledged non-production mutation | Never started by release verification |
| `internal` | Shared runtime helpers sourced by other scripts | Not a standalone workflow |

## Which command should I run?

- `./verify.sh` is the authoritative, complete release verifier. It fails if the pinned upstream
  fixture is absent, any receipt claim is promoted without authority, or script ownership drifts.
- `./test.sh` runs the complete Python suite and requires the pinned upstream fixture.
- `./test.sh unit-only` permits missing upstream data only after printing an explicit incomplete-run
  warning; the skipped integration tests must never be interpreted as a complete green build.
- `./lightyear.sh doctor` checks repository prerequisites and the graph toolchain.
- `./lightyear.sh catalog` checks entry-point coverage without running workloads.
- `./quality-gate.sh` and `./mainframe-access.sh live` are operator-controlled by design; they are
  not release-verifier substitutes.
- `./cloudbank-executable-baseline.sh verify` checks the committed MS #54 execution contract;
  `verify-source`, `source-build`, and `oracle-runtime` enforce the exact pinned checkout and
  authorized Java 21/Maven/Docker evidence path.
- `./cloudbank-customer-postgresql.sh verify` checks the MS #55 seven-column mapping, PostgreSQL
  DDL, synthetic fixtures, compatibility ledger, and fail-closed native execution contract;
  `native-postgresql` additionally requires an admitted MS #54 Oracle receipt.
- `./cloudbank-dark-factory.sh verify` checks the MS #56 sealed six-file application transformation
  and dual-run acceptance contract; `run` additionally requires the signed MS #54 Oracle and
  MS #55 PostgreSQL receipts produced with the same evidence key.
- `./cloudbank-production-qualification.sh verify` checks the MS #57 Customer-service HTTP,
  transaction, packaging, synthetic-profile, and offline cutover/rollback qualification contract;
  `run` additionally requires the passing signed MS #56 receipt produced with the same evidence key.
- `./cloudbank-transaction-wave.sh verify` checks the MS #58 eight-service inventory, transaction
  source and behavior contracts, Account PostgreSQL mapping, recovery model, and migration waves;
  `admit` additionally requires the passing signed MS #57 receipt produced with the same evidence key.
- `./cloudbank-transaction-core.sh verify` checks the MS #59 bounded Account/Transfer target,
  atomic transaction contract, packaging boundary, and false whole-application claims; `run`
  additionally requires the passing signed MS #58 admission receipt produced with the same key.
- `./cloudbank-native-wave.sh verify` checks the MS #60 integrated Account/Transfer HTTP,
  authentication, restart replay, concurrency, conservation, and packaging gates; `run` additionally
  requires the passing signed MS #59 native PostgreSQL receipt produced with the same key.
- `./cloudbank-oracle-equivalence.sh verify` checks the MS #61 shared seven-scenario normalized
  Oracle/PostgreSQL observation contract; `run` additionally requires passing signed MS #57 and
  MS #60 receipts produced with the same key and executes the two native database lanes sequentially.
- `./cloudbank-production-oauth.sh verify` checks the MS #62 Authorization/Account/Transfer OAuth
  application-boundary contract; `run` additionally requires the signed MS #61 receipt produced
  with the same key and exercises real client-credentials JWTs, resource servers, and key restart.
- `./cloudbank-checks-messaging.sh verify` checks the MS #63 durable Checks deposit/clearance queue,
  ordering, idempotency, claim, redelivery, retry, dead-letter, packaging, and false production
  claims; `run` additionally requires the signed MS #62 receipt produced with the same key.
- `./cloudbank-edge-ai.sh verify` checks the MS #64 deterministic synthetic Credit Score and
  bounded Chatbot application contracts; `run` additionally requires signed MS #57 and MS #63
  receipts produced with the same key, packages all eight CloudBank deployables, and executes the
  generated Authorization, Checks, Test Runner, Credit Score, and Chatbot target workcells.
- `./cloudbank-production-readiness.sh verify` checks the MS #65 immutable-image deployment,
  Kubernetes hardening, and cutover/rollback rehearsal contracts; `render` requires an eight-image
  lock and non-production environment profile, while `run` additionally requires the signed MS #64
  receipt and signed 24-scenario operator observation produced with the same evidence key.
- `./cloudbank-ms65-rehearsal.sh run` produces that observation from the bound live GKE target,
  passed signed shared journeys and passed signed isolated SQL recovery. The asynchronous Cloud
  Build launcher survives Cloud Shell disconnects, checkpoints recovery intent before its bounded
  CreditScore traffic switch, restores the original selector, and admits the resulting MS65 receipt.
- `./cloudbank-whole-application-equivalence.sh verify` checks the MS #66 paired eight-service
  governed Oracle/source and PostgreSQL/target contract; `run` additionally requires signed
  MS #61/MS #64 receipts and two same-run signed lane observations without fabricating native
  execution. `./cloudbank-ms66-dual-lane.sh` is the low-level cross-platform executor used by the
  asynchronous GKE submitter: it preserves the pinned checkout, applies only the hash-bound patch in
  a fresh workspace, runs native Oracle/AQ/MicroTx in an isolated namespace, cleans that namespace,
  and then exercises the deployed PostgreSQL lane. Its `recover` command accepts only a signed,
  identity-bound isolated-lane recovery journal.
- `./cloudbank-platform-qualification.sh verify` checks the MS #67 real non-production platform
  contract and GKE implementation; `preflight` performs read-only checks against one signed explicit
  context, while `admit` requires passing signed MS #65/MS #66 receipts and all 28 signed live
  platform scenarios. Chargeable GKE mutation and teardown remain separately acknowledged scripts.
- `./idempiere-divergence-audit.sh verify` checks the committed IDDA Stage 1 pairing and premise
  evidence. `build` and `verify-source` require the exact clean MS #48 iDempiere checkout; neither
  action executes a database or calls a model.
- `./idempiere-divergence-audit.sh compare IDEMPIERE_ROOT` builds the MS #69 pilot followed by
  the full bounded static comparison. `verify-comparison` checks committed integrity and accounting;
  `verify-comparison-source IDEMPIERE_ROOT` also replays every pair from the exact clean source pin.
  Known client/registration commands are counted outside the SQL coverage denominator. Unresolved
  constructs remain findings; none of these commands calls agents or executes SQL.
- `./idempiere-divergence-audit.sh triage` builds the MS #70 deterministic twenty-case work package,
  safe-floor role-contract calibration and evidence registers. `verify-triage` checks committed
  derivation and claim boundaries; `verify-triage-source IDEMPIERE_ROOT` additionally replays the
  exact source and bounded context windows. These release commands call no model and no Builder.
  Credentialed `run-triage` is an explicit Python-controller action requiring an output path,
  current nonzero model pricing and `OPENAI_API_KEY`; it never rewrites committed evidence.

See `scripts.catalog.json` for the exact purpose, role, and verification owner of all entry points.
