# Oracle dialect authority corpus

This directory contains the bounded Oracle-owned source corpus acquired for MS #49. The source is
the official Oracle Database Sample Schemas release `v23.3`, pinned at commit
`e3325a83e56c516815844025418a96ecaf219751`.

Only the active Customer Orders, Human Resources, and Sales History schema definitions,
representative HR stored logic, schema documentation, repository documentation, and license are
copied. Bulk population data, installers, uninstallers, and archived schemas are deliberately
excluded. This keeps the repository small while preserving the authoritative type and schema
surface needed to ground the first dialect fixtures.

## Acquire or verify

```bash
git clone --depth 1 --branch v23.3 --no-tags \
  https://github.com/oracle-samples/db-sample-schemas.git /path/to/oracle-schemas-v23.3
python3 tools/acquire_oracle_dialect_corpus.py \
  --source-root /path/to/oracle-schemas-v23.3
python3 tools/acquire_oracle_dialect_corpus.py --verify
```

Acquisition refuses a dirty checkout, a different commit or tree, a source hash mismatch, or an
unexpected target file. Verification is offline and content-addresses every copied file.

## Evidence boundary

These files are Oracle-authored schema and example sources. Their presence establishes corpus
identity and dialect relevance; it does not establish that LIGHTYEAR executed Oracle Database.
The MS #49 local fixture receipt is a deterministic model execution. The accompanying native SQL
is executable on an authorized Oracle instance, but native execution remains false until a
separate receipt records it. iDempiere equivalence, iDempiere-to-CloudBank mapping, customer
behavior, migration completion, and production readiness remain false.
