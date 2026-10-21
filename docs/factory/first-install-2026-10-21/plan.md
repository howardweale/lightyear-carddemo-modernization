# Factory Tower: reviewed first installation
Prepared 2026-10-21. Status: proposal only; not installed, started or activated.
Howard approved these paths and preparation of this PR. Installation requires his
approval of the exact final green commit and its CI bundle manifest digest.
Neither this document nor a merged software PR is an operator signature.

## Approved layout and installation boundary
| Item | Exact location |
| --- | --- |
| Read-only runtime | C:\ProgramData\Lightyear\FactoryRuntime-v1 |
| Writable data container | C:\ProgramData\Lightyear\FactoryData-v1 |
| Public evidence / live data root | C:\ProgramData\Lightyear\FactoryData-v1\snapshot |
| Authority configuration, created later by Howard | C:\ProgramData\Lightyear\FactoryAuthority\authority.json |
| Private key, created later by Howard | C:\ProgramData\Lightyear\FactoryAuthority\authority.key.pem |
| Public key, created later by Howard | C:\ProgramData\Lightyear\FactoryAuthority\authority.public.pem |
| Individual credential, created later by Howard | C:\ProgramData\Lightyear\FactoryAuthority\authority.credential.txt |
| Public evidence trust, installed later by Howard | C:\ProgramData\Lightyear\FactoryAuthority\factory-evidence-trust.json |
| Login task, installed DISABLED | Lightyear-FactoryTower-Howard |
| Listener, after Howard starts it | http://127.0.0.1:8769 |

The installer copies an exact CI runtime inventory, creates empty data and
authority directories with restrictive ACLs, registers a disabled login task,
and writes a non-secret installation receipt. It performs no Tower command,
network request, account creation, credential generation, key generation, public
snapshot import, journal write, signature, proof export, activation or service start.
There is no firewall rule. No user/group creation or password is required.

The task uses Howard's explicit SID, Interactive logon and Limited run level.
Run the installer elevated as that SAME account, never SYSTEM or another admin.
The runtime owner is Administrators; Howard's normal task token receives RX only,
including every descendant. Data and authority have protected, Howard-only DACLs;
only Howard has an ordinary read grant on the key folder. The task is Howard too,
so it can read his key after he creates it. Windows administrators can take ownership
with elevated privileges; this is not isolation from an administrator or malware
already running as Howard. No installer access rule grants SYSTEM key access.

The runtime contains pinned CPython 3.12.10 and CI-installed cryptography 46.0.3,
cffi 2.0.0 and pycparser 2.23. CI records every byte, size and SHA-256.
No dependency resolution or download happens in the installer.
Python uses isolated mode and disables bytecode writes. The launcher uses fixed
paths and the existing server binds only 127.0.0.1, with no configurable listen host.
No existing B06/Verify runtime, account, authority, journal or task is reused.

## Review and acceptance gates
1. Review the entire PR, correction, dependency inventory and owner commands.
2. Require green required-ci on the exact head and the new Windows installation
   review job. That job runs only on an expendable GitHub runner.
3. Inspect its retained runtime manifest and artifact provenance: head equals the
   reviewed commit, workflow is this PR's workflow, and bundle hashes match.
   Record the public manifest digest in the review handoff; it is not a key digest.
4. Howard approves the exact commit for installation. This approval does not
   authorize identity/key creation, signatures, activation or POSTTRAN execution.
5. Only then download/extract that CI bundle into a NEW operator-controlled staging
   directory. Reject links, extra files, digest/size mismatches and stale commits.
   Retain the bundle and manifest in a durable Release before artifact expiry.
6. Run the installation command below only after that approval. Recheck the disabled
   task, SID, ACLs, empty authority directory and absence of a listener.
7. Howard performs operator-commands.md privately and retains his own recovery copy.
   Codex does not run, transcript, capture or record login or key command output.

CI checks wrong manifest, wrong source commit, SYSTEM identity and path traversal
refusals before writes; exact installation, owner/ACLs, disabled task/interactive
identity, missing-authority start refusal, repeat-install refusal and packaged CLI
imports. It does not provision a real or test authority. ACL assertions do not
constitute a live operator-token penetration test. Before activation Howard verifies
the effective rights in his non-elevated account. No local tests were run for this PR.

## Install command: approved commit only, elevated Howard terminal
Run from a clean checkout of the exact approved head; do not run from either dirty
working tree. Copy the head and manifest digest from the reviewed CI handoff.

    $ApprovedCommit = '<Howard-approved-full-commit>'
    $ManifestSHA256 = '<reviewed-CI-manifest-SHA256>'
    $Stage = '<new-extracted-CI-bundle-directory>'
    $OperatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ((git rev-parse HEAD).Trim() -ne $ApprovedCommit) { throw 'Wrong checkout' }
    if (git status --porcelain) { throw 'Checkout must be clean' }
    & .\tools\factory_install\Install-FactoryTower.ps1 -RuntimeStage $Stage -ManifestSHA256 $ManifestSHA256 -ApprovedCommit $ApprovedCommit -OperatorSid $OperatorSid

