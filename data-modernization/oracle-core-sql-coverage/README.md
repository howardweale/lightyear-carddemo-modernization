# Oracle core SQL and datatype bounded execution

MS #50.1 executes the first broad tranche of the Oracle Semantic Coverage Program. It covers all
230 catalogued behaviors and 920 governed cases in the types, globalization, expressions, and
queries domains.

Every case compares a separately declared Oracle contract expectation with an independently
executed deterministic model result. The four case dimensions exercise the focused behavior, its
null/boundary companion, the declared 19c/26ai session/version posture, and failure plus recovery.

```bash
PYTHONPATH=src python3 -m lightyear_data build-oracle-core-sql-coverage --project-root .
PYTHONPATH=src python3 -m lightyear_data verify-oracle-core-sql-coverage --project-root .
./data-modernization.sh oracle-core-sql
```

The receipt keeps three counts distinct:

- 920 catalog cases passed the bounded model across 230 core behaviors.
- The 24 MS #49 bootstrap executions remain separate evidence records.
- Five bootstrap behavior bindings overlap the core tranche and three do not, producing 233 unique
  bounded-model-verified behaviors rather than an inflated sum of 238.

This is not native Oracle execution. The native execution plan requires authorized Oracle 19c and
26ai database identities, session settings, timestamps, case observations, diagnostics, and sealed
receipts. Native conformance, target equivalence, iDempiere application equivalence, CloudBank
mapping, migration completion, and production readiness remain false.
