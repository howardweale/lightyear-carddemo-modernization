# CloudBank modern Oracle reference estate

This directory records a static inventory and an executable-baseline contract for Oracle's
official CloudBank v5 reference application from `oracle/microservices-backend`. The upstream source is pinned at commit
`4f41b16d00c45503f691836fee8138010c969e86`; its source code is not copied into this repository.

CloudBank is important because it is already a cloud-native microservices application while still
depending on Oracle Database, Oracle connection and wallet components, Transactional Event Queue,
and Oracle MicroTx LRA coordination. It lets LIGHTYEAR demonstrate that autonomous modernization
is not limited to visibly old applications: a modern Java/Kubernetes estate can also require
database decoupling and behavioral verification.

## Measured source surface

The pinned `cloudbank-v5` subtree contains:

- 189 tracked files;
- 70 Java source units and 6,711 Java source lines;
- 10 Maven modules, eight runtime service modules, and ten deployable units;
- nine SQL files and 231 SQL lines;
- 53 Spring and nine JAX-RS endpoint annotations; and
- static Oracle, LRA, local-transaction, messaging, and security coupling signals.

The Control Tower exposes five workloads and 20 bounded migration-risk scenarios:

1. customer and account management;
2. money transfer;
3. cheque deposit and clearance;
4. authentication and service authorization; and
5. credit score service.

## Rebuild the inventory

```bash
git clone --filter=blob:none --no-tags \
  https://github.com/oracle/microservices-backend.git /path/to/oracle-microservices-backend
git -C /path/to/oracle-microservices-backend checkout \
  4f41b16d00c45503f691836fee8138010c969e86
./cloudbank-reference-estate.sh inventory /path/to/oracle-microservices-backend
./cloudbank-reference-estate.sh verify-inventory /path/to/oracle-microservices-backend
./cloudbank-reference-estate.sh build
./cloudbank-reference-estate.sh verify
```

Windows:

```powershell
.\cloudbank-reference-estate.ps1 inventory C:\path\to\oracle-microservices-backend
.\cloudbank-reference-estate.ps1 verify-inventory C:\path\to\oracle-microservices-backend
.\cloudbank-reference-estate.ps1 build
.\cloudbank-reference-estate.ps1 verify
```

The inventory tool refuses a dirty checkout or a commit other than the recorded pin.

## Execute the bounded source baseline

MS #54 requires the full pinned external checkout, Java 21, Maven 3.6 or newer, and, for the native
suite, Docker plus the identified Oracle Free image. The detailed operator flow and claim boundary
are in [`executable-baseline/README.md`](executable-baseline/README.md).

```bash
./cloudbank-executable-baseline.sh verify
./cloudbank-executable-baseline.sh verify-source /path/to/oracle-microservices-backend
```

The checked-in readiness receipt is `ready-to-execute-not-observed`. It is a deterministic
execution contract, not a fabricated source-build or native-runtime result.

## Generate the first PostgreSQL mapping

MS #55 selects the `customer` service as the first transformation workcell. The generated mapping
under [`customer-postgresql/`](customer-postgresql/) covers all seven Oracle columns, the primary
key, Liquibase order, empty-string normalization, DATE/SYSDATE behavior, repository fragment
queries, and CRUD transactions on PostgreSQL 16. It preserves application and production
equivalence as blocked until later milestones.

```bash
./cloudbank-customer-postgresql.sh verify
./cloudbank-customer-postgresql.sh verify-source /path/to/oracle-microservices-backend
```

## Control Tower projection

**CloudBank Reference Estate** is selectable alongside **CardDemo Reference Estate** and
**Oracle Customer (Large)**. PostgreSQL 16 is selected and production-readiness qualification is
contracted for the bounded Customer workcell; target selection for the rest of CloudBank remains
governed later work.

## Run the first bounded application factory workcell

MS #56 seals the six customer-service edits needed to apply that mapping to Spring/JPA and gives
the existing factory controller a baseline-first work order. The same synthetic repository and
authorization contract must pass first on unchanged Oracle source and then on the generated
PostgreSQL service. The operator flow is documented under
[`../../factory/cloudbank/customer-postgresql/`](../../factory/cloudbank/customer-postgresql/).

```bash
./cloudbank-dark-factory.sh verify
./cloudbank-dark-factory.sh verify-source /path/to/oracle-microservices-backend
```

## Qualify the Customer workcell more deeply

MS #57 chains from the signed MS #56 receipt and runs one five-test HTTP, security, error, isolation,
rollback, and data-boundary contract on both native database lanes. It removes Oracle UCP from the
PostgreSQL target dependency path, inspects the executable JAR, creates a 10,000-row synthetic
aggregate profile, and records an offline simulated checkpoint/cutover/rollback rehearsal. The
operator flow is documented under
[`../../factory/cloudbank/customer-production-qualification/`](../../factory/cloudbank/customer-production-qualification/).

```bash
./cloudbank-production-qualification.sh verify
./cloudbank-production-qualification.sh verify-source /path/to/oracle-microservices-backend
```

## Plan the whole application and admit the transaction wave

MS #58 inventories all eight root deployables and assigns each exactly once to a governed delivery
wave. The first connected wave is Customer, Account, and Transfer. It adds an exact source contract,
a 13-column Account/Journal PostgreSQL mapping, transaction and recovery behavior, compatibility
blockers, and a signed admission chained to the passing MS #57 receipt.

