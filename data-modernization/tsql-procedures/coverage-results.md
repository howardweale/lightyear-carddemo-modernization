# T-SQL measured coverage, mappings and twin corrections — October 7, 2026

**The three requested implementation items are complete and natively tested.
Full M0 acceptance remains unmet.** Operator review; not independent attestation.
Zero model calls. All database execution took place on the approved dedicated
Ubuntu x86_64 VM; no local Windows Docker or B06 resources were used.

## Final comparison

Fresh attempt `010` completed 100 SQL Server/PostgreSQL pairs across 42 procedures
and 25 trap families in **268.064 seconds**, including setup and cleanup.

| Verdict | Pairs | Interpretation |
|---|---:|---|
| Equivalent | 36 | Matching observations and qualified coverage gates passed under the declared public-fixture mappings |
| Divergent | 40 | All 40 non-policy wrong twins rejected |
| Insufficient evidence | 24 | Four non-policy correct twins fail coverage proof; 20 repeated ambiguous-choice cases remain policy-gated |

All 40 non-policy correct twins match the compared observations. The 20 policy
runs comprise five repetitions of each variant for ambiguous UPDATE FROM and
unordered TOP. Ten match and ten differ, but all twenty retain their policy gate.
These repetitions are not independent estimates of an effectiveness rate.

The final 100 pairs independently replayed on Windows without database access:
**1,726 files verified**, including the embedded seven-control qualification.
The separate seven-control archive also replayed, as did all 100 pairs from the
earlier measured attempt `009`. No prior evidence was rewritten.

## Three corrected reference twins

| Twin | Actual SQL Server / PostgreSQL return | Final reference verdict | Wrong twin |
|---|---|---|---|
| `ci-unique` | -4 / -4 | Matching observations; coverage insufficient | Divergent |
| `catch-retains-prior-work` | -6 / -6 | Equivalent | Divergent |
| `xact-abort` | -6 / -6 | Matching observations; coverage insufficient | Divergent |

The PostgreSQL values come from the actual corresponding exception handlers.
The adapter reads and validates the declared return column; it does not inject
an expected result. Wrong variants retain their original semantic mistakes, so
matching return codes alone cannot make them pass.

## Measured coverage and remaining gaps

Native SQL Server XE events are reduced against ScriptDom's actual installed
module spans. PostgreSQL records the plpgsql_check 2.10 profiler. Seven native
controls passed their expected coverage outcomes on both engines: straight path,
both branch edges, missing edge, taken handler, missing handler, scalar declaration
and table-variable declaration. Missing-edge and missing-handler controls are
successful **collector rejections**, not equivalent twins. The handler-hit
control's business return-code discrepancy is preserved separately.

| Held correct twin | SQL statement / branch fraction | PostgreSQL statement / branch fraction | Why held |
|---|---|---|---|
| `ci-unique` | 83.3% / 50% | 100% / 100% | Defensive rethrow path not exercised |
| `xact-abort` | 90% / 50% | 100% / 100% | Only one conditional edge exercised |
| `nested-transaction-rollback` | 100% / 100% | 100% / 50% | Native profiler's aggregate branch result cannot prove every handler |
| `identity-rollback-gap` | 100% / 100% | 100% / 50% | Same conservative handler-proof limitation |

The two PostgreSQL cases contain null handler bodies. The retained profile does
not provide an individual handler identity; 50% does not prove a particular
handler was missed. It does mean the required complete error-path proof is absent.
No coverage waiver or source deletion was used to promote these cases.

Bridge revision 2 explicitly separates uninitialized scalar declarations and
table-variable declarations, for which SQL Server emits no standalone executable
statement event. Their source spans remain in `excluded_declarations`; initialized
declarations and subsequent uses remain measured. Two native controls validate
this prospective change. Attempt `009` remains unchanged at 32 equivalent,
40 divergent and 28 insufficient-evidence.

Coverage is procedural: SQL expression/query-plan branches and dynamic SQL body
branches are excluded. Offline replay recomputes SQL coverage and PostgreSQL
statement coverage. PostgreSQL's native branch fraction is retained and checked,
not independently recompiled. See [the exact contract](coverage-and-mappings.md).

## Explicit mappings

