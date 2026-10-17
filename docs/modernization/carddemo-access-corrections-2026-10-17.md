# CardDemo migrated access correction — 17 October 2026

This dated note supersedes the raw-table access and key-shape descriptions in the 16 October next-slice note. Three of five primary keys (CARDDATA, CARDXREF, USRSEC) are PIC X. Their 100,000-record CI sets include low values, high values and mixed bytes. Alternate keys vary across 20,000 values and deliberately repeat.

Both adapters now use the generated typed tables and reconstruct bytes from typed columns. Character columns are bytea with cp037 decoding at the boundary; no printable-only quarantine applies unless explicitly requested by field policy. ISO date interpretation is an explicit copybook-hash/line-bound list, including customer birth date. Original dated receipts remain historical measurements.

VSAM returns CICS RESP names. Generic forward browse starts at the first key greater than or equal to the supplied prefix and continues through the rest of the file. Reverse browse starts at the end of that generic range and continues backwards. DL/I uses PAUTSUM0/PAUTDTL1 path keys and captured twin order, provides GN, and returns GP for missing parentage and AM for read-only inserts. Caller-owned transaction boundaries must clear adapter position.

The CI replay enumerates all forty retained IMS cases. It reports implemented cases, exact returned segment bytes, database after-state and unsupported operations separately. The historical model's DJ responses in cases 07 and 28 are preserved in the result alongside GP/AM corrections required by the work order. GSAM, secondary-index DBDs, checkpoints, restart, routing and native IMS remain unimplemented; they receive no equivalence credit. No result count is claimed before fresh CI finishes.

Sign-on derives offsets and record length from CSUSR01Y. Shared messages come from pinned CSMSG01Y and message literals are checked against COSGN00C. The Python sign-on remains a bounded model. P4 Java services, generated TypeScript screens, P5 browser/API proof and the final durable P6 receipt are separate remaining work; this correction does not claim their acceptance.

The CI gate selects the latest run attempt and waits while dependencies are still running. Old successful heads never satisfy a new head. Historical delivery tests verify measured implementation bytes from their retained Git history instead of requiring current source to equal old source.

Authorized by Howard; performed by Codex. CI-only validation. Unsigned; no activation, real signing, attempt consumption or Phase 2 execution. Merge requires Howard's approval of the exact final green commit.
