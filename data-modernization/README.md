# Database semantic adapters and AUTHFRDS proof cell

MS #45 adds a genuine, target-neutral SAP ASE source adapter with deliberately broad semantic
coverage. Its customer-shaped catalog contains two related tables, 31 columns, four user-defined
datatypes, two identity columns, five constraints, three indexes, six procedures, four triggers,
and both `datarows` and `datapages` locking. Discovery, privacy-preserving profiling, exact bounded
extraction, transaction capabilities, and content-bound replication resume all use the shared
database semantic-core contracts.

Depth is governed rather than inferred. A 107-entry compatibility ledger uses all five classes
(`exact`, `normalized-equivalent`, `policy-decision-required`, `lossy`, and `unsupported`), while a
187-case deterministic corpus covers the ASE type system, UDTs, money and datetime boundaries,
empty-string and character behavior, `IDENTITY`, locking and rollback, replication order and
resume, Transact-SQL, stored procedures, and triggers. Twelve independent gates fail closed if the
catalog, classifications, corpus, adapter contracts, receipt bindings, or safety boundaries drift.

This is a source-adapter and semantic-loss qualification, not a completed migration. No target is
selected. Live ASE catalog, data, log, locking, transaction, or native stored-logic evidence is not
present; ASE-to-PostgreSQL and ASE-to-Oracle remain future pilot qualifications. Stored-logic
inventory is deep, but native stored-logic equivalence, arbitrary application SQL, full database
migration, cutover, and production readiness remain false.

MS #43 adds a genuine Oracle source adapter and a separately gated stored-procedure subset. Four
declared PL/SQL procedures are inventoried, translated to bounded PL/pgSQL, and exercised through
20 deterministic result, side-effect, exception, row-count, decimal, null, empty-string, and
mutation cases. This supports development qualification for the declared subset; it does not claim
a complete Oracle catalog inventory or native source/target equivalence.

MS #35.1 corrects the roadmap alignment by implementing DB2 as a genuine semantic-core source
adapter. Its discovery, profile, source compatibility ledger, and conformance receipt are committed
under `db2-semantic-adapter/`. These are source-only and synthetic-fixture artifacts; they do not
claim a live Db2 catalog, log stream, or z/OS equivalence.

MS #35 adds an independent stored-logic qualification core. It inventories database-resident and
application SQL separately and requires live catalog, source, deployment, scheduler, and privilege
evidence before inventory can be complete. Zero discovered procedures or triggers is not proof of
absence. The canonical artifact is `stored-logic/authfrds.qualification.json`.

MS #34 applies the semantic core to a progressively gated Oracle-to-PostgreSQL proof. The canonical
artifact is `oracle-postgresql-proof/authfrds.proof.json`. Its eight gates deliberately distinguish
development mechanisms, simulations, unresolved policy, and excluded stored logic. A passed proof
means the contract is deterministic and honest; it does not mean the database migration is complete.

MS #33 turns the original AUTHFRDS implementation into a reusable database semantic core. Database
adapters must project through the canonical type system and satisfy the same profiling,
transformation, normalization, comparison, CDC, cutover, rollback, and conformance contracts.

The compatibility ledger is the authority for semantic differences. It classifies every bounded
column and behavior as `exact`, `normalized-equivalent`, `policy-decision-required`, `lossy`, or
`unsupported`. A policy decision cannot be silently auto-accepted, loss blocks equivalence, and an
unsupported item is excluded from the claim scope. The declared stored-procedure subset now has
its own qualification; triggers, arbitrary application SQL, DDL replication, sequence-state
transfer, and general PL/SQL remain separately gated.

This bounded v0.19.2 vertical slice translates the AWS CardDemo Db2 for z/OS `CARDDEMO.AUTHFRDS` contract to PostgreSQL and Oracle while retaining source lineage and explicit evidence gaps.

## What is proven

- deterministic parsing of the 26-column Db2 DDL, composite primary key, unique index, DCL, and COPAUS2C embedded INSERT/UPDATE SQL;
- a target-neutral canonical data model plus PostgreSQL 16 and Oracle Database 26ai Free adapters;
- fixtures covering CP037 EBCDIC, packed and zoned decimal, dates, nulls, and fixed-width text;
- fail-closed exact live comparisons for column metadata, constraints, index order, normalized rows, checksums, queries, commit, and rollback;
- an HMAC-signed **development** receipt whose signer is intentionally labeled as a fixture;
- an on-demand Docker PostgreSQL proof using no network, a read-only root, dropped capabilities, and ephemeral tmpfs storage;
- an Oracle Free proof using no network or published ports, ephemeral credentials, dropped capabilities, and an honestly recorded writable-root exception required by the database image;
- a multi-target aggregate receipt that fails unless both target receipts pass.
- a five-event Db2-shaped change journal covering inserts, updates, and deletes;
- interruption and content-addressed resume with duplicate replay suppressed idempotently;
- normalized source-to-PostgreSQL-to-Oracle dual-target reconciliation;
- an exact, development-only human approval barrier before simulated cutover;
- injected post-cutover divergence followed by exact pre-cutover rollback;
- bounded fixture-event RPO and deterministic recovery-step RTO evidence.

