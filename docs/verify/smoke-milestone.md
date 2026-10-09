# Lightyear Verify VM smoke-kit milestone

Date: 2026-10-04 (America/Los_Angeles).
Base: main `fb5bd13f8a04003e334d3b2529fcdec614af16f1`.
Operator review; not independent attestation.

## Delivered

The [manual runbook](smoke-runbook.md) and
[setup kit](../../tools/verify_smoke/setup.sh) prepare a dedicated Ubuntu 24.04
Multipass VM for hand-testing Verify on macOS. The installer detects arm64 or
x86_64, records the actual platform and package versions, loads Ubuntu's
bubblewrap-specific AppArmor policy and tests namespace operation without
disabling host restrictions.

The protected install and venv are root-owned. Separate non-admin lyjudge and
lyagent identities own the private judge state and public development workspace.
Only the unchanged, Git-bound public INTCALC-run1 rehearsal fixture enters the
private evaluation directory; configuration explicitly declares fixture mode.
Setup checks private-key denial, evaluation-directory denial and installation
write denial, and start repeats these checks after initialization creates the key.
Identical setup reruns verify instead of resetting keys, budgets or evidence.

The judge starts as lyjudge through a dedicated systemd unit and listens only on
loopback. The administrator launcher drops groups, GID and UID before handing
the token to the agent process environment. It does not put the token in argv or
an agent file. Inspector forwards it through an anonymous memory-only session
configuration with its secret store in memory. Stop preserves the session and
cumulative ledger.

The public known-good JAR and the three existing acceptance mutations are built
into the agent workspace. These exercise the erroneous extra cent, omitted
account and changed transaction dates. The optional platform runner invokes the
existing zero-model acceptance supervisor and writes a new architecture-labelled
report. Missing native execution or skipped acceptance tests cannot be reported
as a passing platform check.

The runbook includes Mac VM creation/disposal, an authenticated loopback Inspector
tunnel, tool-by-tool expected results, and separate Claude Code/Codex installation,
login, a shared single-task prompt, pass criteria and a results template. Live
client/model testing is explicitly gated on Howard's further approval.

## Validation completed locally

- **15 Python tests passed; one existing POSIX-only test skipped on Windows.**
  The 10 new kit tests cover public fixture integrity, refusal of modified or extra
  evaluation files, idempotent writes, public manifest bindings, architecture
  mapping, privilege-drop/token handoff ordering, acceptance skip detection and
  actual compilation of all three mutants.
- **11 public Java tests passed** in an offline Maven package build.
- Each compiled mutant changed only the intended Spring Boot service class in
  its JAR; all four artifact hashes were distinct.
- Bash syntax, Python parsing, Unix shell line endings and Git whitespace checks
  passed.

Windows sandbox restrictions prevented initial temporary-directory tests; the
same local tests passed with approved execution access. WSL access was denied,
so no Linux VM validation is attributed to that attempt.

## Platform and live-client evidence

At implementation time, neither an AppArmor load inside a Multipass VM nor a full
setup/start/stop/acceptance cycle on either Mac architecture was run locally.
The kit's generated reports are a mechanism for recording platform checks, not
evidence that those checks have already passed.

The subsequent [2026-10-04 smoke results](smoke-results.md) record Howard's
**operator review; not independent attestation** on Apple Silicon / Ubuntu 24.04
arm64: the Inspector 15-step zero-model walkthrough passed, and Claude Code
reported the expected equivalent/divergent outcomes for all four prebuilt JARs,
four retained receipts, 18 Verify tool calls, $0.76 at API rates and 9 minutes
wall time. Codex remains **planned, not completed** after sign-in problems.
x86_64 and independent platform/replay evidence remain outstanding in that record.

No model calls or Docker operations were made to implement the kit or record
these results; the reported Claude Code test is a separate operator-run live
test. All implementation compilation/testing used public repository material.
This milestone does not admit Maintec data, establish customer-data
confidentiality, qualify a lane, or claim autonomous effectiveness.

## Publication

The setup kit and initial milestone were merged in PR #249; the sudo privilege
check and executable shell modes were corrected in PR #250. Repository CI is
distinct from the operator-reported live results and outstanding checks above.
Approval to publish and merge documentation does not authorize new model calls.

## Kiro CLI results recorded — October 8, 2026

The [Kiro CLI results](smoke-results.md#kiro-cli) record Howard's operator-run
public-fixture test on `lyverify-kiro`, an Apple Silicon Mac running Multipass
Ubuntu 24.04. Kiro CLI 2.28.0 used explicitly selected `claude-sonnet-4.5` as
lyagent. All four prebuilt artifacts produced the expected verdicts: the good
JAR was equivalent; rounding, skipped-record and date mutants were divergent.
The client reported 18 Verify tool calls, four attempts consumed and one left.

Howard reported successful offline replay after stopping the judge: four
attempts and four native verdicts, zero model calls, exit code 0. Receipt
identities, hashes and the terminal journal head are recorded in the supplied
section. They were not separately inspected for this documentation update;
the journal head was obtained immediately before replay, not pinned by an
independent observer. Operator review; not independent attestation.

Reported usage was 6.73 Kiro credits, approximately six minutes wall time and a
calculated $0.13 at the Pro plan rate (not an invoice). Follow-up observations
cover model-composed idempotency UUIDs, public-read order and receipt identities
reported without agent-written receipt files. This demonstrates the prebuilt
public-fixture workflow, not autonomous implementation effectiveness or Maintec
equivalence. Codex's existing planned status is unchanged.

PR #281 adds the supplied Kiro section verbatim between Claude Code and Codex
and this milestone entry. Validation confirmed attachment byte equality and
preservation of every original smoke-results byte; Git whitespace checks passed.
This documentation update made zero model calls and ran no live client or Docker
workload. Repository CI is separate from the reported Kiro evidence.
