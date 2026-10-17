# POSTTRAN Phase 2 — operator signing and one-attempt launch

This is one comparison of the unchanged attempt-1 candidate with the provisional
twin. It grants no model call, repair, retry, z/OS confirmation or release credit.
Allow about ten minutes for these steps after the preparation and proof-publication
PRs are ready. No action in this document has been executed on Howard's behalf.

## Before signing

Open `posttran-phase2-readiness-2026-10-17.json` beside the new unsigned
`posttran-phase2-authorization-request-2026-10-16.json`. The readiness receipt
must name the actual compiler artifact ID, preparation run, expiry, sign-and-launch
deadline and executable commit. Do not use an estimated expiry. The deadline is
24 hours before the artifact expires; a warning appears at or below five days remaining before the sign-and-launch deadline.
Sign and launch by **2026-10-29 14:46 UTC (07:46 Pacific)**, exclusively.
Push the execution branch and open its PR before 29 Oct 14:46 UTC (07:46 Pacific). A run that starts later is refused.
The `reserve` authorization check must start before the cutoff; an earlier PR opening does not guarantee timely runner scheduling. Allow queue time.
The daily [deadline workflow](../../.github/workflows/posttran-handoff-deadline.yml) evaluates the real UTC clock independently of this dated status snapshot. At or after 24 Oct 14:46 UTC it fails and maintains one warning issue; scheduled jobs may be delayed.
If the receipt is absent or a deadline has passed, stop for fresh preparation.
The October 14 and October 15 plans and requests are historical only.

1. Confirm the preparation workflow passed, including the throwaway-authority
   rehearsal. Its compiler artifact must still exist. Preparation builds only
   the compiler image; it does not execute POSTTRAN or consume an attempt.
2. Confirm the request's `details.executable_commit` contains the published plan,
   and `details.request_seal` equals that plan's `content_sha256`. Check candidate,
   provenance, compiler archive, workflow hash, one-run caps and UTC window.
3. Howard, as the operator, will import that public snapshot and unsigned request into
   the **Factory** Tower on port **8769**. Use its existing isolated authority.
   Do not use the B06 Tower on 8768. Importing a request does not approve it.

## Sign, publish the proof, then set the variables

4. In Factory Tower, sign in with your individual credential. Click **Work queue**,
   then the POSTTRAN `engineering-run-approval` item. Compare its hashes with
   step 2. Choose **approve**, enter your reason, and click **Record decision** once.
5. Click **Decision history** and inspect the new signed event. Howard will export its proof at the current trusted journal head. Prepare
   that proof as `posttran-phase2-authorization-proof-2026-10-16.json` in
   `docs/factory/`, alongside the exact request, in a local execution-branch
   commit. Record its SHA before opening the execution PR. Howard prepares the execution PR, which may add only
   those two files after the signed executable commit. A code, plan, public-key
   or other file change needs new preparation and approval.
6. Review the final execution PR commit SHA. In GitHub, open the repository,
   **Settings → Secrets and variables → Actions → Variables**. Set these repository
   variables, in this order (use **New repository variable**, or edit the existing one):

   | Variable | Exact value |
   | --- | --- |
   | `POSTTRAN_PHASE2_APPROVED_PLAN` | New plan's 64-character `content_sha256` |
   | `POSTTRAN_PHASE2_APPROVED_JOURNAL_HEAD` | Trusted current journal head used by the exported proof |
   | `POSTTRAN_PHASE2_APPROVED_HEAD` | Final 40-character execution PR commit, including the proof |

   Set HEAD last. These variables are approvals, not the compiler preparation
   commit or the plan file's byte hash. Read all three back before proceeding.
7. A variable change alone does not start a run. After reading back the variables,
   Howard will push that exact execution-branch commit. In GitHub,
   click **Pull requests → New pull request**, select main as base and the
   execution branch as compare, verify the SHA, and click **Create pull request**.
   This first PR event starts the authorized path. Do not click **Re-run jobs**:
   the execution gate accepts only `GITHUB_RUN_ATTEMPT=1`. If a first attempt
   cannot be arranged without changing the head, stop and review the final head
   again. Do not guess, bypass checks or reuse an earlier run.

## Verify reservation and consumption

8. In **Actions → POSTTRAN Phase2 preparation and authorized comparison**, check
   the head and first attempt. `reserve` verifies the signed request and journal,
   executable ancestry and allowed-file diff, then downloads and hashes the
   original compiler archive and confirms at least 24 hours remain.
9. Only after those checks, one atomic Git ref creation reserves
   `posttran-phase2-consumed-<plan-content-sha256>`. Its reservation artifact records
   the plan, exact head, run ID and `consumed_before_execution: true`. A duplicate
   tag is a refusal. A timeout has an unknown outcome: stop and inspect the tag;
   never retry the reservation automatically.
