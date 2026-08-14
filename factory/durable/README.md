# Durable factory control plane

v0.16 turns the portfolio runner into a recoverable control plane. The local
reference backend is SQLite in WAL mode. Its contract is deliberately small so
production deployments can replace it with PostgreSQL and object storage.

## Guarantees

- `BEGIN IMMEDIATE` makes leasing atomic across workers.
- Lease tokens are returned once; only their SHA-256 digest is persisted.
- Heartbeats extend bounded leases. Expired leases are retried or dead-lettered.
- Passed work cells are terminal and never become eligible again.
- Later waves are eligible only after every earlier work cell has passed.
- A human approval receipt can be consumed by exactly one portfolio run.
- Work-cell receipts are content-addressed in the artifact index.
- Every state change enters a tamper-evident hash-chained event ledger.
- Dashboard access opens SQLite in `mode=ro` and has no dispatch route.

## Local operation

```bash
./durable-factory.sh init
./durable-factory.sh submit \
  --plan factory/portfolio/carddemo-plan.snapshot.json \
  --approval work/portfolio/approval.json \
  --run-id carddemo-portfolio-001
./durable-factory.sh lease --worker-id worker-01 --output work/lease.json
./durable-factory.sh start --lease work/lease.json
./durable-factory.sh heartbeat --lease work/lease.json
./durable-factory.sh complete --lease work/lease.json --receipt work/cell-receipt.json
./durable-factory.sh recover
./durable-factory.sh validate
./durable-factory.sh conformance
```

Set `LIGHTYEAR_DURABLE_DATABASE` to select a different database. Lease files
contain bearer authority and belong in protected ephemeral worker storage, never
in source control.

The conformance command deliberately kills a logical worker by allowing its lease
to expire, re-leases the same cell to a replacement, completes all waves once,
rejects approval replay, validates the event chain, and emits the deterministic
receipt committed at `factory/durable/conformance.receipt.json`.

## Production boundary

SQLite is the executable oracle for durability semantics, not the recommended
multi-host production database. A production adapter must preserve the same
atomic lease, approval-consumption, idempotency, receipt-index, and event-chain
contracts while using PostgreSQL and immutable object storage.
