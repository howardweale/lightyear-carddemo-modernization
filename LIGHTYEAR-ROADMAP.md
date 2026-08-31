# LIGHTYEAR qualification roadmap

This is the governing sequence after the source-only pilot planning milestones. Generated
development cells are planning scopes; they are not evidence that a language or platform is
production-qualified.

| Milestone | Scope | Status |
|---|---|---|
| MS #33 | Database Semantic Core | Complete |
| MS #34 | Oracle to PostgreSQL Proof | Complete |
| MS #35 | DB2 Semantic Adapter Hardening | Corrected by MS #35.1 |
| MS #35.1 | DB2 Semantic Adapter Hardening | Complete |
| MS #36 | COBOL Qualification Hardening | Complete |
| MS #37 | PL/I Qualification Hardening | Complete |
| MS #38 | JCL Qualification Hardening | Complete |
| MS #39 | VSAM/CICS Qualification Hardening | Complete |
| MS #40 | IMS Qualification Hardening | Complete |
| MS #41 | HLASM Qualification Hardening | Complete |
| MS #42 | Integrated Pilot Qualification | Complete |
| MS #43 | Oracle Source and Stored-Procedure Qualification | Complete |
| MS #44 | Milestone Documentation System | Complete |
| MS #44.1 | Searchable Milestone Index Reliability | Complete |
| MS #45 | SAP ASE Semantic Source Adapter | Complete |
| MS #46 | Unified Estate Operator Navigation | Complete |

The v0.35.0 stored-logic qualification core is retained as supporting MS #34 evidence. It does not
replace the planned DB2 milestone.

## Governing compatibility classifications

Every schema, data, query, transaction, CDC, and operational transformation must resolve to exactly
one classification:

- `exact`
- `normalized-equivalent`
- `policy-decision-required`
- `lossy`
- `unsupported`

Unresolved policy and loss block equivalence. Unsupported behavior must be excluded explicitly from
the claim scope and cannot be silently treated as migrated.
## MS #37 — PL/I Qualification Hardening

MS #37 governs the existing bounded PL/I evidence through a five-class compatibility ledger and ten
independent qualification gates. It qualifies the supported static and development subset while
keeping general Enterprise PL/I, IBM compiler, z/OS runtime, mainframe-equivalence, and production
claims blocked pending authorized native evidence and representative customer-estate coverage.

## MS #38 — JCL Qualification Hardening

MS #38 binds the pinned JCL estate and a 30-case synthetic conformance corpus to a five-class
compatibility ledger and ten independent gates. It qualifies bounded static discovery and parsing
while keeping native JCL, JES, catalog/SMS, scheduler, restart, z/OS runtime, mainframe-equivalence,
and production claims blocked pending authorized native execution evidence.

## MS #39 — VSAM/CICS Qualification Hardening

MS #39 binds the canonical CICS and VSAM graph inventory, the existing read-only `CAVW`
differential proof, and a 38-case synthetic semantic corpus to a five-class compatibility ledger
and eleven independent gates. It qualifies a bounded development subset across KSDS, ESDS, RRDS,
alternate indexes, PATHs, access and mutation commands, file status, browsing, locking, syncpoint,
BMS, and program control. Native CICS-region and VSAM-catalog behavior, LDS record access, RLS,
queues, journals, recovery, mainframe equivalence, and production readiness stay blocked pending
authorized native evidence.

## MS #40 — IMS Qualification Hardening

MS #40 binds the canonical IMS graph inventory, the existing `CBPAUP0C` expiry-purge differential
proof, and a 40-case synthetic semantic corpus to a five-class compatibility ledger and eleven
independent gates. It qualifies a bounded development subset across DBDs, PSBs, PCBs, HIDAM,
secondary-index and GSAM boundaries, hierarchical navigation, SSAs, DL/I status codes, segment
mutation, checkpoint, restart, rollback, and scheduling boundaries. Native IMS-region scheduling,
IMS TM, Fast Path, DBRC, logging, restart/recovery equivalence, mainframe equivalence, and
production readiness stay blocked pending authorized native evidence.

## MS #41 — HLASM Qualification Hardening

MS #41 binds the canonical two-program HLASM graph inventory, the existing `COBDATFT` date
differential proof, and a 40-case synthetic semantic corpus to a five-class compatibility ledger
and eleven independent gates. It qualifies a bounded development subset across DSECT fields,
storage operations, condition codes, branches, register operations, save-area mechanics,
addressability, COPY, static macro expansion, literal-pool boundaries, and parameter handoff. Native
HLASM assembly and object code, binder and load-module behavior, AMODE/RMODE, LE/COBOL linkage,
STIMER and authorized services, storage protection, recovery, broad instruction behavior,
mainframe equivalence, and production readiness stay blocked pending authorized native evidence.

