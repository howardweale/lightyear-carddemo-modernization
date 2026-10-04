# PR235 review follow-up: confidential evaluation and durable probing limits

Implemented on `codex/verify-pr235-hardening`, based on main `3e2d611`.
Operator review; not independent. Published for review in
[PR #240](https://github.com/howardweale/lightyear-carddemo-modernization/pull/240),
with the [hardening milestone](hardening-milestone.md). Publication does not grant
permission to admit customer data.

## Behavior

Non-fixture tasks default to confidential mode and cannot enable field disclosure.
Their result channel carries the verdict and affected dataset identities only;
fields, diagnostic subtypes, counts and bands are removed. Signed public receipts
also omit private-evidence commitments. Private receipts retain those commitments
for replay. The operator README documents deliberate encoding by a malicious
candidate, deployment-specific policy, residual timing channels and a conservative
business-result bound below 26 bits over five confidential submissions. A literal
leak scan does not establish resistance to deliberate encoding or zero leakage.

An inventory-hash ledger is shared by all tasks under the managed judge identity.
It signs and chains reservations, locks across processes, carries usage into new
tasks, and never refunds interrupted or voided attempts. A new task cannot raise
the cumulative cap. A human Tower budget-increase decision must bind the inventory,
current ledger head and usage, and new limit; it leaves each task's sealed limit
unchanged. The judge's OS-registered home selects the ledger, not task paths or an
agent-controlled environment variable. Protect and back up that ledger and pin
its terminal head. Deleting it administratively or provisioning another judge
identity is outside this trust boundary.

Non-completed receipts create `verify-attempt-review` requests in Tower. Signed
human `continue` or `void` proofs bind the exact public receipt and are imported
through the operator CLI. They allow a fresh attempt after review while retaining
the original outcome and consumed slot. Completed receipts cannot be voided by
this path. There is no agent approval RPC. Proofs, keys, scope, journal head and
receipt binding are checked again during offline replay.

Task fingerprints include all four Python packages, `spec/mainframe` assets,
bubblewrap's binary and the Java runtime including linked configuration. Changed
fingerprints refuse admission, worker start/completion and replay. Existing tasks
must retain their original protected installation; this change does not rewrite
old task signatures or migrate historical evidence automatically.

Submission returns a durable attempt ID and `pending` before evaluation finishes.
The service remains available for verdict/budget reads while a separate private
worker evaluates. Idempotent retries cannot create another attempt. Process-local
arrival state cannot race between tasks; service death kills its worker, and an
unfinished reservation is consumed on restart.

The flat allowance is now named `attempt_slots`, not measured build minutes. Each
slot permits up to 300 seconds of sandbox execution across its evaluation runs;
the worker supervisor has a 360-second limit including preparation and replay.
There is no source build in the judge's JAR-only mode.

Invalid and unauthenticated requests use fixed-cardinality, saturating memory
counters with at most one signed summary per minute with traffic, plus shutdown.
Ordinary queries are aggregated too. Accepted attempts and decisions remain
individually durable. Request throttling, bounded header/body read time, and
suppressed per-connection error tracebacks limit HTTP flood amplification. A crash
can lose unflushed traffic counters; local service availability is not guaranteed
against a hostile host user.

## Validation

- Linux protected-install acceptance: **19 tests passed**. Five confidential
  submissions and five fixture-field submissions each independently replayed
  through the existing INTCALC replay. Protected-value scans found zero matches.
  The fixture-field flow used the real MCP SDK and separate agent/judge OS users.
  Hostile Java failed host-file/network access; its delayed child did not survive.
- Final hardening regression after the HTTP edge-case change: **13 tests passed**.
  Coverage includes deliberate diagnostic encoding collapse, binary/asset/runtime
  fingerprint changes, pending results and idempotency, cross-task and real
  cross-process budget races, signed budget grants, interruption recovery,
  receipt-bound continue/void, completed-receipt refusal, invalid-request floods,
  non-ASCII authorization headers and receipt path traversal.
- Scoped Windows regression: **96 passed, 12 platform-specific skips**. This
  covered toolkit, Tower decisions/HTTP/workflows, z/OS intake and status exports.
  Linux-only locking and sandbox checks ran separately on Linux as described above.
- A redundant Linux regression invocation directly against the Windows worktree
  hit its Windows-format Git metadata and slow mounted-filesystem traversal; it
  was interrupted and is not reported as a pass. The protected Linux acceptance
  installation and native Windows regression supplied the platform checks.

Only public synthetic fixtures and the unchanged public Java candidate were used.
The candidate source and build configuration match the earlier built fixture;
test mutants were compiled by the acceptance suite. No model calls, Docker
operations, Maintec data, B05/B06 changes, or `work/ms94` access were needed.

## Deployment and remaining validation

The [operator README](README.md) documents confidentiality policy, async polling,
budget migration terminology and exact operator decision commands. The bundled
agent workflow now describes pending results and dataset-only diagnostics.

CI now loads the distribution's bubblewrap-specific AppArmor profile instead of
disabling user-namespace restrictions with a global sysctl. This WSL environment
has no active AppArmor filesystem, so **policy loading has not been validated
locally**. Ubuntu 24.04 [CI run 37163426350](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/37163426350)
subsequently passed policy loading and all 19 acceptance tests in 54.048 seconds.
The initial CI attempt failed because the profile was not installed at the assumed
default path; the correction installs `apparmor-profiles` and loads the packaged
`bwrap-userns-restrict` extra profile. Missing policy still fails closed.

No optional model-backed harness smoke test was run. The supported claim remains
“built and tested with the MCP SDK,” not universal live-harness compatibility.
These tests do not authorize customer-data disclosure. Existing pre-upgrade
evaluations require an operator accounting review before the same inventory is
admitted under a new ledger; no automatic historical-ledger migration is claimed.
