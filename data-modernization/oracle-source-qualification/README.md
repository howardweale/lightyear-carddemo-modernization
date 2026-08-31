# Oracle source and stored-procedure qualification

MS #43 binds a genuine Oracle semantic-core source adapter to the bounded AUTHFRDS
Oracle-to-PostgreSQL development path. The committed evidence contains:

- `source-compatibility-ledger.json` — all 26 columns and material Oracle source behaviors;
- `source-conformance.receipt.json` — discovery, profiling, extraction, CDC resume, transaction,
  ledger, determinism, and fail-closed live-claim checks;
- `procedure-compatibility-ledger.json` — supported, policy, lossy, and excluded PL/SQL boundaries;
- `procedure-conformance.receipt.json` — 20 deterministic result and side-effect cases;
- `procedure-qualification.json` — four declared procedure translations and eight independent gates;
- `qualification.json` — the combined eight-gate Oracle-to-PostgreSQL source qualification.

Run:

```bash
./data-modernization.sh oracle-source
PYTHONPATH=src python3 -m lightyear_data verify-oracle-source-qualification
```

`development_ready: true` and `supported_procedure_subset_qualified: true` apply only to the
declared bounded reference source and synthetic behavior corpus. No live Oracle catalog, source
rows, redo stream, PostgreSQL target, or native procedure execution was observed. Full stored-logic
completion, database migration completion, and production readiness remain false.
