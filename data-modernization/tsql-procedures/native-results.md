# T-SQL M0 native comparison — October 7, 2026

**Native adapters, database capture and offline replay executed. M0 qualification has not passed.**

Operator review; not independent attestation. Zero model calls. All Docker work ran on the approved dedicated `ly-tsql-m0` x86_64 Linux VM in project `lightyear-ms67-nonproduction`. No local Windows Docker commands; no B05/B06, template-r1, work/ms94 or frozen-evidence edits.

## Measured result

| Population | Result |
|---|---|
| Authored procedures | 42 across 25 trap families |
| Full native comparisons | 100, including repeated policy cases |
| Non-policy wrong twins | 40/40 divergent, each tagged with its declared trap family |
| Non-policy proposed correct twins | 37 observed matches; 3 divergent |
| Policy cases | 20 runs: ambiguous UPDATE FROM and unordered TOP, five repeats per variant |
| Independent offline replay | 100/100 pair receipts; 1,205 evidence files verified |
| Equivalent certificates | 0; coverage/mapping admission incomplete |
| Full-run duration | 222.214 seconds, including provisioning, reset, calls, immediate replay and cleanup |

The full run started `2026-10-07T18:58:22.174390Z` and ended `2026-10-07T19:02:04.388574Z`. Native calls began after readiness at 18:58:32Z. A separate six-pair transport smoke passed in 24.883 seconds and independently replayed all six receipts / 77 files. Raw matching outputs are not equivalence certificates.

## Reference discrepancies preserved

| Proposed correct twin | SQL Server TDS return status | PostgreSQL mapped return status | Other compared observations |
|---|---:|---:|---|
| ci-unique | -4 | 0 | Matched |
| catch-retains-prior-work | -6 | 0 | Matched |
| xact-abort | -6 | 0 | Matched |

These are measured implicit return-status differences after handled errors. The comparator did not discard or normalize them. The original source and twin bytes remain unchanged. Correct twins must implement a faithful, explicitly declared return mapping before a fresh qualification can pass.

## Runtime and capture

- SQL Server 2022 Developer CU27, `16.0.4295.3`; image digest `sha256:4402d880dd4c34bfa7d8705e56a86cd6c88da80a1f6bbbe741f999e76264a090`.
- PostgreSQL `16.15`; image digest `sha256:0ea6700a3b4f0ae6ce746519073558aed4d88a79d8d07622a9a644946c7319c4`. This is a provisional target, not a claim about mLogica’s target deployment.
- python-tds 1.16.1, psycopg 3.2.10, cryptography 46.0.3. VM Ubuntu 24.04.5 LTS, x86_64.
- SQL Server: verified CHECKSUM golden backup, fresh restore for each call. PostgreSQL: fresh database from each fixture template. No outer-rollback reset.
- Captures enumerate all ordinary user tables, including trigger targets, raw column metadata, primary keys and row multiplicities; identity/sequence state is retained.
- RPC captures retain result-set order, native metadata and values, OUTPUT parameters, return status, DONE/INFO/ERROR tokens and errors. PostgreSQL captures results, explicit OUT/return mappings, notices and ordered refcursors.
- The refcursor test uses its declared BEGIN/CALL/FETCH/FETCH/COMMIT transaction. Other calls use autocommit. Exit transaction state and visible temporary objects are captured.
- Full SQL Server temp catalogs are retained. Cached/internal objects inaccessible to the caller are not labelled leaked candidate tables; OBJECT_ID visibility is checked.
- Each pair records real UTC times, engine version, session settings, database clock before execution, source/setup hashes, reset method and image bindings.
- Credentials and run-local recorder private keys remain in restricted VM sibling directories outside every evidence archive. They are not Tower signing authorities.

## Replay and cleanup

The terminal manifest hashes every retained evidence file. A separate Windows process verified the externally pinned recorder key and terminal report, signatures, exact file closure, progress/report consistency, image bindings, source/setup hashes and pair-plan bindings. It independently recomputed all-table deltas and comparisons without database or Docker calls.

Containers ran on fresh internal Docker networks without published database ports. Each resource had a unique task owner label. Only exact owned resources were removed. The full run’s two containers, two volumes and network were absent at completion. A later read-only recheck found no resources for any of the five attempt labels (15 successful filtered inventory checks). Images remain cached. The VM remains subject to its approved 12-hour auto-stop.

