# Lightyear Verify confidential evaluation milestone

Date: 2026-10-03. Operator review; not independent.

## Purpose and delivered behavior

This milestone addresses the review of PR #235 before admitting non-public data.
It reduces the diagnostic disclosure channel and makes evaluation limits survive
new tasks, interrupted execution and service restarts.

- Non-fixture evaluation defaults to confidential mode: verdict and dataset-level
  diagnostics only. Public receipts exclude private evidence commitments.
- A signed inventory-hash ledger enforces cumulative attempt limits across tasks
  and processes. Interrupted and voided attempts remain consumed.
- Tower continue/void decisions bind a non-completed receipt. Separate signed
  budget grants bind the inventory, ledger head, usage and new limit.
- Task fingerprints bind specification/mainframe assets, bubblewrap and the Java
  runtime as well as the Python implementation.
- Submission returns a durable pending attempt while an isolated worker runs.
  The allowance is accurately named `attempt_slots`; invalid traffic is throttled
  and journaled in bounded aggregate summaries.
- Deployment uses the distribution's bubblewrap AppArmor profile while retaining
  the host user-namespace restriction.

The implementation is recorded in commit `12d321fcae4e4e650cbd725ae8ff11cec120d86c`.
The [review follow-up record](pr235-hardening.md) provides detailed behavior,
validation and migration limits. The [operator guide](README.md) provides setup,
policy and decision commands. The [original milestone](milestone.md) remains a
historical record of the initial delivery.

## Validation and limits

Protected Linux acceptance passed 19 tests, including confidential and fixture
submissions, real MCP SDK transport, separate OS users, hostile Java isolation,
protected-value scanning and offline replay. The final hardening regression
passed 13 tests. Scoped Windows regression passed 96 tests with 12 platform skips.
These are separate runs, not a combined count of unique tests.

The local WSL host cannot validate AppArmor policy loading; the Ubuntu acceptance
CI must validate that deployment step before merge. No model calls or customer
data were used. B05, B06 and `work/ms94` remain outside this change.

Confidential mode reduces disclosure; it does not eliminate deliberate encoding,
timing channels or risks from a hostile host administrator. Existing inventory
exposures need operator accounting before adoption of a new ledger. No automatic
historical ledger migration or permission to disclose customer data is implied.

## Publication

[PR #240](https://github.com/howardweale/lightyear-carddemo-modernization/pull/240)
publishes this milestone and the hardening implementation. Publication contains code,
public-fixture tests and documentation only; private task evidence and keys are
excluded. Merge is contingent on the required repository checks.
