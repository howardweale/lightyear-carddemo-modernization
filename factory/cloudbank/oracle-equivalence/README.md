# CloudBank bounded Oracle/PostgreSQL equivalence

MS #61 compares the pinned Oracle source and the generated PostgreSQL target for the migrated
Customer, Account, and Transfer boundary. Customer equivalence is inherited only from the verified
MS #57 receipt. Account state transitions and Transfer orchestration are re-executed in isolated
MS #61 workspaces using one seven-scenario normalized observation contract.

## Verify the committed contracts

```bash
./cloudbank-oracle-equivalence.sh verify
./cloudbank-oracle-equivalence.sh verify-source /path/to/cloudbank-upstream
```

## Run both native database lanes

Use the same `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` used to sign MS #57 and MS #60:

```bash
./cloudbank-oracle-equivalence.sh run \
  /path/to/cloudbank-upstream \
  work/cloudbank-production-qualification/cloudbank-customer-production-qualification.receipt.json \
  work/cloudbank-native-wave/cloudbank-native-transaction-wave.receipt.json \
  work/cloudbank-oracle-equivalence \
  howard-macbook

./cloudbank-oracle-equivalence.sh verify-receipt \
  work/cloudbank-oracle-equivalence/cloudbank-oracle-postgresql-equivalence.receipt.json
```

The Oracle and PostgreSQL containers run sequentially to reduce local memory pressure. Both expose
random loopback-only ports, use generated credentials, and receive synthetic data only. Raw Maven
output and credentials are not written into evidence.

## What a passing receipt proves

- The prior Customer Oracle/PostgreSQL qualification receipt remains valid and is bound into MS #61.
- The original Account business methods execute against native Oracle.
- The original Transfer source executes invalid-input, missing-identity, and successful orchestration
  contracts against isolated HTTP collaborators.
- The generated Account target executes the same normalized balance and recovery outcomes against
  native PostgreSQL, while its Transfer facade executes the corresponding target contract.
- Both lanes emit exactly the same seven-scenario normalized observation identity.

This is bounded business equivalence, not identical implementation. Oracle LRA compensation and
PostgreSQL local atomic rollback intentionally differ internally. The original integrated
Account/Transfer HTTP wave is not started with an Oracle MicroTx coordinator in this milestone.
Production OAuth/OIDC, Checks AQ/JMS, the remaining five services, production data, whole-application
equivalence, migration completion, and production readiness remain false.