```bash
./cloudbank-transaction-wave.sh verify
./cloudbank-transaction-wave.sh verify-source /path/to/oracle-microservices-backend
```

Oracle AQ/JMS and MicroTx LRA replacement remain blocked on native behavioral evidence. The
committed readiness receipt does not claim target code generation or Account/Transfer execution.

## Generate and run the PostgreSQL transaction core

MS #59 materializes the admitted Account and Transfer target in an isolated workspace. It replaces
the distributed LRA debit/deposit callback with one idempotent PostgreSQL transaction, retains an
authenticated Transfer facade, and packages both services without Oracle or MicroTx runtime
libraries.

```bash
./cloudbank-transaction-core.sh verify
./cloudbank-transaction-core.sh verify-source /path/to/oracle-microservices-backend
```

The signed native action requires the MS #58 admission receipt. Its seven tests cover all eight
MS #58 transaction scenarios. The committed readiness artifact does not claim that operator run,
Oracle equivalence, Checks AQ migration, the remaining service workcells, or production readiness.

## Run the native Account/Transfer HTTP wave

MS #60 starts the generated Account and Transfer JARs together against native PostgreSQL. Eleven
scenarios prove authentication boundaries, rejection without mutation, successful and concurrent
value conservation, duplicate suppression, and durable replay after separate service restarts.

```bash
./cloudbank-native-wave.sh verify
./cloudbank-native-wave.sh verify-source /path/to/oracle-microservices-backend
```

The signed action requires the passing MS #59 receipt. A passing run closes the bounded target-side
native transaction-wave and local LRA-replacement gates. It does not qualify production identity,
Oracle equivalence, Checks AQ/JMS, the remaining services, or production readiness.

## Run the bounded Oracle/PostgreSQL equivalence gate

MS #61 binds the signed MS #57 and MS #60 receipts and executes one seven-scenario normalized
contract across the pinned Oracle source and generated PostgreSQL target.

```bash
./cloudbank-oracle-equivalence.sh verify
./cloudbank-oracle-equivalence.sh verify-source /path/to/oracle-microservices-backend
```

The lanes run sequentially and use synthetic data on loopback-only database ports. A passing signed
receipt closes bounded normalized Customer, Account, and Transfer equivalence, while explicitly
retaining LRA compensation versus atomic rollback as an implementation difference. It does not
start the source integrated HTTP wave with MicroTx or qualify production identity, Checks messaging,
the remaining services, whole-application equivalence, migration completion, or production readiness.

## Run the production OAuth application-boundary gate

MS #62 chains from the signed MS #61 result and replaces the bounded target's Basic-authentication
and static internal token with a live PostgreSQL-backed CloudBank authorization server and scoped,
audience-bound RSA JWTs.

```bash
./cloudbank-production-oauth.sh verify
./cloudbank-production-oauth.sh verify-source /path/to/oracle-microservices-backend
```

The native gate starts Authorization, Account, and Transfer, separates caller and service identity,
rejects client, signature, scope, audience, and ownership failures before mutation, and restarts all
three services with the same signing key. The signed result qualifies the application OAuth profile,
not external TLS, managed-secret rotation, enterprise IdP federation, Checks messaging, the remaining
services, whole-application equivalence, migration completion, or production readiness.

## Run the Checks durable-messaging gate

MS #63 chains from the signed MS #62 receipt and replaces Oracle AQ/JMS in Checks and Test Runner
with a PostgreSQL durable queue. Its bounded semantics include idempotent enqueue, per-aggregate
ordering, exclusive claims, lease-based redelivery, retry backoff, dead-letter quarantine, and
governed replay.

```bash
./cloudbank-checks-messaging.sh verify
./cloudbank-checks-messaging.sh verify-source /path/to/oracle-microservices-backend
```

The native gate packages the five Authorization, Account, Transfer, Checks, and Test Runner services
without Oracle or MicroTx runtime libraries and exercises twelve PostgreSQL queue scenarios. A
passing signed receipt qualifies target messaging only; it does not establish native Oracle AQ
equivalence, remaining-service completion, whole-application equivalence, or production readiness.

The projection is composed with the existing PL/I and Oracle Customer (Large) fragments. It does
not change the canonical CardDemo graph or the identity to which runtime and audit evidence are
bound.

## Evidence boundary

MS #53 is upstream static inventory and curated migration-risk evidence. MS #54 adds the exact
source-build and bounded Oracle-runtime admission path. MS #55 generates the customer-table
PostgreSQL mapping while leaving its committed native target readiness unobserved. No customer
system or production data is attached. MS #56 adds the sealed application transformation and
dual-run workcell, but the committed readiness receipt does not claim the operator run occurred.
MS #57 adds deeper Customer qualification, packaging and offline rehearsal contracts. MS #58 adds
the complete portfolio plan and admits the transaction wave. MS #59 generates the Account/Transfer
PostgreSQL target and its native operator gate. MS #60 adds the integrated target-side native HTTP,
restart, and concurrency wave. MS #61 adds bounded normalized Oracle/PostgreSQL comparison for the
Customer, Account, and Transfer scope. MS #62 adds the production OAuth application boundary for
Authorization, Account, and Transfer. MS #63 adds the bounded PostgreSQL Checks messaging target.
Native Oracle AQ comparison, external production security operations, production data, the remaining
service workcells, whole-CloudBank equivalence, migration completion, and production readiness remain
unclaimed.
