# CloudBank PostgreSQL transaction-core factory run

MS #59 turns the admitted Account/Transfer wave into generated target code and a native
PostgreSQL run. The source checkout remains unchanged; the generated workspace contains the
bounded transformation.

## Verify contracts and pinned source

```bash
./cloudbank-transaction-core.sh verify
./cloudbank-transaction-core.sh verify-source /path/to/cloudbank-upstream
```

## Run the workcell

Use the same `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` used for MS #58, and pin the already
downloaded PostgreSQL image by immutable ID through the signed MS #58 receipt:

```bash
./cloudbank-transaction-core.sh run \
  /path/to/cloudbank-upstream \
  work/cloudbank-transaction-wave/cloudbank-transaction-wave.receipt.json \
  work/cloudbank-transaction-core \
  operator-id

./cloudbank-transaction-core.sh verify-receipt \
  work/cloudbank-transaction-core/cloudbank-transaction-core.receipt.json
```

Replace `operator-id` with a stable audit label such as `howard-macbook`. The command starts one
ephemeral, immutable PostgreSQL 16 container on a loopback-only random port, materializes the
target under the run directory, executes seven tests across Account and Transfer, packages both
Spring Boot applications, verifies that the JARs contain no Oracle or MicroTx runtime libraries,
then signs the bounded receipt.

## What changes

- Account, Transfer, the root Maven dependency, PostgreSQL Liquibase DDL, and seven Java target
  units are changed or created in the isolated workspace.
- A transfer command debits, credits, records two journal entries, and marks its idempotency key
  complete in one PostgreSQL transaction.
- Stable account-lock ordering, owner authorization, duplicate suppression, injected rollback,
  retry, and journal replay are exercised with synthetic data.
- The old Account LRA participant classes and its Account-local AQ grant script are removed from
  the generated target.

## Evidence boundary

This milestone proves Account's bounded native PostgreSQL transaction core and Transfer's isolated
facade contract. It does not start both services for a real HTTP exchange, so the full native
transaction wave and LRA-replacement claims remain false. It also does not run the original
services on Oracle, so Oracle-to-PostgreSQL transaction equivalence remains false. The Oracle AQ
flow used by Checks, the remaining five service workcells, production data, whole-application
equivalence, migration completion, and production readiness also remain false.