The initial SID must be checked as Howard's account, not merely a familiar name.
No autostart occurs at install time or at subsequent logins while the task is disabled.
No proof endpoint is a health check: exporting a proof signs journal material.

## Schedule (America/Los_Angeles, PDT = UTC-07:00)
October 24, 2026 is Saturday. Use Friday October 23 for the requested installation
and operator setup completion, one day earlier than the supplied calendar date.

| Target, Pacific time | Owner / deliverable | Gate |
| --- | --- | --- |
| Wed Oct 21, by 18:00 | Codex: this PR, CI bundle, correction and dependency review | No local installation |
| Thu Oct 22, by 12:00 | CI and reviewer: exact-head green + bundle manifest/provenance | Repair failures in PR, do not bypass |
| Thu Oct 22, by 17:00 | Howard: exact commit installation approval | Schedule slips if approval/CI is missing |
| Fri Oct 23, 09:00-11:00 | Approved installation, disabled task and ACL inspection | Only installation; no Tower commands |
| Fri Oct 23, 11:00-14:00 | Howard privately: identity/key, public snapshot, roles and seven-record backfill | Preserve original dates; new signatures have actual current time |
| Fri Oct 23, by 16:00 | Howard: verify new public trust/current journal and enable signed-only; publish PUBLIC PEM through reviewed handoff | No login/private key output collected |
| Fri Oct 23, afternoon through Mon Oct 26 | Codex/CI: new-key POSTTRAN preparation, additive amendment, plan, unsigned request, readiness and public proof rehearsal | No real signature or attempt |
| Tue Oct 27, by 12:00 | Reviewer/Howard: final executable bindings, artifact lifetime and signable request accepted | Stop on stale/missing artifacts or binding drift |
| Tue Oct 27, 13:00-16:00 | Howard: sign POSTTRAN, verify/export proof, review final execution head and repository variables | Separate execution approval; request/proof-only final diff |
| Wed Oct 28, before 12:00 | Howard: arrange first execution PR event and verify reservation starts if separately approved | Leaves queue buffer; no blind rerun |
| Thu Oct 29, strictly before 07:46 | Absolute existing sign-and-launch cutoff | Reserve authorization check must start before cutoff |

These are targets, not a claim that CI or human approval is guaranteed by a time.
The Oct 24 07:46 warning threshold remains a warning, not an extended window.
Missing Friday setup or Monday preparation triggers a revised schedule immediately.
If the existing cutoff cannot be met, stop for a newly reviewed window/preparation;
never backdate, loosen a gate, reuse a consumed attempt or infer execution approval.

## POSTTRAN must be re-prepared
YES: replacing the committed key invalidates the old executable/plan binding for
the new signer. The old request cannot simply be imported and signed with the new
key. Its execution branch permits only request/proof additions after the sealed
executable commit; changing the PEM requires fresh preparation and approval.

This PR preserves all frozen POSTTRAN paths, original dated plans and the old PEM.
Once Howard creates and deliberately publishes only his new public PEM, prepare a
separate reviewed key-rotation/preparation change with an explicit frozen-binding
exception approved by Howard. Recompute the full bound inventory and plan seal,
record the additive key-change amendment, publish the exact CI plan and new
unsigned request/readiness record, verify artifact existence/digest/retention and
rehearse with a disposable CI authority. A new artifact may have later retention,
but it does NOT silently extend Howard's October 29 deadline. Preserve candidate,
no-model/no-repair scope and one-attempt cap unless Howard separately changes them.
The current deadline and artifact IDs are historical inputs, not fresh availability
checks. Re-query them during preparation and immediately before signing/reservation.

## B06 cleanup: no prerequisite
No B06 cleanup item is required for this installation. The older cleanup-seal
prompt is dropped. Required preflight is limited to: port 8769 unused, all three
Factory destinations absent, task name absent, adequate space and valid staged
inventory. A conflict means stop and inspect; do not delete/stop B06 or another
service. B06 port 8768, private authority and missing run receipts are separate.
Those receipts remain requirements for B06's own claims, not for installing Factory.

## Failure and rollback
A failed installer leaves an inert partial installation for inspection and refuses
a blind retry. It never recursively deletes destinations. A reviewed cleanup plan
must identify exact paths and prove authority/data contain no user material before
removal. After Howard has provisioned anything, preserve authority, credentials,
journal, public proof and backups; never regenerate to make a check pass.
For a running install, Howard can disable and end the named task in his terminal.
Uninstall/deletion is a separate reviewed action, not part of this installer.