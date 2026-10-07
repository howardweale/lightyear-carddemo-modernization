# Measured coverage and explicit public-fixture mappings

This increment adds native coverage and prospective return-contract corrections.
The original attempts 001–005 and their source bundles remain historical evidence.
Operator review; not independent attestation. No model calls. Native execution is
restricted to the approved dedicated Linux VM, never the Windows B06 host.

## Coverage contract

SQL Server records `sp_statement_starting` and `sp_statement_completed` Extended
Events in a session filtered to the call's SPID, with a no-event-loss ring buffer.
Truncation, dropped events and duplicate event sequence numbers fail closed.
ScriptDom parses the actual installed module definitions, including user triggers.
Its UTF-16 spans are matched to the native byte offsets. Statement visits, IF/WHILE
edges and CATCH entries are derived from those events. A predicate completion plus
the subsequent statement is required to infer a false edge. Merely completing a
procedure never proves coverage. Repeated loop visits are considered separately.

PostgreSQL uses `plpgsql_check` 2.10 in a digest-pinned derived image. Each call has
a fresh session-local profile. The statement catalogue is saved before execution;
statement identifiers must remain identical afterward. Native statement counts,
uncovered lines and the native procedural branch fraction are retained. Version
2.10 does not expose individual handler identities in its statement table, so the
error-path gate conservatively requires **100% of native branches**, whose
denominator includes exception-handler bodies. A lower fraction is not labelled
proof that a specific handler was missed; it means complete handler coverage is
unproven. This can reject an otherwise adequate test, but cannot waive that gate.

Both collectors cover procedural statements and branches. SQL expression branches,
query plans and branch coverage inside dynamic SQL text are outside this measurement.
The default statement/branch thresholds remain 90%/80%, with all error paths
required. Missing paths stay in the denominator; none is deleted because a
reference produced the expected result.

Seven separately declared native controls test a straight path, both branch edges,
a missing branch, a taken handler, a missing handler, an uninitialized scalar
declaration and a table-variable declaration on both engines. These
controls test the collectors, not twin effectiveness. The handler-hit control's
implicit return-code difference is retained and is not counted as an equivalence
success. Full runs bind the collector file, ScriptDom bridge and image identities
to those signed control receipts. Offline audit replays the control qualification
as well as every corpus comparison.

ScriptDom retains uninitialized scalar and table-variable declarations in an
explicit `excluded_declarations` catalogue. SQL Server does not emit their own
executable statement events; subsequent assignments and uses remain measured.
Initialized scalar declarations remain executable statements. This prospective
denominator correction is bound to bridge revision 2 and the two native controls;
it does not rewrite the first measured full run or remove unhit executable paths.

Offline replay independently derives the SQL summary from saved events and AST
spans, and PostgreSQL statement coverage from saved profile rows. The PostgreSQL
branch fraction is a recorded native-profiler result; replay validates and gates
that fraction, it does not execute the PostgreSQL compiler again. Signed file
closure binds all profiler inputs and outputs.

## Explicit mapping contract

Each procedure receives a `tsql-public-mapping/1` record bound to all six SQL/setup
asset hashes and its calling convention. The register covers all 42 procedures
and all 25 trap families. These are public-fixture rules, not customer approvals.

| Observable | Declared rule |
|---|---|
| Result sets | Preserve set order and exact column names; map only enumerated character type codes. Preserve values, whitespace, nulls and duplicate rows. Public fixture result rows are multisets. |
| Table schema | Infer only exact schema/table/column names and flag the inference. Map `int` to `integer`, and `varchar(n)` to `character varying(n)`; compare nullability and primary keys. Unknown types remain unsupported. |
| Table effects | Compare complete before/after captures, keyed by primary key where present, otherwise as duplicate-preserving multisets; include trigger tables. |
| Identity/sequence | Use native sequence ownership, not a guessed sequence name. Compare owner, seed, increment and last consumed value. An uncalled sequence maps to an unconsumed identity, not to a consumed seed. |
| OUTPUT / return | Exact values under each declared calling convention. The three corrected twins return status from their actual exception handlers. |
| Errors | Preserve raw numbers, severity, state and SQLSTATE. Two errors do not become equivalent without an explicit error map. |
| Informational messages | Map SQL Server INFO severity 0–10 to PostgreSQL NOTICE/00000; compare message text exactly. No blanket message suppression. |
| Row-count stream | Preserve actual TDS tokens. A present stream requires a policy decision because PostgreSQL does not expose an equivalent nested protocol stream. |
| Transactions / temp state | Compare exit state and all-table effects; detect caller-visible temp-object leaks. Internal transaction histories are not claimed complete. |
| Ambiguous UPDATE FROM / unordered TOP | Remain policy-gated across repeated runs. Coincidental equality cannot produce equivalence. |

Every reported difference has exactly one compatibility class. Observed value
loss is `lossy`; representation-only mappings are listed as normalization;
unmapped features are `unsupported`; unapproved business choices are
`policy-decision-required`. The 107 ASE seeds remain review obligations: this
increment does not promote ASE evidence into SQL Server qualification.

## Three prospective twin corrections

`ci-unique` now returns `-4` only from its `unique_violation` handler.
`catch-retains-prior-work` returns `-6` from its `division_by_zero` handler.
The r14 XACT_ABORT twin advances its mapped status after the insert succeeds, so
a trigger rollback before that point retains zero; the subsequent arithmetic
error retains `-6`. The unique-index twin uses a top-level procedure to preserve
the first committed insert on an unexpected later error. Each exposes
`tsql_return_code` as an actual integer
result column. The adapter validates a unique, nonempty, consistent return column,
removes that transport column from business results, and compares its value with
the native TDS return status. It never substitutes a desired constant. The original
wrong-twin faults remain and must still be rejected.

R14 adds two prospectively declared setup cases and procedure-level coverage
acceptance. Exact source sites may accumulate across cases; anonymous native
branch fractions may not. See [the final qualification](m0-results-r14.md).

## Remaining authority boundary

An internal `equivalent` verdict is bounded to the observed public fixture,
declared mappings and coverage scope. A public/customer certificate still needs
its Tower release decision. No Tower authority or decision has been fabricated.
Customer error maps, row-count suppression, unordered-choice policies and mLogica
schema mappings remain separate decisions. Security, concurrency and performance
equivalence remain not assessed.

Collector references: [Microsoft Extended Events](https://learn.microsoft.com/en-us/sql/relational-databases/extended-events/quick-start-extended-events-in-sql-server?view=sql-server-ver16)
and [plpgsql_check profiler](https://github.com/okbob/plpgsql_check).
