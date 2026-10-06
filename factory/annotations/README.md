# Annotation ledger

The operator initializes `ledger.jsonl` with `lightyear-factory annotate add`.
The ledger and keys are deployment data, not source fixtures. Never commit a
customer ledger. All writes are signed, hash chained and exclusive-writer guarded.
An incomplete append fails closed; recovery requires an explicit operator action.

See [the operator guide](../../docs/factory/graph-memory.md).