## Run

macOS/Linux:

```bash
./data-modernization.sh verify /path/to/aws-carddemo
./data-modernization.sh live-postgres
./data-modernization.sh live-oracle
./data-modernization.sh live-all
PYTHONPATH=src python3 -m lightyear_data verify-semantic-core
PYTHONPATH=src python3 -m lightyear_data verify-oracle-postgresql-proof
PYTHONPATH=src python3 -m lightyear_data verify-stored-logic-qualification
PYTHONPATH=src python3 -m lightyear_data verify-db2-semantic-adapter
PYTHONPATH=src python3 -m lightyear_data verify-oracle-source-qualification
PYTHONPATH=src python3 -m lightyear_data verify-oracle-dialect-corpus
PYTHONPATH=src python3 -m lightyear_data verify-oracle-semantic-coverage
PYTHONPATH=src python3 -m lightyear_data verify-oracle-core-sql-coverage
PYTHONPATH=src python3 -m lightyear_data verify-oracle-plsql-coverage
PYTHONPATH=src python3 -m lightyear_data verify-sap-ase-source-adapter --project-root .
./data-modernization.sh oracle-coverage
./data-modernization.sh oracle-core-sql
./data-modernization.sh oracle-plsql
./data-modernization.sh ase-source
./migration-rehearsal.sh verify /path/to/aws-carddemo
```

Windows PowerShell:

```powershell
.\data-modernization.ps1 verify C:\path\to\aws-carddemo
.\data-modernization.ps1 live-postgres
.\data-modernization.ps1 live-oracle
.\data-modernization.ps1 live-all
.\data-modernization.ps1 oracle-coverage
.\data-modernization.ps1 oracle-core-sql
.\data-modernization.ps1 oracle-plsql
.\data-modernization.ps1 ase-source
.\migration-rehearsal.ps1 verify C:\path\to\aws-carddemo
```

For a customer-controlled signature, set `FACTORYDARK_DATA_EQUIVALENCE_KEY` and run `sign`.
After `live-all`, the command signs the multi-target aggregate; otherwise it signs the PostgreSQL
receipt. Never commit that key.

## Honest boundary

The Oracle runner defaults to the official locally built `oracle/database:23.26.1-free` image. Follow
Oracle's official container-image instructions and accept the applicable license before running it.
The image supports Oracle Database Free on ARM64, but startup is materially slower than PostgreSQL.

`production_ready` remains `false`. The cell has not observed a live Db2 catalog or log, customer
data, z/OS transaction behavior, or a real cutover. CDC, dual-run, approval, failure, rollback, RPO,
and RTO are now rehearsed only against deterministic offline projections. The current source
lineage is COBOL-specific for the AUTHFRDS slice; Oracle empty-string semantics still require live
data profiling.

## Scope confirmation

| Capability | v0.19.2 status |
|---|---|
| Parse Db2 DDL, DCL and bounded embedded SQL | Passed for AUTHFRDS/COPAUS2C; not a general Db2 parser |
| Graph tables, columns, indexes, constraints and SQL | Passed for this vertical slice |
| Connect source logic to reads/writes | COBOL paragraph lineage passed; PL/I not present in this slice |
| Target-neutral canonical model | Passed for AUTHFRDS |
| PostgreSQL and Oracle generation | Passed deterministically |
| EBCDIC, packed/zoned decimal, dates, nulls, fixed width | Covered by representative fixtures |
| Live target containers | On-demand; receipt exists only after each target actually runs |
| Exact schema/data/query/transaction comparison | Implemented fail-closed for both targets |
| Signed equivalence | Development HMAC and customer-key signing mechanism; no production key is shipped |
| Control Tower lineage/gaps/equivalence | Side-by-side target projection implemented |
| Offline CDC, interruption and resume | Passed for a five-event deterministic journal |
| Dual-target reconciliation | PostgreSQL- and Oracle-shaped projections converge exactly |
| Cutover approval | Simulated human, plan-bound, development-only; no production authority |
| Rollback | Injected divergence detected; exact pre-cutover identities restored |
| RPO/RTO | Zero fixture events and three recovery steps; no production timing claim |
| Database semantic core | Canonical types, adapters, profiling, transformations, rows, comparisons, CDC, cutover/rollback, and conformance passed |
| Compatibility ledger | 52 column mappings plus behavioral boundaries; unresolved policy decisions block equivalence |
| Stored logic | Four declared procedures pass a bounded separate qualification; triggers, arbitrary application SQL, live catalog completeness, native equivalence, security and operability remain open |
| SAP ASE source adapter | Two-table, 31-column catalog; 107 classified semantic entries; 187 deterministic cases; source-only development qualification |
| SAP ASE stored logic | Six procedures and four triggers inventoried and classified; native execution and migration equivalence remain open |
