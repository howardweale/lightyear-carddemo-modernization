# Oracle PL/SQL bounded execution matrix

Release 0.50.2 executes the PL/SQL tranche of the MS #50 Oracle Semantic Coverage Program.
The evidence is deterministic bounded-model evidence, not native Oracle observation.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | 500 | 2000 |
| Core SQL/type catalog cases passed | 230 | 920 |
| PL/SQL catalog cases passed | 80 | 320 |
| Cumulative catalog cases passed | 310 | 1240 |
| Unique bounded-model coverage including bootstrap-only bindings | 312 | 1264 |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

The tranche covers 16 PL/SQL topic families, five behavior focuses per
topic, and four governed case dimensions per behavior. The MS #49 `SELECT INTO`/`NO_DATA_FOUND`
binding overlaps this tranche; the transaction-locking and LOB bindings remain bootstrap-only.
That produces 312 unique bounded-model verified behaviors, not 318. The remaining 760 catalog cases,
native Oracle 19c/26ai execution, target equivalence, iDempiere application equivalence, and
production readiness remain false.
