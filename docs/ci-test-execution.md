# Python test execution and skip reporting

Work-order R2/C1 adds an execution ledger to the full Python unittest discovery
already run by `verify.sh` and `verify.ps1`. It does not replace or summarize the
later Java, verifier CLI, or differential commands. Those commands retain their
own exit-status gates. The static test-collection check remains separate.

Each Linux and Windows differential-verification job uploads
`python-test-execution-<OS>-<run>-<attempt>` containing `report.json` and
`report.md`, including after a test failure. The job summary shows the counts
and every skip. Missing reports fail the upload step; neither a missing report
nor a successful artifact upload establishes that verification passed.

The JSON binds the checkout, PR head when present, workflow run/attempt/job,
Python/platform, policy hash, and discovered test-source hashes. It records
every discovered test, whether it started, duration when available, outcomes,
fixture events, subtest events, and exact skip reasons. Fixture skips explain
unstarted tests; failed fixtures and aborted runs cannot produce acceptance.
Counts partition discovered tests. A partially skipped subtest case counts as
skipped, never as passed. Expected failures are reported and rejected.

`tools/ci/test-skip-allowlist.json` lists permitted skips for this full-discovery
job only. Each allowance has an exact test or class identity, literal reason,
platforms and rationale. No glob or reason regex is accepted. The source file
hash binds class entries to their reviewed tests; changing a bound source
requires reviewing its allowances. An allowance permits a skip but does not
cause one, and unused allowances do not prevent an optional test from running.

Existing platform-only, explicit native-environment, retained local-evidence,
optional SDK and dedicated integration skips remain visible. These allowances
are not evidence that the corresponding native or dedicated tests ran. Missing
mandatory JDKs, installed signing/parser dependencies, pinned upstream fixtures,
or a newly introduced skip fail the report. A CI failure must be diagnosed;
do not automatically add its reason to the allow-list.

The full unittest loader retains its default `test*.py` discovery and executes
the suite once. CI fixtures verify success, failure, import errors, fixture
skips/errors, subtest skips/failures, expected/unexpected success, interruption,
duplicate discovery and exact policy matching. Reports are CI artifacts;
no execution result is committed or inferred from static preparation.
