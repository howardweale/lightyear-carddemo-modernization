# CloudBank customer first dark factory run

Milestone 56 turns the admitted MS #54 Oracle baseline and MS #55 PostgreSQL mapping into the first
end-to-end CloudBank factory workcell. The existing factory controller copies the complete pinned
`cloudbank-v5` source into an isolated workspace, gives planner and builder roles only six writable
customer-service paths, applies the content-addressed transformation, and leaves the upstream
checkout untouched.

The verifier runs one shared Spring/JPA and controller contract twice:

1. against the unchanged customer service and the immutable Oracle image admitted by MS #54; and
2. against the generated customer service and the immutable PostgreSQL image admitted by MS #55.

The contract uses a four-row synthetic corpus and checks JPA bootstrap, default timestamps, Oracle
empty-string normalization, case-sensitive name/email searches, repository CRUD, and owner/admin
controller authorization. The PostgreSQL lane additionally verifies the new `ROLE` field and target
schema binding. Maven output, ephemeral database credentials, and production data are not written
to the signed workcell receipt.

## Static verification

```bash
./cloudbank-dark-factory.sh verify
./cloudbank-dark-factory.sh verify-source ../cloudbank-upstream
```

## First native factory run

Keep `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` set to the same value used for MS #54 and MS #55,
then run:

```bash
./cloudbank-dark-factory.sh run \
  ../cloudbank-upstream \
  work/cloudbank-oracle-runtime.receipt.json \
  work/cloudbank-customer-postgresql.receipt.json \
  work/cloudbank-dark-factory \
  operator-id

./cloudbank-dark-factory.sh verify-receipt \
  work/cloudbank-dark-factory/cloudbank-customer-dark-factory.receipt.json
```

The retained run directory contains the isolated transformed workspace, hash-chained events, and
role-separated artifacts. Do not commit the run directory or either operator receipt.

## Exact boundary

A passing run qualifies one bounded customer-service application contract on both databases. It
does not authorize promotion, refactor the shared parent or other services, compare production
data, prove concurrency/CDC/cutover/rollback, establish whole-CloudBank equivalence, complete a
migration, or establish production readiness. Dependency resolution is an explicitly allowed
development-network boundary and is recorded in the receipt.
