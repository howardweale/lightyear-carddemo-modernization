# R3: staged re-verification under pglast 7.20 — 2026-10-21

Stage A requests fresh public-corpus and comparator verification under exactly
pglast 7.20. This record is a request, not a passing result. CI emits a dated
result note and source-bound report for each Linux/Windows checkout. Once
verified, publish the actual CI result as a new dated record; retain this request.

The complete existing test_tsql*.py suite remains mandatory. Empty discovery,
skips, expected failures and errors fail the run. Both current PostgreSQL contract
parsers process all 43 public procedures' correct/wrong targets, preserving
every policy obligation and source binding. CI records checkout, PR head, run,
attempt, parser version and each test result. Synthetic export fixtures run
only in CI. Public-corpus verification cannot complete Stage B.

The historical revision-9 86/86 expected procedure/variant outcomes were measured
with the earlier parser, across 108 native pairs (55 matches, 53 divergences).
They are not 108 equivalence certificates and are not a pglast 7.20 result.

Stage B must independently re-verify all 108 unchanged historical native capture
pairs under pglast 7.20 in read-only CI. Howard authorizes archive reads for this
job only: no writes to retained evidence, new native runs, database/model calls
or adjustments of expected outcomes. Report any outcome or contract difference
pair by pair and publish a new dated record. Until then, new material citing
86/86 must identify it as measured with the earlier parser.

No CI-readable archive exists yet. The reviewed operator export procedure is
[docs/tsql-r9-export.md](../../../docs/tsql-r9-export.md). Howard runs it on
ly-tsql-m0, reviews identifiers, transfers the immutable package through IAP,
stops the VM and uploads Release tsql-r9-evidence-2026-10-21. The exporter binds
the exact historical report content hash, public-key byte hash and 1,889 signed
file entries (1,890 including report.json), refuses extras/secrets, and emits
per-file and package hashes. It never accesses a recorder private key.

Stage B remains unstarted until Howard posts the Release asset name and SHA-256
on the PR. Bind the exact asset and verify all bytes before CI reads them.
Original receipts, historical dated records and generated status remain unchanged.
No local installation, startup, export, replay or model calls are authorized.
