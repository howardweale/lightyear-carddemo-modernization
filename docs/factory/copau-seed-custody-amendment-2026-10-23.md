# COPAU automatic seed custody and Windows procedure — 23 October 2026

This additive amendment supersedes every manual seed-entry instruction in the
[qualification amendment](copau-heldout-qualification-amendment-2026-10-23.md) and
[original proposal](copau-heldout-helper-2026-10-23.md). Those records remain
historical. COPAU is PR #446; #445 remains the separate POSTTRAN key-only work.
No private generation, signing, model call, Tower action or proof export has
been performed by preparing this PR. Run the commands only after exact-head
review, approval and green Windows-first synthetic CI.

The helper calls `secrets.token_bytes(32)` itself and exclusively persists it in
`heldout-seed.json`. Howard selects the directory, never the seed value. There is
no seed argument, environment variable or prompt. The private provenance refers
to that file rather than duplicating its contents. Only the path and private
backup reminder are displayed. Back up the whole directory to private storage
with equivalent access controls; do not open or paste its contents.

Windows defaults to
`C:\ProgramData\Lightyear\FactoryControllerPrivate-v1\copau-key-1`.
The directory uses #430's unchanged atomic protected-DACL creation and ACL
verifier. Each file is exclusive, initially protected by the Howard-only parent,
then assigned an explicit Howard-owned DACL with inheritance disabled. Effective
allow entries, owner, inheritance, ancestor replacement rights, links and file
identity are verified after writing and on reuse. No other user/group receives
an allow entry. Windows administrators retain their OS-level ability to take
ownership; this does not claim protection from an administrator controlling the
machine. Linux uses the same custody checks plus exact 0700/0600 modes and UID.

Reject OneDrive (including configured sync roots), `.codex`, any checkout with a
Git ancestor, the worker workspace and all declared/indexed exposed roots. A
complete reviewed exposure inventory remains mandatory. Neither path checks nor
ACLs establish the completeness of that inventory. Never repair an existing
seed's permissions silently or overwrite it after a refusal.

## Normal PowerShell as Howard

Use a clean, separate checkout outside OneDrive and `.codex`, exact Git bytes
(`core.autocrlf=false`), and the reviewed Python environment with the reference's
psycopg import dependency. Do not use the dirty development checkout. These
inputs are public paths, an approved commit, a reviewed index digest and a SID;
none is a seed or expected value. Obtain the reviewed index through the unchanged
collector and closure-review procedure in the qualification amendment.

```powershell
$ErrorActionPreference = 'Stop'
$Python = Read-Host 'Full path of the reviewed Python executable'
$Checkout = Read-Host 'Full path of the clean approved helper checkout'
$Commit = Read-Host 'Exact approved 40-character helper commit'
$Index = Read-Host 'Absolute path of the reviewed public corpus index JSON'
$IndexSHA = Read-Host 'Approved SHA-256 of that exact index file'
$Worker = Read-Host 'Absolute path of the exact 403-file worker workspace'
$AdditionalExposedRoots = @(Read-Host 'Absolute path of the factory run/output root')
$OwnerSID = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$ControllerSID = $OwnerSID
$PrivateParent = 'C:\ProgramData\Lightyear\FactoryControllerPrivate-v1'
$PrivateDir = Join-Path $PrivateParent 'copau-key-1'
if ($Commit -cnotmatch '^[0-9a-f]{40}$' -or $IndexSHA -cnotmatch '^[0-9a-f]{64}$') { throw 'Invalid public binding' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONDONTWRITEBYTECODE = '1'
if (!(Test-Path -LiteralPath $PrivateParent)) {
  & $Python -B -m tools.copau_private_prerequisites initialize --exposed-root $Worker
  if ($LASTEXITCODE -ne 0) { throw 'Parent creation refused; use the one-time step below only if the parent is still absent' }
}
$HelperArgs = @('-B','-m','tools.copau_answer_key','--reviewed-commit',$Commit,
  '--corpus-index',$Index,'--reviewed-corpus-sha256',$IndexSHA,
  '--private-dir',$PrivateDir,'--expected-owner-sid',$OwnerSID,'--exposed-root',$Worker)
foreach ($Root in $AdditionalExposedRoots) { $HelperArgs += @('--exposed-root',$Root) }
& $Python @HelperArgs
if ($LASTEXITCODE -ne 0) { throw 'Not qualified. Preserve private files; do not rerun to seek another seed.' }
```

