# Integrated pilot qualification

MS #42 binds the exact selected `ACCOUNTV` reference slice and its five-cell work package to one
cross-technology development qualification. The bounded proof covers:

- `ACCOUNTV` and `ACCTREC` COBOL/copybook layout, SQL, and PL/I call contract;
- `ACCTPL1` Db2 lookup and external `CBACT04C OPTIONS(COBOL)` boundary;
- the three-column `AUTHFRDS` projection, primary key, and ordered unique index;
- `ACCTPIL` RUN/FORMAT step order and its STEPLIB/ACCTIN bindings;
- `DATEFMT` null/non-null pointer branches and return codes 8/0;
- all five work-package coordination dependencies.

The 40-case synthetic corpus contains 5 positive integrated paths, 31 targeted boundaries, and 4
fail-closed native-runtime vectors. The evidence matrix accounts for all 15 bounded deliverables,
10 acceptance-evidence requirements, and 15 blocked live-evidence requirements. The 30-entry
compatibility ledger uses all five governing classes.

```bash
./integrated-pilot-qualification.sh verify
PYTHONPATH=src python3 -m lightyear_pilot.integrated_qualification verify
```

`wave_2_integrated_development_ready: true` is limited to this exact six-file synthetic reference
selection. It does not admit a factory work order, authorize dispatch or native execution, model
the external `CBACT04C` business behavior, or establish mainframe equivalence or production
readiness. Those claims remain false and Wave 3 remains blocked.
