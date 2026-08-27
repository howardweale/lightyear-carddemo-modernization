# PL/I discovery conformance lab

This lab measures the static-discovery subset implemented by `lightyear.pli` v1.2. It is synthetic
test evidence, not a claim of IBM Enterprise PL/I compatibility.

## Evidence set

- `support-matrix.json` publishes the exact supported construct categories and explicit exclusions.
- `corpus/manifest.json` binds 27 sorted, uniquely addressed synthetic cases.
- `golden-results.json` records recognized constructs, references, diagnostics, and source locations.
- `coverage.receipt.json` binds the graph, matrix, manifest, golden result, checks, and claim boundary.

Run `./pli-conformance.sh verify` from the repository root. Verification rebuilds both generated
artifacts, compares them byte-for-byte, runs adversarial tests, and rejects graph drift, tampering,
or any attempt to promote static corpus evidence to runtime or mainframe equivalence.

## Supported subset

The measured subset covers main and internal procedures, scalar and decimal declarations, levelled
structures, includes, entries and `OPTIONS(COBOL)`, fixed/varying records, bounded embedded SQL and
SQLCA, `READ FILE`/`WRITE FILE`, static calls, assignments, condition/error control, and discovery-
level CICS and IMS references.

Unsupported constructs are not silently skipped. The current explicit gaps include storage models
such as `BASED` and `CONTROLLED`, generic entries, packages, preprocessors other than `%INCLUDE`,
dynamic call targets, arbitrary SQL/EXEC grammars, macro expansion, type inference, compiler
semantics, and all runtime behavior.
