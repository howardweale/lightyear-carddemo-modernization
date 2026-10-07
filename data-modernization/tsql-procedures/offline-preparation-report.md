# T-SQL M0 offline preparation report

Date: 2026-10-07. Operator review; not independent attestation.

Branch: `codex/tsql-procedure-m0`.
Base: `92a497744d7093dde3c3a557fbfda99378613754`.
See [scope, limitations and first-VM proposal](README.md).

## Verified in this increment

- 38 new offline unit tests passed.
- 39 existing semantic-core, stored-logic and SAP ASE tests passed.
- Combined run: **77 tests, zero failures, zero errors**.
- Python source syntax checks passed.
- Regenerated public corpus/ledger assets match all 254 checked-in generated files byte for byte.
- Corpus closure: 42 source procedures, 42 proposed correct twins, 42 wrong twins,
  all 25 trap families and six hash-bound SQL assets per procedure.
- ASE provenance closure: all 107 ledger entries retained as unverified SQL
  Server review obligations; no ASE classification or decision treated as native
  SQL Server evidence.
- Inventory CLI tests verified private/public separation, missing-input refusal,
  explicit unparsed accounting and no overwrite of an existing output directory.
- Parser tests use mock protocol responses. They are not real ScriptDom or
  sqlglot integration qualification.

The first sandboxed unit-test invocation could not read/write its temporary
directories (Windows error 5). Re-running with task-local temporary files and
the managed-worktree filesystem permission passed. No test assertion was
weakened for that environment error.

## Artifact bindings

| Artifact | File SHA-256 | Content SHA-256 |
|---|---|---|
| corpus.json | `5639f202c43a9fe53d5b61734ff1100fd871a5a5945da563a810b19f8dba7d48` | `0f39716b4190078fdfe479568682568d4cfa348d43bf7f7ec47b4b3fbe86a39b` |
| compatibility-ledger.json | `76b98afcad991864093b374ab6c671ba718155438d7f3eae1117d8f8124d273a` | `5a5e4aef3dc6119104ada1170d66a9e968967fac7063294ceabacd5629ad6f9a` |

These hashes are integrity bindings, not signatures or native receipts.

## Execution and readiness

Docker commands: **0**. Native pairs: **0**. Model calls: **0**.
No dependencies downloaded. No B05/B06, template-r1, work/ms94 or frozen-path
changes were made by this task.

The offline corpus, inventory and adapter interfaces are ready for the first
approved Linux VM integration spike. They do **not** constitute an executable
native qualification runner: driver/capture/reset backends, real parser build,
coverage collectors, approved mappings, signed native receipts/replay and Tower
policy integration remain to be completed.

No VM has been approved or provisioned by this increment. There is no admitted
image digest, measured restore time, cases/minute estimate or native equivalence
result. No container should be started from this report.

Full M0 acceptance remains pending. In particular, ambiguous UPDATE FROM and
unordered TOP must retain their policy gates; no coincidental match is a pass.