Add every other exposed root to `$AdditionalExposedRoots` before invoking. The
index automatically excludes its worker, graph, prompt, context and repository
roots too. The Python process SID must equal `$OwnerSID`; do not run under SYSTEM,
a service account, another administrator, or a different scheduled-task identity.
Public output contains the redacted surface counts/hashes, historical public-ID
disclosures, bundle digest/size/count, and seed path/backup instructions. It never
includes fragments, seed bytes, matching locations or exception detail. Tracebacks,
Python logging and inherited stdout/stderr are suppressed during private work.

## Only if protected parent creation needs elevation

The single elevated operation is creating the absent private parent with #430's
verified directory ACL code. It generates no seed or signing key. Open elevated
PowerShell **as Howard**, set the same public `$Python`, `$Checkout`, `$Worker`
paths and paste the previously displayed normal-session SID into `$NormalSID`.
If the parent already exists, stop and inspect its metadata privately; this
procedure must not overwrite or reset its permissions.

```powershell
$ErrorActionPreference = 'Stop'
$NormalSID = Read-Host 'Howard SID from normal PowerShell (public identity)'
$Python = Read-Host 'Full path of the same reviewed Python executable'
$Checkout = Read-Host 'Full path of the same clean approved helper checkout'
$Worker = Read-Host 'Absolute path of the exact worker workspace'
if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne $NormalSID) { throw 'Wrong identity' }
if (Test-Path -LiteralPath 'C:\ProgramData\Lightyear\FactoryControllerPrivate-v1') { throw 'Parent exists; stop' }
[IO.Directory]::CreateDirectory('C:\ProgramData\Lightyear') | Out-Null
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
& $Python -B -m tools.copau_private_prerequisites initialize --exposed-root $Worker
if ($LASTEXITCODE -ne 0) { throw 'Protected parent creation refused' }
```

Close the elevated window and return to normal PowerShell for generation. The
helper never elevates itself. Linux operators instead create the missing private
parent with mode 0700 and use `--private-dir ~/private/copau-key-1`; no SID argument
is needed. The Linux CI job depends on success of the Windows job.

## Replay, public attestation and controller handoff

Keep the original reviewed checkout and index. From that same normal session:

```powershell
& $Python @HelperArgs --reuse
if ($LASTEXITCODE -ne 0) { throw 'Private replay refused; preserve originals' }
$BundlePath = Join-Path $PrivateDir 'copau-expected-values.json'
if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne $ControllerSID) { throw 'Controller identity differs' }
# Later approved controller invocation uses this argument pair; this is NOT a run command:
$PrivateInputArguments = @('--factory-private-expected-values',$BundlePath)
```

A second ordinary invocation against a completed directory also reuses the seed
and compares regenerated bundle bytes. Neither path rewrites seed, bundle or
original evidence. `--reuse` refuses a missing seed or incomplete bundle. Replay
can use a historical reviewed index and proves reproducibility, **not current
surface qualification**. Changes to run-visible surfaces still require fresh
review and scans before admission; replay does not extend the approved bindings.

The optional `--seed-commitment` switch adds only SHA-256(seed); it is explicitly
marked optional in the attestation and absent by default. The bundle remains
exactly #430's `factory-private-expected-values/1` format. The unchanged
`FactoryModelAdmission.private_expected_values` accepts this absolute path after
signed admission, then checks approved digest, size, count and excluded roots.
Synthetic CI exercises that parser with a disposable admission fixture. The
Oct30 controller must run as the recorded Howard SID, not merely share a display
name with Tower; its actual future identity is not yet verified. Never grant a
different controller account access to make this check pass. No controller run
is authorized by these commands.

All four qualification criteria and the Sunday Oct25 review, Monday Oct26 noon
Pacific POSTTRAN review and Wednesday Oct28 18:00 Pacific go/no-go remain. Missing
historical artifacts are disclosure-only. Unmet exposure, freshness, collision
or selection criteria move the run; no date-driven exceptions. Ten-minute checks
remain off. Concrete F2 binding and `request_ready=true` await the operator's
qualified public digest/size/count, signing-key ID and complete CI validation.
