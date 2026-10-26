# Ten public procedure/twin pairs — readiness draft

The new harness prepares native execution and receipt generation for ten existing authored public SQL Server/PostgreSQL pairs. **No new native pair has been executed or verified by this draft yet.** Contract-test success is not SQL Server/PostgreSQL equivalence. No mLogica procedure, customer fixture, Maintec data or private capture is an input.

The fixed selection covers LEN, integer division, ISNULL length, DATEDIFF day/year, negative ROUND precision, MONEY scale, BIT, UUID case and trailing VARCHAR spaces. Each includes the public correct twin and deliberately wrong twin. [selection.json](selection.json) pins the whole typed corpus and exact IDs; intake also checks every selected source/setup/twin hash before a database operation. A changed corpus needs review and a new pin, not a `public_fixture` label alone.

## Intake format

One procedure entry reuses the existing typed corpus contract: unique `id`; `assets` descriptors for source, correct twin, wrong twin and their setups (`path`, LF-normalized SHA-256); typed named parameters; source/target calling convention; ordered declared cases and repeats; session settings; reset state; coverage thresholds; and explicit policy obligations. The fixed public selection rejects missing/duplicate IDs, absent assets, path escape, hash drift and unsupported extra coverage scenarios.

A future customer intake must additionally bind the SQL Server version, compatibility/collation, target engine/version, schema/dependency closure, execution/security context, transaction behavior, result ordering, OUT/RETURN mapping, errors, row-count policy and owner-approved semantic choices. It belongs in a private intake location and is **not accepted by this public-only harness**. Never infer a dependency or a business decision from a filename or a successful parse.

## Execution and receipt

`tools.ci.tsql_readiness_ten.run_suite(root, output, source_engine, target_engine, bridge, selection, qualification)` accepts fresh existing `NativeEngine` instances for SQL Server and PostgreSQL. A separately reviewed CI provisioner must supply the connections and qualified coverage controls. The harness does not create containers, credentials, keys or signatures. It refuses local execution and the Friday 08:00–20:00 PT runner blackout.

For every declared case and repeat, it provisions and resets owned databases, executes source and twin, captures raw observations, invokes the existing revision-9 comparator, recomputes from retained bytes, and drops only its owned databases. It repeats with the wrong twin. Cleanup failure stops further work. It writes raw source/target/comparison bytes, case receipts, per-procedure receipts and a summary in a fresh output directory. Receipts bind assets, calling convention, declared cases, CI identity, plan and file hashes. They are **unsigned CI observations**, not Tower decisions or independently attested customer certificates.

Per-procedure outcomes are `equivalent-on-declared-public-cases`, `divergent`, `insufficient-evidence`, or `execution-error`. A correct-twin mismatch stays divergent. Missing cases, unresolved obligations, absent qualified coverage, or a wrong twin that fails to diverge cannot pass. A successful summary requires all ten procedure outcomes; it never substitutes seed labels for observations. Native engine/profile validation and qualified controls remain part of the upstream admission boundary.

## What works, what is missing, effort to 300

Existing code already supplies typed invocation, fresh reset/capture, ordered/duplicate-preserving result comparison, state/error/OUT/RETURN handling, coverage and revision-9 replay. Historical repository reports describe public-corpus native qualification; they do not prove this new harness or customer readiness. This draft adds the ten-pair orchestration and five contract tests, authored for CI only.

Missing: approved CI provisioning/connection custody, actual native execution of these ten pairs, pinned provisioner/image/driver evidence, verified coverage controls and measured cleanup; then a private customer dependency inventory, policy decisions, security-context coverage and concurrency/performance scope. The existing VM runner creates recorder keys and signatures, so it cannot simply be invoked under the current no-signing rule. This harness creates neither; no VM access or signing is requested implicitly.

Planning estimate, not measured throughput: 2–4 engineer-days to integrate and prove the dedicated CI boundary, 2–3 days for ten-pair native evidence and defect triage, then 1–2 days to inventory the 300 private pairs after authorized intake. Per-procedure work depends on dependency and semantic complexity: use a measured first tranche to estimate the rest; do not multiply ten public successes into a promise of 300. Customer translation defects, unsupported SQL and owner policy decisions are separate effort/wait categories. Record actual minutes, cases, failures and bytes per pair in that tranche before committing a delivery date.

The PR remains draft and cannot merge before the Friday run. No required-CI workflow, source comparator, policy, Tower code or repository visibility is changed.
