# Oracle schema and structured-data bounded execution matrix

Release 0.50.4 executes the final bounded catalog tranche of the MS #50 Oracle Semantic Coverage
Program. The evidence is deterministic bounded-model evidence, not native Oracle observation.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | 500 | 2000 |
| Prior catalog execution | 380 | 1520 |
| Schema and structured-data cases passed in bounded model | 120 | 480 |
| Complete bounded catalog execution | 500 | 2000 |
| Bounded evidence including separate bootstrap executions | 500 | 2024 |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

| Domain | Topic families | Behaviors | Passed cases |
|---|---:|---:|---:|
| Schema and DML | 10 | 50 | 200 |
| Schema objects | 7 | 35 | 140 |
| Structured data | 7 | 35 | 140 |
| **Total** | **24** | **120** | **480** |

All eight MS #49 bootstrap bindings now overlap executed catalog behaviors, so unique bounded-model
coverage is 500 behaviors, not 508. The 24 bootstrap
runs remain separate evidence records, producing 2024
records in total. Complete bounded catalog execution does not establish native Oracle conformance,
target equivalence, iDempiere application equivalence, CloudBank mapping, migration completion, or
production readiness.
