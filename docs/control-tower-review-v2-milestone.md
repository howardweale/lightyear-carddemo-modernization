# Control Tower Decision Console v2 review milestone

Date: 2026-10-02 (America/Los_Angeles). Scope: review rounds one and two together,
based on main `1b204fe7cf36f180f4a96ab36070536b6d4661cd`. This follows the
[original five-part delivery](control-tower-decision-console-milestone.md).
It is a software implementation milestone, not an MS94 measurement or a lane
qualification. Operator review; not independent attestation.

## Delivered behavior

Customer evidence exports now freeze when two distinct authorized people approve
the same reviewed bundle. The export includes the two release decisions and chain
commitments, without adding unrelated private journal bodies or later drafts.
Qualification records use their own external trust key, separately from the
Console's signatures. Independent reviews derive authorship from an authenticated
proposal event; a new request ID cannot prevent a rejection from superseding an
approval of the same subject.

Evidence reads reject special files and run outside the decision writer lock.
Review dates have a maximum interval, all authenticated users can log out, and HTTP
requests have bounded socket handling. Authorities, keys, credentials and
qualification trust must remain outside the engine-writable data root. Two live
fixture deployments exercise every HTTP/SSE route and all seven MCP tools with
both valid and foreign credentials.

Campaign projections fingerprint arbitrary business failures, use recorded origins,
validate available signed journal chains, isolate malformed campaigns, and distinguish
missing evidence from mismatches. Epoch times and elapsed budgets are explicit.
Future controllers bind the verified campaign identity and require a separate exact
resume for every pause. These changes are not wired into any frozen controller.

Rule-register membership changes advance its major version. Overdue reviews are
queued, known pending changes produce catalogue warnings, and entries show overdue
dependent-rule reviews. Partner disclosure is allowlisted and sharing is separate
for each partner. Agent sessions refresh when expired.

The [remediation record](control-tower-review-v2-remediation.md) maps all 25 review
findings to the implementation and tests. The
[operating guide](control-tower-decision-console.md) explains the approval,
trust, export and migration contracts.

## Windows observation boundary

The suspected atomic-replacement race was reproduced using disposable files.
Allowing Win32 delete sharing still did not let Python's `os.replace` replace an
open destination. Reader retries cannot prevent an error already delivered to the
writer. Live Windows observation therefore fails closed before opening producer
evidence. Explicitly configured completed immutable exports are supported.

This milestone does **not** claim safe live Windows observation. A future
producer-coordinated export protocol is still needed for that capability. A live
root must never be relabelled as an immutable export. No observer was pointed at
B05, and no frozen writer was changed.

## Validation and delivery

- Decision Console suite: 50 tests successful on Windows, with two POSIX-only
  skips. The skipped FIFO and overlapping replace/append tests are included in
  the existing Linux/macOS CI matrix.
- Compatibility suites: 117 tests passed across legacy decisions, action plans,
  run indexing, live Tower, comparator, workflows/history and paired campaigns.
- Chromium Console flow passed with zero external browser requests.
- Final key/credential path-refusal and expanded two-server isolation tests passed.
- JavaScript syntax and `git diff --check` passed. Original signed B04 fixtures
  are unchanged and still match their provenance manifest.

The compatibility run emitted an unrelated legacy Explorer SSE teardown traceback
after a disposable database was removed; the suite completed successfully. That
Explorer code was not changed. Local results do not substitute for required PR
checks; repository CI records publication and merge validation separately.

The initial Linux CI run exposed a test portability assumption: Python 3.13 can
parse nesting that reaches the recursion limit on local Python, then rejects the
non-object request with HTTP 422. The regression now accepts that safe refusal
and separately injects a parser `RecursionError` to require HTTP 500. Socket timeout
and catch-all behavior are unchanged; no check was disabled.

Publication includes Console source changes, tests, example configuration and
documentation only. It includes no new private captures, archives, checkpoints,
reference sources or signing material. B04 remains VOID. No model calls, native
database executions or campaign operations were performed for this milestone.

## Remaining boundaries

Older independent approvals without proposal bindings, authorizations without a
campaign binding, and unfrozen v1 releases are preserved but require fresh explicit
reviews under the new contracts. Historical signatures and verdicts are not
rewritten. Offline verification establishes validity at the archived head and
cannot prove that a newer decision does not exist.

Production LAS replay, SSO, hosted multi-tenancy, WORM retention, remote deployment,
safe live Windows polling and migration of frozen measurements remain outside
this delivery. The Console records decisions without dispatching work or changing
verdicts.