The [public policy register](public-policy-register.json) binds all 42 procedure
profiles to their six source/setup assets and calling conventions. It declares
exact-name schema inference, explicit type and message mappings, native sequence
ownership and consumption, result ordering/multisets, return contracts and
compatibility classifications. Unknown types or mappings remain unsupported;
unapproved business choices remain policy-decision-required. Values are not
trimmed or suppressed to obtain a match.

The 107 ASE ledger seeds remain review obligations. These public-fixture profiles
do not authorize customer policy or certificate release. No Tower decision was
fabricated. Security, concurrency, performance, complete nested PostgreSQL
row-count streams and internal transaction-event histories remain outside this
increment's proof.

## Evidence bindings

| Record | SHA-256 |
|---|---|
| Final native report content | `7ec005f292917b0bc4bd478b024eacb9a88bbeb1d5d6437bce341ea25ec62dce` |
| Recorder public key | `f5bdd5002b137b56f6dd315e4746d9ba336ec14b50f64387811826b3a1cb01f7` |
| Independent final audit file | `463d14ad44b60384cb73e0bf9461f5d711cb4bfbf061111044e165ad7db51d34` |
| Seven-control report content | `d45ac6915421409a5d6966131632735e320fe1c17ba5d2969c1586b48957238a` |
| Seven-control independent audit | `5406ea8c92609a39c9ecc99be27bd37a1cdd585bd23f2af7ec779199c5a86b28` |
| Coverage bridge revision 2 | `46d8195e2ef853c777bc06d3fe3f5146c7bf6a89dd22657c0474fe5b1eca0cd5` |
| Coverage collector | `9188d9d003df70557e0b0322c3934f874b3eece3e4e32164c98540d333c58beb` |
| Public mapping register content | `d121f7fe5b8eaa154a6e944cce443238187ff6e3fff7bb64bda7bcb7018c4d13` |
| Read-only actual cleanup audit | `f3ac5312544c5cf79a77919e463f3d566327147fc3e5ff595c1e12883807618e` |

SQL Server image:
`mcr.microsoft.com/mssql/server@sha256:4402d880dd4c34bfa7d8705e56a86cd6c88da80a1f6bbbe741f999e76264a090`.
PostgreSQL coverage image:
`sha256:b03ef125d79567173ab5622d9c5b05c9baf353a4eb78f8c13a938de4141de30d`.

The signed run's human-readable `claim` still contains the old phrase
“coverage unqualified.” Its bound plan explicitly records qualified coverage,
and its qualification record and per-pair comparisons replay successfully.
The stale label is disclosed here and fixed prospectively in the runner; the
signed report is preserved unchanged. Overall `qualification_passed:false`
remains correct because full M0 acceptance has not passed.

## Preserved development outcomes and costs

| Run | Outcome | Elapsed seconds |
|---|---|---:|
| 006 | Eight pre-call failures: XE error_reported incompatible with selected no-loss session; no candidate calls | 35.710 |
| 007 | First native pair captured; summary failed on wrong profiler field name; stopped | 15.089 |
| 008 | Ten implementation checks, including the three twins and wrong variants; all replayed | 38.255 |
| Controls 001 | Five collector controls passed | 28.002 |
| 009 | First 100-pair measured run, declaration gaps retained | 267.447 |
| Controls 002 | Seven collector controls passed | 30.238 |
| 010 | Final 100-pair comparison | 268.064 |

All seven runs' owned containers, networks and volumes were independently absent
in the read-only VM inventory review. The initial audit helper lacked Docker
socket permission; an elevated invocation then resolved the wrong home directory.
Both checks made no mutation. The corrected helper used the runner's `sudo -n`
Docker access and explicit per-run owner filters. No native pair was rerun for
these audit-helper errors.

Final independent replay took 0.703 seconds; attempt `009` replay took 0.687
seconds and controls `002` took 0.047 seconds. Preparation compilation/image-build
costs are separate from native timings; a complete monotonic preparation total
was not captured. Whole-run elapsed time is not a reset-only benchmark.
**73 scoped offline tests passed.**

The [machine-readable summary](coverage-results-summary.json) records every pair's
coverage, verdict and manifest hash. Original attempts 001–005 remain in the
[historical native report](native-results.md). Raw archives/captures and private
credential directories remain local. No upload, PR or certificate was issued.
