# POSTTRAN Phase 2 — operator signing and one-attempt launch

This is one comparison of the unchanged attempt-1 candidate with the provisional
twin. It grants no model call, repair, retry, z/OS confirmation or release credit.
Allow about ten minutes for these steps after the preparation and proof-publication
PRs are ready. No action in this document has been executed on Howard's behalf.

## Before signing

Open `posttran-phase2-readiness-2026-10-16.json` beside the new unsigned
`posttran-phase2-authorization-request-2026-10-16.json`. The readiness receipt
must name the actual compiler artifact ID, preparation run, expiry, signing
deadline and executable commit. Do not use an estimated expiry. The deadline is
24 hours before the artifact expires; a warning appears at or below five days remaining before the signing deadline.
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
CI checks the complete fresh binding inventory again. If other follow-ups change
bound code before launch, prepare a new dated plan; never execute across drift.

## Howard's roles and exact Windows commands (execute later)

Howard performs the repository fetch/checkout, public request import, individual UI review/signing, proof export, and final variable/readback steps. Codex prepares and checks public files only; it has no authority to sign or launch. These commands are documentation, not an executed handoff. Before signing, recheck the final reviewed executable ancestry: only request/proof may differ after the executable commit. If other follow-ups landed, finalize a new request for that reviewed commit first; do not use the draft below across drift.

### Import step 3

Use the request delivered by this reviewed follow-up and a separate clean Windows checkout. The repository source pins remain immutable even though the request file is a separate public handoff file. Existing private installation paths are deliberately operator-supplied.

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<existing-clean-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$Request = '<absolute-path-to-reviewed-posttran-phase2-authorization-request-2026-10-16.json>'
$ExecutableCommit = '65bd4cd549067dd3695f4197e495cc15c9473417'
$ExpectedRequestFileHash = 'bc66b605325a11c306b6b58c1bec1e9be25a7fc85eb3844509a420b288729f5c'
$ExpectedQueueHash = 'ab22d84fcebabc79472a27e35012e3e4ff6b3bd330cb5995b08b3a7bc034c49b'
foreach ($Path in @($Checkout, $FactoryRoot, $Python, $Request)) { if (-not (Test-Path -LiteralPath $Path)) { throw "Missing: $Path" } }
if ($FactoryRoot -match '(?i)b06') { throw 'Use Factory 8769, never B06' }
if (git -C $Checkout status --porcelain) { throw 'Checkout must be clean' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
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
$Tower = 'http://localhost:8769'
$DecisionSha = '<64-hex-signed-decision-SHA-from-Decision-history>'
$ProofPath = '<absolute-new-path-to-posttran-phase2-authorization-proof-2026-10-16.json>'
$PublicKey = '<existing-Factory-public-key.pem>'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Decision SHA required' }
if (Test-Path -LiteralPath $ProofPath) { throw 'Do not overwrite a preserved proof' }
if (-not (Test-Path -LiteralPath $PublicKey)) { throw 'Public key missing' }
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
