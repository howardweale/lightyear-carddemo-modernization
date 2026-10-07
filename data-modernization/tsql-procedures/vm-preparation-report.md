# T-SQL M0 VM and capture preparation — October 7, 2026

Operator review; not independent attestation.

Google Cloud was selected, but no project, VM or authenticated connection has
been supplied. No cloud resources were created. The proposed environment and
create-once Cloud Shell commands are in [linux-vm-setup.md](linux-vm-setup.md).

This increment adds:
- An x86-64 Linux ScriptDom build/check script that retains logs and checks all
  42 public source procedures. Bash syntax passed; the build itself has not run.
- Read-only DB-API ordinary-table capture, raw typed-value transport and
  before/after side-effect reconstruction.
- Offline signed-manifest and file-hash verification, strict evidence closure
  and side-effect replay. It always reports insufficient-evidence while native
  reset/cleanup, cross-engine mapping and coverage admission are unqualified.

Validation: 53 T-SQL tests plus 39 existing semantic-core, stored-logic and ASE
regressions passed (92 total). Capture tests use mock DB-API connections; replay
tests use ephemeral test signing keys. These are not native database evidence.

Remaining: select and approve the exact Google Cloud project/VM; transfer only
reviewed T-SQL code; build ScriptDom with the real SDK; implement/connect native
driver call/reset backends; qualify engine catalogs (including unsupported
external/foreign-table handling), capture, error mappings, coverage, replay and
owned-resource cleanup on the approved VM. No native equivalence claim is made.

Zero Docker commands, zero native pairs and zero model calls. B05, B06,
template-r1, work/ms94 and frozen paths were not modified.