10. `compare` consumes that reservation and the same compiler artifact. Preserve
    its results, including divergent and indeterminate cases. An execution
    failure still consumes the attempt. No second run, candidate change or model
    call is authorized by this request.

The CI rehearsal provisions a disposable test authority, signs a synthetic
request, verifies proof/variables and intercepts the reservation HTTP transport.
It never creates a real tag. Missing proof, altered request, wrong head/plan,
missing journal, expired window and invalid image all stop before that transport.

## Preparation publication sequence (maintainer)

Prepare from the reviewed branch based on current main with no active fresh plan.
Download the CI `posttran-phase2-plan` artifact and commit its exact plan bytes.
Fetch the preparation run's artifact listing via REST, then run the unsigned
request builder against that plan-publication commit:

```text
python -B -m tools.finalize_posttran_phase2 --root . --artifacts <saved-artifact-list.json> --output <staging-directory>
```

Publish its request and readiness receipt without changing executable bindings.
The builder checks that the plan is committed and the artifact's run/head match.
CI checks the complete fresh binding inventory again. Drift is measured from the signed executable commit to the proposed execution head, not from current main. A branch based on `65bd4cd549067dd3695f4197e495cc15c9473417` may add only the request and proof. Changes on main alone do not invalidate that branch. Any other change on the execution branch needs new preparation and approval.

## Howard's roles and exact Windows commands (execute later)

Howard performs the repository fetch/checkout, public request import, individual UI review/signing, proof export, and final variable/readback steps. Codex prepares and checks public files only; it has no authority to sign or launch. These commands are documentation, not an executed handoff. Before signing, recheck the final reviewed executable ancestry: only request/proof may differ after the executable commit. Main moving on is not execution-branch drift. Keep the execution branch based on the signed executable commit; do not merge current main into it. Any other file difference requires fresh preparation and approval.

### Import step 3

