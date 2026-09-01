# Oracle semantic coverage matrix

Release 0.50.0 establishes the governed coverage contract. It does not claim that all catalogued
behaviors have been implemented or executed.

| Domain | Behavior contracts | Specified cases |
|---|---:|---:|
| Datatypes, nulls, numbers, dates, and intervals | 65 | 260 |
| Character semantics, NLS, collation, and conversion | 45 | 180 |
| Functions and expression evaluation | 60 | 240 |
| Queries, joins, analytics, hierarchy, and set operations | 60 | 240 |
| DML, DDL, constraints, and indexes | 50 | 200 |
| Transactions, isolation, locking, and concurrency | 45 | 180 |
| PL/SQL, packages, cursors, exceptions, and triggers | 80 | 320 |
| Views, sequences, synonyms, partitions, and materialized views | 35 | 140 |
| LOB, JSON, XML, and object types | 35 | 140 |
| CDC, metadata, session, and security behavior | 25 | 100 |
| **Total** | **500** | **2000** |

## Evidence ladder

| Level | Behaviors | Cases | Meaning |
|---|---:|---:|---|
| Catalogued | 500 | 2,000 | Governed scope with Oracle documentation authority |
| Bounded-model verified | 8 | 24 | Existing MS #49 bootstrap evidence only |
| Native Oracle verified | 0 | 0 | Requires an authorized Oracle 19c/26ai execution receipt |
| Target equivalent | 0 | 0 | Requires source-versus-target comparison evidence |

The architect-facing coverage answer must always carry the evidence level. Catalogued does not mean
supported, bounded-model execution does not mean native Oracle conformance, and native verification
does not by itself establish target equivalence or production readiness.
