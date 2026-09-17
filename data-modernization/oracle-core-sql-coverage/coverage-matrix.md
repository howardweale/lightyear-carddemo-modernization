# Oracle core SQL and datatype execution matrix

Release 0.50.1 executes the first broad tranche of the MS #50 Oracle Semantic Coverage Program.
The evidence is deterministic bounded-model evidence, not native Oracle observation.

This catalog receipt covers 500 catalogued behaviours: 233/500 bounded-model verified and 0/500 native-Oracle verified. These counts exclude separate application-level evidence such as CloudBank runs; they do not establish target equivalence or production readiness.

| Evidence level | Behaviors | Cases / evidence records |
|---|---:|---:|
| Catalogued | 500 | 2000 |
| Core catalog cases passed in bounded model | 230 | 920 |
| Unique bounded-model coverage including non-core bootstrap bindings | 233 | 944 |
| Native Oracle verified | 0 | 0 |
| Target equivalent | 0 | 0 |

| Core domain | Behaviors | Passed cases |
|---|---:|---:|
| Types | 65 | 260 |
| Globalization | 45 | 180 |
| Expressions | 60 | 240 |
| Queries | 60 | 240 |
| **Total** | **230** | **920** |

The 24 MS #49 bootstrap executions remain separate evidence records. Five of their eight behavior
bindings overlap the core tranche; three remain outside it. That produces 233 unique bounded-model
verified behaviors, not 238. Native Oracle 19c/26ai execution, target equivalence, iDempiere
application equivalence, and production readiness remain false.
