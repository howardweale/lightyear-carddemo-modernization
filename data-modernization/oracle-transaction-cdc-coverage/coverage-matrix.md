# Oracle transaction and CDC bounded execution matrix

Release 0.50.3 executes the transaction and operations tranche of the MS #50 Oracle Semantic
Coverage Program. The evidence is deterministic bounded-model evidence, not native Oracle
observation.

This catalog receipt covers 500 catalogued behaviours: 381/500 bounded-model verified and 0/500 native-Oracle verified. These counts exclude separate application-level evidence such as CloudBank runs; they do not establish target equivalence or production readiness.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | 500 | 2000 |
| Prior core SQL/type and PL/SQL catalog execution | 310 | 1240 |
| Transaction and operations cases passed in bounded model | 70 | 280 |
| Cumulative catalog execution | 380 | 1520 |
| Unique bounded-model coverage including bootstrap-only binding | 381 | 1544 |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

| Domain | Topic families | Behaviors | Passed cases |
|---|---:|---:|---:|
| Transactions, isolation, locking, and concurrency | 9 | 45 | 180 |
| CDC, metadata, session, security, and diagnostics | 5 | 25 | 100 |
| **Total** | **14** | **70** | **280** |

Seven of the eight MS #49 bootstrap behavior bindings now overlap executed catalog tranches; the LOB
binding remains bootstrap-only. That produces 381
unique bounded-model verified behaviors, not 388. The remaining
480 catalog cases cover schema/DML, schema objects, and
structured data. Concurrency schedules, locks, redo/SCN, LogMiner, metadata visibility, privilege
enforcement, and diagnostics are bounded simulations until sealed native Oracle 19c/26ai evidence
is attached.
