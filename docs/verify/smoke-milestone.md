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

## Pending platform and live-client evidence

Ubuntu 24.04 Multipass **arm64 and x86_64 remain unverified** by this milestone.
Neither an AppArmor load inside those VMs nor a full setup/start/stop/acceptance
cycle on either Mac architecture was run locally. The kit's generated reports
are the mechanism for recording those future results, not evidence that they
have already passed.

No live Inspector browser session, Claude Code model test or Codex model test is
claimed. No model calls or Docker operations were made for this implementation.
All compilation/testing used public repository material. This milestone does
not admit Maintec data, establish customer-data confidentiality, qualify a lane,
or claim autonomous effectiveness.

## Publication

This milestone travels with the setup-kit PR. Repository CI results are distinct
from the unrun Multipass and live-client checks above. Approval to publish and
merge the kit does not authorize those model calls.