Use the request delivered by this reviewed follow-up and a separate clean Windows checkout. The repository source pins remain immutable even though the request file is a separate public handoff file. Existing private installation paths are deliberately operator-supplied.

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<existing-clean-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$RequestCheckout = '<new-public-request-worktree-directory>'
$RequestRef = '5f50acac88abe371c4a2a0b2e10b55d00ee6923f'
$Request = Join-Path $RequestCheckout 'docs\factory\posttran-phase2-authorization-request-2026-10-16.json'
$PublicKey = '<existing-Factory-Tower-public-key.pem>'
$ExpectedPublicKeyHash = '42c4417fbc33aad3e97318af1a319c413252da674a2546e8351469d3f1415cfd'
$ExecutableCommit = '65bd4cd549067dd3695f4197e495cc15c9473417'
$ExpectedRequestFileHash = 'bc66b605325a11c306b6b58c1bec1e9be25a7fc85eb3844509a420b288729f5c'
$ExpectedQueueHash = 'ab22d84fcebabc79472a27e35012e3e4ff6b3bd330cb5995b08b3a7bc034c49b'
foreach ($Path in @($Checkout, $FactoryRoot, $Python, $PublicKey)) { if (-not (Test-Path -LiteralPath $Path)) { throw "Missing: $Path" } }
if ($FactoryRoot -match '(?i)b06') { throw 'Use Factory 8769, never B06' }
if (git -C $Checkout status --porcelain) { throw 'Checkout must be clean' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
if (Test-Path -LiteralPath $RequestCheckout) { throw 'Use a new request worktree path; preserve existing files' }
git -C $Checkout worktree add --detach $RequestCheckout $RequestRef
if ($LASTEXITCODE -ne 0) { throw 'Request worktree creation failed' }
if (-not (Test-Path -LiteralPath $Request)) { throw 'Published request missing' }
if ((Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Factory Tower public key differs; STOP before import or signing' }
$InstalledPlan = Join-Path $FactoryRoot 'docs\factory\posttran-phase2-plan-2026-10-16.json'
$ExpectedPlanFileHash = 'bd4eda8ebab9209202653e4c96cb931830f9beb538cb3ed9d220fff784884881'
if (Test-Path -LiteralPath $InstalledPlan) {
  if ((Get-FileHash -LiteralPath $InstalledPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPlanFileHash) { throw 'Existing immutable plan differs (possibly the earlier #354 version). STOP; preserve it and request a reviewed supersession. Do not delete, replace, or create another Factory root.' }
}
git -C $Checkout checkout --detach $ExecutableCommit
if ($LASTEXITCODE -ne 0) { throw 'Checkout failed' }
git -C $Checkout merge-base --is-ancestor $ExecutableCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Executable commit is not on fetched main' }
if ((Get-FileHash -LiteralPath $Request -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedRequestFileHash) { throw 'Request bytes differ' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract $Request
if ($LASTEXITCODE -ne 0) { throw 'Import refused' }
# Compare factory-<ExpectedQueueHash> on http://localhost:8769 before any signature.
```

### Proof export step 5, only after Howard signs in the UI

Use Howard's current authenticated Factory session token and the decision SHA shown in Decision history. The endpoint exports the existing public proof; it does not create a new decision. Never substitute an activation-time journal head.

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<existing-clean-Windows-checkout-at-65bd4cd549067dd3695f4197e495cc15c9473417>'
$Python = '<installed-Windows-Tower-Python>'
$ExpectedQueueHash = 'ab22d84fcebabc79472a27e35012e3e4ff6b3bd330cb5995b08b3a7bc034c49b'
$ExpectedPublicKeyHash = '42c4417fbc33aad3e97318af1a319c413252da674a2546e8351469d3f1415cfd'
foreach ($Path in @($Checkout, $Python)) { if (-not (Test-Path -LiteralPath $Path)) { throw "Missing: $Path" } }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne '65bd4cd549067dd3695f4197e495cc15c9473417') { throw 'Wrong executable checkout' }
if (git -C $Checkout status --porcelain) { throw 'Checkout must be clean' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Tower = 'http://localhost:8769'
$DecisionSha = '<64-hex-signed-decision-SHA-from-Decision-history>'
$ProofPath = '<absolute-new-path-to-posttran-phase2-authorization-proof-2026-10-16.json>'
$PublicKey = '<existing-Factory-public-key.pem>'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Decision SHA required' }
if (Test-Path -LiteralPath $ProofPath) { throw 'Do not overwrite a preserved proof' }
if (-not (Test-Path -LiteralPath $PublicKey)) { throw 'Public key missing' }
if ((Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Factory Tower public key differs' }
$SecureToken = Read-Host 'Current Factory session token' -AsSecureString
$Token = [Net.NetworkCredential]::new('', $SecureToken).Password
try {
  $Headers = @{ Authorization = "Bearer $Token" }
  $Item = Invoke-RestMethod -Uri "$Tower/api/tower/item?id=factory-$ExpectedQueueHash" -Headers $Headers
  if ($Item.bound.contract -ne $ExpectedQueueHash) { throw 'Queue contract differs' }
  Invoke-WebRequest -Uri "$Tower/api/tower/proof?sha256=$DecisionSha" -Headers $Headers -OutFile $ProofPath
} finally { $Token = $null; $Headers = $null }
$Proof = Get-Content -LiteralPath $ProofPath -Raw | ConvertFrom-Json
if ($Proof.decision_sha256 -ne $DecisionSha) { throw 'Wrong decision proof' }
$JournalHead = Read-Host 'Current independently verified Factory journal head'
if ($JournalHead -notmatch '^[0-9a-f]{64}$') { throw 'Trusted journal head required' }
$BoundPath = $ProofPath + '.bound.json'
if (Test-Path -LiteralPath $BoundPath) { throw 'Bound file already exists' }
[IO.File]::WriteAllText($BoundPath, ($Item.bound | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
Get-FileHash -LiteralPath $ProofPath -Algorithm SHA256
& $Python -B -m lightyear_control_tower verify-decision --record $ProofPath --trusted-public-key $PublicKey --kind engineering-run-approval --scope factory --bound $BoundPath --journal-head $JournalHead
if ($LASTEXITCODE -ne 0) { throw 'Public proof verification refused' }
```

Stop if the proof, contract, public key or current journal head cannot be independently verified. No private-key command belongs in this runbook.

## October 17 correction record

The request is read from the immutable publication ref `5f50acac88abe371c4a2a0b2e10b55d00ee6923f`, separately from the executable checkout. Do not extract it with PowerShell `>`: Windows PowerShell 5.1 may change its encoding. Git worktree extraction preserves its exact bytes.

The committed authority PEM SHA-256 is `42c4417fbc33aad3e97318af1a319c413252da674a2546e8351469d3f1415cfd`. This is the CI trust anchor, **not evidence that the local Tower uses that key**. Howard must compare the existing Tower public key before signing; a mismatch is a stop, not permission to provision or replace a key.

The [dated plan amendment](posttran-phase2-plan-amendment-2026-10-17.json) records the single changed binding and the original CI artifact hash. The [new readiness record](posttran-phase2-readiness-2026-10-17.json) supersedes the October 16 description without modifying the request, plan, or authority. Authorized by: Howard (documentation and code follow-ups). Performed by: Codex. No signing, import, activation, reservation, or launch performed.
