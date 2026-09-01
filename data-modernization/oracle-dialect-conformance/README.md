# Oracle dialect authority and first executable fixtures

MS #49 acquires a pinned subset of Oracle's official `db-sample-schemas` release `v23.3` and
turns the eight semantic risks selected in MS #48 into a deterministic executable corpus.

Artifacts:

- `fixture-catalog.json` binds 8 fixtures and 24 cases to Oracle documentation, the official
  Customer Orders, Human Resources, and Sales History schema sources, and the iDempiere source
  paths that established their priority.
- `model-conformance.receipt.json` records all 24 cases passing the bounded local semantics model.
- `native-oracle-fixtures.sql` is a fail-fast SQL*Plus/SQLcl harness that emits one PASS marker per
  fixture or exits on the first Oracle error.

Build and verify:

```bash
PYTHONPATH=src python3 -m lightyear_data build-oracle-dialect-corpus
PYTHONPATH=src python3 -m lightyear_data verify-oracle-dialect-corpus
./data-modernization.sh oracle-dialect
```

The local receipt is not a native Oracle receipt. `native_oracle_execution_observed`,
`native_oracle_conformance`, `idempiere_application_equivalence`, `cloudbank_mapping_complete`,
`migration_complete`, and `production_ready` remain false. A later authorized Oracle run must
capture the database identity, image or service version, script digest, all eight PASS markers,
and transaction/session evidence before any native conformance claim can change.
