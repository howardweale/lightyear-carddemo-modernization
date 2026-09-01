# Oracle transaction and CDC bounded execution

MS #50.3 executes all 70 behavior contracts and 280 governed cases in the `transactions` and
`operations` domains. The tranche covers commit, rollback, savepoints, read committed,
serializable and read-only snapshots, row and table locks, deadlocks, redo/LogMiner capture,
dictionary visibility, session state, privileges, and Oracle diagnostic identity.

Every case compares a separately declared Oracle contract expectation with an independently
executed deterministic model observation. Each topic has five behavior focuses and every behavior
has canonical, null/boundary, session/version, and failure/recovery case dimensions.

```bash
PYTHONPATH=src python3 -m lightyear_data build-oracle-transaction-cdc-coverage --project-root .
PYTHONPATH=src python3 -m lightyear_data verify-oracle-transaction-cdc-coverage --project-root .
./data-modernization.sh oracle-transaction-cdc
```

The cumulative receipt keeps catalog cases, bootstrap evidence records, and unique behavior IDs
distinct:

- 1,520 catalog cases have passed across 380 behaviors when combined with MS #50.1 and #50.2.
- The 24 MS #49 bootstrap executions remain separate evidence records.
- Seven bootstrap behavior bindings overlap executed tranches; the LOB binding remains outside,
  producing 381 unique bounded-model-verified behaviors and 1,544 evidence records.
- The remaining 480 catalog cases cover schema/DML, schema objects, and structured data.

This is not live Oracle concurrency, redo, LogMiner, metadata, privilege, or diagnostic evidence.
The native execution plan requires authorized Oracle 19c and 26ai identities, multiple controlled
sessions, deterministic schedules, SCN and redo coordinates, privilege context, exact error stacks,
timestamps, runner identity, and sealed receipts. Native conformance, target equivalence, iDempiere
application equivalence, CloudBank mapping, migration completion, and production readiness remain
false.