## MS #42 — Integrated Pilot Qualification

MS #42 composes the five independently qualified technology subsets into the exact `ACCOUNTV`
pilot selected in MS #32. The graph-bound qualification covers six source files, five cells, five
coordination dependencies, three integrated paths, a deterministic 40-case corpus, ten bounded
acceptance-evidence items, and a 30-entry five-class compatibility ledger. It makes Wave 2
integrated development evidence ready without admitting a factory work order. All 15 live-evidence
items remain blocked; factory dispatch, native compilation and execution, mainframe equivalence,
production release, and production readiness remain false pending authorized evidence.

## MS #43 — Oracle Source and Stored-Procedure Qualification

MS #43 upgrades the bounded Oracle-to-PostgreSQL mechanism with a genuine Oracle `SourceAdapter`,
SCN-bound CDC resume, source profiling and extraction contracts, a five-class semantic ledger, and
an eight-gate source-to-target qualification. It also qualifies four declared PL/SQL procedures
through deterministic PL/pgSQL translation and 20 result, side-effect, row-count, exception,
decimal, null, empty-string, and mutation cases. Dynamic SQL, autonomous transactions, package
state, database links, and procedure-owned commits remain excluded. Native database execution,
live redo, general stored-logic completion, database migration completion, and production readiness
stay blocked pending authorized evidence.

## MS #44 — Milestone Documentation System

MS #44 publishes MS #1 through MS #44 as one governed customer-readable body of record. Each
milestone has matching Markdown, Microsoft Word, and PDF editions covering purpose, customer value,
delivered capability, evidence posture, relationship to earlier work, limitations, and safe claim
language. A deterministic generator and 132-artifact content manifest fail closed on source drift,
missing or modified output, and undeclared milestone files. The documentation packages existing
evidence but does not create new technical qualification, live execution, platform equivalence, or
production-readiness evidence.

## MS #44.1 — Searchable Milestone Index Reliability

MS #44.1 corrects the customer access path for the milestone library. It adds a responsive,
client-side search and roadmap-phase filter, publishes the index through GitHub Pages, replaces
context-dependent relative format links with absolute GitHub links, and makes Word links direct
downloads. Search covers customer-readable milestone metadata and narrative fields; it does not
search customer source code or replace underlying receipts, ledgers, tests, or policy evidence.

## MS #45 — SAP ASE Semantic Source Adapter

MS #45 implements a genuine target-neutral SAP ASE `SourceAdapter` and broad semantic-loss analysis.
The bounded catalog covers 2 tables, 31 columns, 4 UDTs, 2 identity columns, 5 constraints, 3
indexes, 6 procedures, 4 triggers, and multiple ASE locking schemes. A 187-case corpus provides
depth across datatypes, identity, money, datetime, empty strings, Transact-SQL, stored logic,
transactions, rollback, locking, replication order, and resume. A 107-entry five-class ledger and
twelve gates qualify the source adapter and analysis while keeping live ASE observation, target
selection, target migration qualification, native stored-logic execution, database-migration
completion, and production readiness false. The ASE-to-PostgreSQL or ASE-to-Oracle proof will follow
a real pilot choice.

## MS #46 — Unified Estate Operator Navigation

MS #46 gives an operator one customer-centered way to move between unified-estate, mainframe, and
database views without splitting the dependency graph into disconnected products. Customer,
technology scope, and operator lens are separate controls. Scope visually emphasizes the selected
technology while retaining connected nodes that explain cross-platform impact; SAP estate and
security-vulnerability views remain explicitly planned.

The new trace workflow follows directed source-to-target semantics or, when deliberately selected,
an undirected related-evidence path. It reports hop count, platforms, static evidence class,
customer boundary, and runtime boundary. Committed examples demonstrate COBOL-to-DB2 writes and
source-backed COBOL-to-IMS `DLET` paths. A separate `AUTHUPD1` fixture demonstrates PL/I-to-DB2
write extraction and is explicitly labeled non-customer reference evidence; `ACCTPL1` remains a
read path. Oracle and SAP ASE adapter qualifications remain outside the graph, so the UI reports
their missing projection and customer integration edges rather than inventing an Oracle-to-
mainframe transaction path. Live execution, customer equivalence, and production readiness remain
false.