## Failures and development attempts

| Attempt | Outcome | Seconds | Cleanup |
|---|---|---:|---|
| 001 | No procedure ran: Docker internal network did not publish ports; changed to direct host access to the private bridge | 2.798 | Passed |
| 002 | Six failed adapter slots: empty parameter tuples mishandled literal percent signs; OUTPUT parameter type supplied incorrectly | 22.446 | Passed |
| 003 | Six receipts exposed internal temp-table false positives; token instrumentation also missed direct RPC completion handlers | 28.219 | Passed |
| 004 | Corrected transport smoke: 3 reference matches, 3 intended mutant divergences | 24.883 | Passed |
| 005 | Full corpus: 100 completed pairs, 47 observed matches and 53 observed divergences including policy cases | 222.214 | Passed |

All five attempts remain preserved separately. No failed outcome was replaced. An earlier VM import check caught an omitted shared package before Docker; a subsequent host guard rejected the short hostname before Docker. The fully qualified, verified VM hostname was then supplied explicitly.

## Remaining M0 gates

1. Measure and qualify statement/branch/error-path coverage on both engines. coverage() returns None; no execution count or expected label is substituted for coverage.
2. Correct the three proposed reference twins’ return contracts and rerun them as new evidence.
3. Admit ledger/Tower policies for unordered choices, error/notice severity, and identity/sequence catalog mappings. Raw identities and sequences are captured but their cross-engine mapping is not admitted.
4. Add PostgreSQL nested statement row-count instrumentation and complete internal transaction-event capture. Current captures contain actual TDS tokens and exit transaction state, not a claimed complete cross-engine transaction history.
5. Bind mLogica’s exact compatibility level, collation, target version and extensions on intake; qualify schema/type mappings and dependency closure.
6. Separately measure reset-only monotonic time and broaden boundary cases. The 222.214-second wall duration is a measured whole run, not a reset benchmark.

No customer code/data, native M0 qualification success, production certificate, security equivalence or performance equivalence is claimed.

## Integrity bindings

| Artifact | SHA-256 |
|---|---|
| Signed terminal content | `2c959ed46d0df07843daba0f82d65f95152803f54d939f63cb677ffa1618d23d` |
| Terminal file bytes | `b703601d23c39a45fb0563c71405c4e01fb305f7f1b0df2066e7bd2169d09fe5` |
| Recorder public key | `d2ba91299470034ce7b835d6735a47725a7e2bf0b5954ae5c3819d613277f45a` |
| Independent offline audit file | `1ecf544b0f573852830ef3cd3aac8900f858b846b5658b3b9ab481d2712ddfa5` |
| Actual cleanup recheck file | `2bed20279bf064fa3f5b4334e2b738571c1cddf251d7de318b0092e1acc295a2` |
| Five-attempt archive | `2d66d98f90ed29f03fd045d3578a75306b9e20a3be6a0127e4076be8c585c51a` |

ScriptDom passed all 42 source procedures. The report and three build hashes supplied by Howard were re-read directly on the VM and matched exactly:

- Report `cd1b52a0b76ca508415839b20fbf0bbad4117b257e254cfd74025b573e65cc1a`.
- Bridge `ab4efd62483ef5b4572a7b765a83e1efd60f8d280619e6027706035acf40cf8b`.
- ScriptDom assembly `0c84098c3ceb902677d7f8fe2ed3bd338d88f5b03e0cb577fc6480bbc261ea60`.
- Package lock `c5b9c98f04ae6e36b79006ab1317e48b0abd01cede1af5de27dda276db314aed`.

Local raw evidence is under `work/tsql-m0-transfer/native-evidence/` in the main checkout. The VM retains `/home/howard_weale_gmail_com/tsql-native-attempt-001` through `-005`. Only this hash/count report and the hash-only summary belong in the repository. Nothing was uploaded publicly.

See [native-results-summary.json](native-results-summary.json) for every pair’s hash and outcome.

The executed source bundle is retained as `native-r5.tar.gz`, SHA-256 `1fd14cc6c47c88cb7ad7e1f4c2759f49d592147c08943cd3ba48e3602b89cdec`. After execution, the worktree received documentation/type-annotation clarifications only in `adapters.py` and `native.py`; the executed bundle and plan were not changed. The standalone independent replayer also gained stricter plan/image/input/progress binding checks before the local audit.
