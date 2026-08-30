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
| MS #37 | PL/I Qualification Hardening | In progress |
| MS #38 | JCL Qualification Hardening | Planned |
| MS #39 | VSAM/CICS Qualification Hardening | Planned |
| MS #40 | IMS Qualification Hardening | Planned |
| MS #41 | HLASM Qualification Hardening | Planned |

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
