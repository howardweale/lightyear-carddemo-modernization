# Review 304-307 follow-up milestone

## GitHub enforcement

On October10, Howard selected required GitHub checks plus his commit-specific
chat approval (no non-author GitHub review requirement). Main protection is now
active: GitHub Actions app15368 must supply `documentation-and-lint` and
`required-ci`; branch must be current; conversations resolved; admins included;
force pushes and deletion disabled. This PR is not approval to merge itself.
The required-ci workflow waits for every path-selected workflow on the exact PR
head. Missing, queued, running, failed, cancelled, skipped or neutral workflow
results do not pass. The fast gate runs on every PR, including Markdown-only
changes, avoiding required path-filtered checks that stay pending forever.

All workflows cancel superseded branch runs. Main runs have unique groups and
are never cancelled by newer pushes. Broad PR suites skip Markdown-only changes;
executable documentation assets and JSON receipts still trigger validation. Twin
and reconciliation run on main pushes and weekly, and shared codecs, fixtures,
bindings, spec and runner changes trigger them. No historical main run was
cancelled. Queue before changes: 0 queued, 9 active main runs. The attachment's
38 queued figure was historical, not current. Before publication: 0 queued.
The CI follow-up records the queue after publication and post-merge green latency
for the next three PRs; future observations cannot be claimed in this milestone.

[GitHub status-check troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
explains why a skipped workflow cannot serve as the sole required check.

## Twin and reconciliation changes

- Missing/malformed INTCALC processing dates refuse before output creation.
  POSTTRAN explicitly declares that it does not consume the parameter date.
- New receipts bind [twin limits](twin-limits.md), are provisional/non-releasable,
  and never claim z/OS confirmation. ASCII collation is known different.
- Real compiler probes compare native and EBCDIC program collation for ordinary
  comparison, SORT/MERGE and indexed order; original source remains pinned.
- Installer pins four compiler/runtime package versions and SHA256s from the
  official 20240501T000000Z Ubuntu snapshot. It verifies archive downloads and
  falls back to that snapshot; reconciliation CI forces the fallback path.
- Every POSTTRAN twin run invokes independent conservation/condition checks and
  emits a deterministic unsigned sample. The acceptance runner repeats POSTTRAN
  and checks all output hashes for byte identity. Candidate adapters can invoke
  the same checker; no absent Java integration is called complete.
- A real Spring Boot context test exercises the injected INTCALC service and
  batch-job wiring. The lightweight three-way harness remains explicitly labelled.

Focused local validation: 31 tests passed. This includes refusal before output,
exact-head CI gating, input selection, tampered/missing/duplicated posting outputs,
reason codes, collation-sensitive input refusal and sample coverage. An actual
prior public twin artifact was checked against its already-published hashes:
300 input records, 262 posted,38 rejected; all new independent invariants pass.
New public regression files preserve those observed bytes and identify their
source run. They are not hand-made Python POSTTRAN expected outputs.

Linux compiler/Spring and full final-head CI results are linked by the PR check
panel. Pending is not success; this document does not predeclare them green.

## Decisions and deferred work

| Review item | Delivery / remaining prerequisite |
|---|---|
|1 CI | Protection, concurrency, filtering, wider triggers and pinned fallback implemented. Next-three-PR post-merge latency is prospective monitoring. |
|2.1 Collation | Known-difference label, bounded inventory and executable comparison/SORT/MERGE/indexed experiment. General EBCDIC equivalence not asserted. |
|2.2 Dates | Refusal implemented and tested; POSTTRAN no-parameter contract explicit. |
|2.3 Limits | Register bound to receipts and linked in the Tower review checklist below. |
|2.4 VM | Blocked: Multipass absent from PATH/standard installation. Same two-build command and hash-comparison procedure documented; no VM result claimed. |
|3.1 Scenarios | Deferred until Workstream1.2 generator lands; no scenario generator exists in this checkout. Existing18comparisons are not promotion evidence for a wider domain. |
|3.2 POSTTRAN | Provisional twin selected; independent invariants, repeatability and unsigned sample implemented. Java POSTTRAN candidate and signed human sample review remain unavailable/pending, so release stays blocked. No Python POSTTRAN oracle. |
|3.3 Memo | [Promotion decision memo](twin-oracle-decision-memo.md); recommends retaining provisional status. |
|3.4 Spring | Real application-context regression added to hosted reconciliation. |
|4 B07 | [Selected draft](b07-primary-comparison-plan.md): G-vs-S primary, B06 secondary, two balanced isolated runners subject to approval. No model/native authorization. |

Tower operator review checklist: inspect the receipt's `twin_limits_path` and
`twin_limits_sha256`, the [limits register](twin-limits.md), unresolved outcomes,
and [public human review sheet](posttran-human-review-sheet.json). The sheet is
unsigned. No agent-created signature represents Howard's review. No deployed
Tower or machine configuration was changed. Sealed B06 evidence is untouched.

No model calls, customer/Maintec data, qualification or measurement credit.
