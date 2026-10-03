# Lightyear Verify implementation acceptance

Implemented on branch `codex/lightyear-verify-mcp`, based on `d4a97d0`.
Local acceptance uses public synthetic fixtures. Operator review; not independent.

## Delivered

- Separate stdio toolkit and operator-owned loopback judge, with two OS users.
- JAR submission, fixed durable budgets, UUID idempotency, signed receipts and
  hash-chained query journal; no candidate-output submission path.
- Existing INTCALC comparison/replay, closed dataset/field diagnostics and count bands.
- Signed immutable Tower exports, attempt/verdict/budget views, repeated-result
  alerts, and human-only normalization drafts that do not modify rules.
- Legacy modernization skill, four harness configuration examples, setup and
  isolation instructions, leakage analysis, and a Linux CI acceptance job.

## Validation

The real Linux MCP SDK acceptance suite exercises five budgeted submissions:
the current Java candidate passes; erroneous one-cent interest rounding, a
missing account and changed timestamp dates diverge; the repeated date fault
raises the repeated-diagnostic alert. Each receipt independently replays using
the existing offline INTCALC replay. Submission six is refused and remains visible
in the journal and Tower. A new service process retains the exhausted budget.

Every evaluation input/output field value of four or more non-padding characters
is included in the leak scan. Only exact documented public fixture overlaps are
excluded, as Howard approved. The evaluation-only canary remains protected;
there are zero protected-value matches in captured tool responses, receipts,
Tower views/requests and exports. Direct reads under the MCP user's UID fail.

Real hostile Java execution cannot read the host signing key or connect to the
judge's loopback port, and its delayed child cannot survive sandbox teardown.
The second rehearsal run remains a divergent timestamp negative control. Modified
receipt and journal content fail offline verification. Human requests appear in
the authenticated Console; agent sessions cannot decide them.

Windows intake/Tower/toolkit regression: 61 tests, one Linux-only test skipped.
Additional Console decision/HTTP/observer/workflow regression: 43 tests, one
platform-specific test skipped. Across the three suites: 107 passed, two skipped.
Linux acceptance: five tests, including the real multi-submission SDK session and
hostile candidate/negative-control test. The skill passes `quick_validate.py`.
The Windows suite includes the real concurrent immutable export writer/reader.

## Limits

No model calls, Docker operations or Maintec data were used. No B05 evidence,
`work/ms94` state or B06 preparation was changed. These controls are not autonomous
modernization effectiveness measurements and do not establish Maintec equivalence.
No optional live harness smoke test was run. These local results precede PR CI;
the pull request records remote validation and publication separately. The
[milestone](milestone.md) summarizes the delivered behavior and remaining limits.

Judge execution currently requires a protected Linux repository installation and
Java/bubblewrap; the toolkit is cross-platform. It accepts runnable JARs, not source
bundles. Isolation is a local OS boundary, not VM isolation or protection against
kernel exploits and side channels. No licence choice was made. See the
[operator README](README.md) for the precise budgets, deployment prerequisites,
public-overlap policy and response-alphabet leakage bound.
