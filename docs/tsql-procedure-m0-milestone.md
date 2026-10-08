# T-SQL procedure verification: native implementation milestone

October 7, 2026. Operator review; not independent attestation.

## PR269 review follow-up

The [fresh review result](../data-modernization/tsql-procedures/review-results.md)
supersedes the current implementation counts below: 43 procedures, 26 families,
108 native pairs, all 108 independently replayed on Linux and Windows; actual
owned-resource absence verified. All 43 wrong variants were rejected; 41 correct
variants met aggregate gates and two remain policy-gated. ORDER BY and AST-derived
policy routing close the reported false-acceptance paths. Named typed invocation,
fresh per-case reset, pinned/read-back collation/compatibility, error/type contracts,
SEQUENCE capture and per-pair intake refusal are implemented. 89 T-SQL offline
tests and 18 Tower registry tests pass. Zero model calls.

Collector revision 2 is now [natively qualified on nine controls](../data-modernization/tsql-procedures/coverage-v2-results.md),
including non-dbo schema capture and view exclusion. All nine controls and six
fresh consuming comparison pairs replayed on Linux and Windows; actual owned
cleanup passed. The consumption check produced three equivalent correct cases
and three divergent wrong cases. The current offline suite passes 93 tests.
Earlier failed attempts remain preserved. Case proposal/shrink APIs and Tower
policy verification remain offline-tested, without customer qualification.
Full customer dependency closure and release remain gated. The following is the
preserved earlier milestone, not the current run's results.

Implemented ScriptDom inventory, native SQL Server/PostgreSQL adapters, fresh
backup/template resets, all-table and protocol capture, signed evidence and
database-free replay. The public corpus covers 42 procedures and 25 trap families.
Explicit asset-bound mappings and native procedural coverage are implemented.
The three return-contract twins have prospective corrections with new evidence;
all original failures and source bundles remain preserved.

The fresh approved-VM run completed 104 pairs and passed procedure-level M0
acceptance: 40 non-policy correct twins equivalent across their declared cases,
40 corresponding wrong twins rejected in the correct trap family, and two
ambiguous-choice families routed to policy review (both variants). All 104 pairs
passed independent offline replay, bound to the earlier seven-control native
coverage qualification. Actual
owned containers, networks and volumes were absent. The scoped offline suite
passed 77 tests.
Zero model calls; no Windows Docker or B06 resource use.

**Public-corpus M0 qualification passed.** Pair verdicts remain 38 equivalent,
41 divergent and 25 insufficient-evidence: coverage is also evaluated at procedure
level across the prospectively declared fresh cases, without changing any pair
verdict. Twenty repeated ambiguous-choice cases remain policy-gated. Customer
policies and certificate release remain separate approvals; security, concurrency
and performance equivalence are outside this M0 claim.

Native execution and cleanup took 286.619 seconds (21.77 pairs/minute). Mean
reset-only time was 0.771 seconds for SQL Server and 0.063 seconds for PostgreSQL.
Runs 011 and 012 preserve the added-case mismatches that led to the final reference
corrections; neither was overwritten or promoted to a pass.

- [M0 final results and exact hashes](../data-modernization/tsql-procedures/m0-results-r14.json)
- [M0 qualification interpretation and preserved failures](../data-modernization/tsql-procedures/m0-results-r14.md)

- [Native results, costs, limitations and full hashes](../data-modernization/tsql-procedures/coverage-results.md)
- [Every pair's verdict, coverage and manifest hash](../data-modernization/tsql-procedures/coverage-results-summary.json)
- [Coverage and mapping contract](../data-modernization/tsql-procedures/coverage-and-mappings.md)
- [Historical original native results](../data-modernization/tsql-procedures/native-results.md)

Publication contains implementation, authored public fixtures and hash-only result
summaries. Raw archives, database captures, VM credentials and recorder private
keys are excluded. CI repeats the offline public-fixture suite on Linux and Windows;
it does not launch native database qualification or call a model.


## PR273 review completion increment — October 8 UTC

The revised executor adds conservative EXEC/dynamic-result refusal, per-result ordering and tied-row comparison, source/twin policy obligations, broader exact table-value contracts, expanded native error mappings, all-module dependency captures, Tower-bound float tolerance, generated typed inputs and bounded failure-preserving shrinking. All 43 public procedures now have unique names and typed arguments in a prospective corpus; historical assets remain intact. PostgreSQL locale/timezone and SQL Server compatibility levels are explicit.

The fresh nine-control coverage-v2 check passed independent replay. A separate full native seed run completed 108 pairs (57 observable matches, 51 divergences) and cleaned up, but its original finalization failed on case labels. That report remains failed. A corrected versioned offline finalizer binds signed assets and actual argument hashes; ten procedure/variant outcomes remain unresolved. Therefore full requalification and mLogica readiness are not claimed. See [native review results](../data-modernization/tsql-procedures/native-review-r2.md) and the hash-only audits for every preserved attempt.

Finalization tests reject changed record bindings, missing cases and duplicates. The latest T-SQL suite has 111 passing tests. The earlier combined run covered 486 tests, 15 skipped and no failures; the extra finalization test was then added and included in the 111-test rerun. No model calls or local Docker execution occurred. Real database execution used only the approved dedicated Linux VM.

A separate generated-input/shrinking integration completed 92 native pairs (54 observable matches, 38 divergences), with independent replay and verified cleanup. Full results and costs are recorded in the linked native review report. No synthetic trace is presented as native evidence.


## PR277 review completion - October 8 UTC

Fresh revision 9 qualification passed 86/86 expected procedure/variant outcomes across 108 native pairs. All archives independently replayed; nine coverage controls, eight ordering controls and an 18-pair generated/shrink integration were also verified. Prior failed revision 8 remains preserved. The dedicated VM was stopped after 3767.859 seconds (about 63 minutes), within the approved four-hour limit. Zero model calls and zero local Docker commands. [Results, exact hashes and limitations](../data-modernization/tsql-procedures/review-r3/README.md).

Publication CI: the dedicated T-SQL Linux and Windows jobs passed. The first full Linux suite ran 2,731 tests and found one missing optional parser dependency; its workflow now installs the same tsql extra before the full suite. No qualified implementation, source bundle or native evidence was changed.
