# INTCALC ordered signing runbook

Prepared October 18, 2026. This is a proposed operator procedure, not permission
to sign, import, merge, activate or execute anything. Use only the existing
Windows Factory on localhost:8769 and its installed environment. Never provision
a second root, use B06 port 8768, or supply a private key to the binding command.

## Approval and evidence prerequisites

Howard must approve the exact final green implementation before these commands
are used. Review the complete selected packet and any changed evidence binding.
The current sixth template deliberately has unmet typed conditions: it cannot
be signed just because a predecessor hash is available. Prepare and approve the
complete evidence-backed packet before starting; do not edit packet bodies
mid-chain. A new packet identity requires its own reviewed sequence.

There are six signature rounds. Round 1's original template is already published
in the ordered packet. Rounds 2 through 6 each create new unsigned bytes, requiring
**five additional request PRs** after the initial packet is approved. If packet
preparation changes, its replacement preparation PR is additional. The tool's
implementation PR is also separate. A sixth-round approval is not a release or
Phase 2 authorization.

A possible future alternative is local verified binding: accept unsigned bytes
only after comparing their complete template body, packet identity and immediate
predecessor against a verified current journal. That would remove the five
publication PRs, but would change the committed-public-intake boundary. It is a
proposal only; Howard's approval is required before implementing it.

## Operator steps

Each block is self-contained. Replace placeholders with reviewed values. For
round 1, the input is the current signed Factory journal export; later rounds
use the immediately preceding decision proof. Always obtain the trusted head
independently from the existing Factory, not from the input proof itself. The
public key must be the existing independently pinned Factory key.

For rounds 2-6, the bound request must already have been published, approved at
its final green SHA, and merged before import. After a block opens the next
request PR, stop. Let its CI finish, have Howard approve that exact SHA, and
merge it through the normal reviewed process. The next block verifies the
approved commit is on fetched main before importing the exact committed bytes.
No block performs a merge or grants signing authority.

## Round 1

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<clean-reviewed-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$ApprovedCommit = '<exact-final-green-commit-approved-by-Howard>'
$ContractPath = '<repository-relative-published-request-for-this-round>'
$ProofInput = '<current-journal-export-for-round-1-or-predecessor-proof-for-later-round>'
$PublicKey = '<existing-Factory-public-key.pem>'
$ExpectedPublicKeyHash = '<independently-pinned-64-hex-public-key-file-hash>'
$TrustedHead = Read-Host 'Independently verified current Factory journal head'
$Tower = 'http://localhost:8769'
$Position = 1
$Output = '<new-temporary-binding-directory>'
if (-not (Test-Path -LiteralPath $FactoryRoot -PathType Container)) { throw 'Existing Factory root required' }
if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or $TrustedHead -notmatch '^[0-9a-f]{64}$') { throw 'Explicit approved commit and current trust required' }
if ($ExpectedPublicKeyHash -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Public key differs' }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne $ApprovedCommit -or (git -C $Checkout status --porcelain)) { throw 'Use a clean approved checkout' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $Checkout merge-base --is-ancestor $ApprovedCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not on fetched main' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Binding = & $Python -B -m tools.bind_next_intcalc_request --proof $ProofInput --public-key $PublicKey --trusted-head $TrustedHead --position $Position --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Binding refused' }
$Bound = $Binding | ConvertFrom-Json
$Published = Join-Path $Checkout $ContractPath
if ($Position -ne 1 -and (Get-FileHash -LiteralPath $Published -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Bound.file_sha256) { throw 'Reviewed published bytes differ; stop for a request PR' }
# Round 1 imports the freshly verified canonical copy of its hash-bound published template.
$ImportPath = if ($Position -eq 1) { $Bound.path } else { $Published }
$JournalPath = Join-Path $Output 'verified-journal.json'
$Proof = Get-Content -LiteralPath $ProofInput -Raw | ConvertFrom-Json
$Journal = if ($Position -eq 1) { $Proof } else { $Proof.journal }
[IO.File]::WriteAllText($JournalPath, ($Journal | ConvertTo-Json -Depth 100 -Compress), [Text.UTF8Encoding]::new($false))
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract $ImportPath --journal $JournalPath --public-key $PublicKey --trusted-head $TrustedHead
if ($LASTEXITCODE -ne 0) { throw 'Import refused' }
Write-Host "Review $($Bound.queue_id) in the existing Factory UI. Howard must review and sign there."
$DecisionSha = Read-Host 'Decision SHA after Howard signs this exact queue item'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Signed decision SHA required' }
$ProofOutput = Join-Path $Output 'decision-proof.json'
$SecureToken = Read-Host 'Current Factory session token' -AsSecureString
$Token = [Net.NetworkCredential]::new('', $SecureToken).Password
try {
  $Headers = @{ Authorization = "Bearer $Token" }
  $Item = Invoke-RestMethod -Uri "$Tower/api/tower/item?id=$($Bound.queue_id)" -Headers $Headers
  if ($Item.bound.contract -ne $Bound.file_sha256) { throw 'Queue bytes differ' }
  Invoke-WebRequest -Uri "$Tower/api/tower/proof?sha256=$DecisionSha" -Headers $Headers -OutFile $ProofOutput
} finally { $Token = $null; $Headers = $null }
$NextTrustedHead = Read-Host 'Current independently verified Factory journal head after this decision'
$NextPosition = 2
$NextDirectory = Join-Path $Checkout ('docs/factory/intcalc-bound-round-' + $NextPosition)
& $Python -B -m tools.bind_next_intcalc_request --proof $ProofOutput --public-key $PublicKey --trusted-head $NextTrustedHead --position $NextPosition --output $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Next request refused; stop' }
$Branch = "codex/intcalc-bound-round-$NextPosition"
git switch -c $Branch
if ($LASTEXITCODE -ne 0) { throw 'New request branch failed' }
git add -- $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
git -c commit.gpgsign=false commit -m "Publish unsigned INTCALC round $NextPosition request"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed' }
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'Push outcome must be reconciled before retry' }
gh pr create --draft --base main --head $Branch --title "Unsigned INTCALC round $NextPosition binding" --body "Unsigned request bound to the verified predecessor; exact final green SHA requires Howard approval before merge and intake."
if ($LASTEXITCODE -ne 0) { throw 'PR outcome must be reconciled before retry' }
Write-Host 'STOP: CI, exact-SHA Howard approval and reviewed merge must finish before the next round.'
```

## Round 2

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<clean-reviewed-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$ApprovedCommit = '<exact-final-green-commit-approved-by-Howard>'
$ContractPath = '<repository-relative-published-request-for-this-round>'
$ProofInput = '<current-journal-export-for-round-1-or-predecessor-proof-for-later-round>'
$PublicKey = '<existing-Factory-public-key.pem>'
$ExpectedPublicKeyHash = '<independently-pinned-64-hex-public-key-file-hash>'
$TrustedHead = Read-Host 'Independently verified current Factory journal head'
$Tower = 'http://localhost:8769'
$Position = 2
$Output = '<new-temporary-binding-directory>'
if (-not (Test-Path -LiteralPath $FactoryRoot -PathType Container)) { throw 'Existing Factory root required' }
if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or $TrustedHead -notmatch '^[0-9a-f]{64}$') { throw 'Explicit approved commit and current trust required' }
if ($ExpectedPublicKeyHash -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Public key differs' }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne $ApprovedCommit -or (git -C $Checkout status --porcelain)) { throw 'Use a clean approved checkout' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $Checkout merge-base --is-ancestor $ApprovedCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not on fetched main' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Binding = & $Python -B -m tools.bind_next_intcalc_request --proof $ProofInput --public-key $PublicKey --trusted-head $TrustedHead --position $Position --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Binding refused' }
$Bound = $Binding | ConvertFrom-Json
$Published = Join-Path $Checkout $ContractPath
if ($Position -ne 1 -and (Get-FileHash -LiteralPath $Published -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Bound.file_sha256) { throw 'Reviewed published bytes differ; stop for a request PR' }
# Round 1 imports the freshly verified canonical copy of its hash-bound published template.
$ImportPath = if ($Position -eq 1) { $Bound.path } else { $Published }
$JournalPath = Join-Path $Output 'verified-journal.json'
$Proof = Get-Content -LiteralPath $ProofInput -Raw | ConvertFrom-Json
$Journal = if ($Position -eq 1) { $Proof } else { $Proof.journal }
[IO.File]::WriteAllText($JournalPath, ($Journal | ConvertTo-Json -Depth 100 -Compress), [Text.UTF8Encoding]::new($false))
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract $ImportPath --journal $JournalPath --public-key $PublicKey --trusted-head $TrustedHead
if ($LASTEXITCODE -ne 0) { throw 'Import refused' }
Write-Host "Review $($Bound.queue_id) in the existing Factory UI. Howard must review and sign there."
$DecisionSha = Read-Host 'Decision SHA after Howard signs this exact queue item'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Signed decision SHA required' }
$ProofOutput = Join-Path $Output 'decision-proof.json'
$SecureToken = Read-Host 'Current Factory session token' -AsSecureString
$Token = [Net.NetworkCredential]::new('', $SecureToken).Password
try {
  $Headers = @{ Authorization = "Bearer $Token" }
  $Item = Invoke-RestMethod -Uri "$Tower/api/tower/item?id=$($Bound.queue_id)" -Headers $Headers
  if ($Item.bound.contract -ne $Bound.file_sha256) { throw 'Queue bytes differ' }
  Invoke-WebRequest -Uri "$Tower/api/tower/proof?sha256=$DecisionSha" -Headers $Headers -OutFile $ProofOutput
} finally { $Token = $null; $Headers = $null }
$NextTrustedHead = Read-Host 'Current independently verified Factory journal head after this decision'
$NextPosition = 3
$NextDirectory = Join-Path $Checkout ('docs/factory/intcalc-bound-round-' + $NextPosition)
& $Python -B -m tools.bind_next_intcalc_request --proof $ProofOutput --public-key $PublicKey --trusted-head $NextTrustedHead --position $NextPosition --output $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Next request refused; stop' }
$Branch = "codex/intcalc-bound-round-$NextPosition"
git switch -c $Branch
if ($LASTEXITCODE -ne 0) { throw 'New request branch failed' }
git add -- $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
git -c commit.gpgsign=false commit -m "Publish unsigned INTCALC round $NextPosition request"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed' }
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'Push outcome must be reconciled before retry' }
gh pr create --draft --base main --head $Branch --title "Unsigned INTCALC round $NextPosition binding" --body "Unsigned request bound to the verified predecessor; exact final green SHA requires Howard approval before merge and intake."
if ($LASTEXITCODE -ne 0) { throw 'PR outcome must be reconciled before retry' }
Write-Host 'STOP: CI, exact-SHA Howard approval and reviewed merge must finish before the next round.'
```

## Round 3

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<clean-reviewed-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$ApprovedCommit = '<exact-final-green-commit-approved-by-Howard>'
$ContractPath = '<repository-relative-published-request-for-this-round>'
$ProofInput = '<current-journal-export-for-round-1-or-predecessor-proof-for-later-round>'
$PublicKey = '<existing-Factory-public-key.pem>'
$ExpectedPublicKeyHash = '<independently-pinned-64-hex-public-key-file-hash>'
$TrustedHead = Read-Host 'Independently verified current Factory journal head'
$Tower = 'http://localhost:8769'
$Position = 3
$Output = '<new-temporary-binding-directory>'
if (-not (Test-Path -LiteralPath $FactoryRoot -PathType Container)) { throw 'Existing Factory root required' }
if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or $TrustedHead -notmatch '^[0-9a-f]{64}$') { throw 'Explicit approved commit and current trust required' }
if ($ExpectedPublicKeyHash -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Public key differs' }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne $ApprovedCommit -or (git -C $Checkout status --porcelain)) { throw 'Use a clean approved checkout' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $Checkout merge-base --is-ancestor $ApprovedCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not on fetched main' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Binding = & $Python -B -m tools.bind_next_intcalc_request --proof $ProofInput --public-key $PublicKey --trusted-head $TrustedHead --position $Position --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Binding refused' }
$Bound = $Binding | ConvertFrom-Json
$Published = Join-Path $Checkout $ContractPath
if ($Position -ne 1 -and (Get-FileHash -LiteralPath $Published -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Bound.file_sha256) { throw 'Reviewed published bytes differ; stop for a request PR' }
# Round 1 imports the freshly verified canonical copy of its hash-bound published template.
$ImportPath = if ($Position -eq 1) { $Bound.path } else { $Published }
$JournalPath = Join-Path $Output 'verified-journal.json'
$Proof = Get-Content -LiteralPath $ProofInput -Raw | ConvertFrom-Json
$Journal = if ($Position -eq 1) { $Proof } else { $Proof.journal }
[IO.File]::WriteAllText($JournalPath, ($Journal | ConvertTo-Json -Depth 100 -Compress), [Text.UTF8Encoding]::new($false))
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract $ImportPath --journal $JournalPath --public-key $PublicKey --trusted-head $TrustedHead
if ($LASTEXITCODE -ne 0) { throw 'Import refused' }
Write-Host "Review $($Bound.queue_id) in the existing Factory UI. Howard must review and sign there."
$DecisionSha = Read-Host 'Decision SHA after Howard signs this exact queue item'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Signed decision SHA required' }
$ProofOutput = Join-Path $Output 'decision-proof.json'
$SecureToken = Read-Host 'Current Factory session token' -AsSecureString
$Token = [Net.NetworkCredential]::new('', $SecureToken).Password
try {
  $Headers = @{ Authorization = "Bearer $Token" }
  $Item = Invoke-RestMethod -Uri "$Tower/api/tower/item?id=$($Bound.queue_id)" -Headers $Headers
  if ($Item.bound.contract -ne $Bound.file_sha256) { throw 'Queue bytes differ' }
  Invoke-WebRequest -Uri "$Tower/api/tower/proof?sha256=$DecisionSha" -Headers $Headers -OutFile $ProofOutput
} finally { $Token = $null; $Headers = $null }
$NextTrustedHead = Read-Host 'Current independently verified Factory journal head after this decision'
$NextPosition = 4
$NextDirectory = Join-Path $Checkout ('docs/factory/intcalc-bound-round-' + $NextPosition)
& $Python -B -m tools.bind_next_intcalc_request --proof $ProofOutput --public-key $PublicKey --trusted-head $NextTrustedHead --position $NextPosition --output $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Next request refused; stop' }
$Branch = "codex/intcalc-bound-round-$NextPosition"
git switch -c $Branch
if ($LASTEXITCODE -ne 0) { throw 'New request branch failed' }
git add -- $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
git -c commit.gpgsign=false commit -m "Publish unsigned INTCALC round $NextPosition request"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed' }
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'Push outcome must be reconciled before retry' }
gh pr create --draft --base main --head $Branch --title "Unsigned INTCALC round $NextPosition binding" --body "Unsigned request bound to the verified predecessor; exact final green SHA requires Howard approval before merge and intake."
if ($LASTEXITCODE -ne 0) { throw 'PR outcome must be reconciled before retry' }
Write-Host 'STOP: CI, exact-SHA Howard approval and reviewed merge must finish before the next round.'
```

## Round 4

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<clean-reviewed-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$ApprovedCommit = '<exact-final-green-commit-approved-by-Howard>'
$ContractPath = '<repository-relative-published-request-for-this-round>'
$ProofInput = '<current-journal-export-for-round-1-or-predecessor-proof-for-later-round>'
$PublicKey = '<existing-Factory-public-key.pem>'
$ExpectedPublicKeyHash = '<independently-pinned-64-hex-public-key-file-hash>'
$TrustedHead = Read-Host 'Independently verified current Factory journal head'
$Tower = 'http://localhost:8769'
$Position = 4
$Output = '<new-temporary-binding-directory>'
if (-not (Test-Path -LiteralPath $FactoryRoot -PathType Container)) { throw 'Existing Factory root required' }
if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or $TrustedHead -notmatch '^[0-9a-f]{64}$') { throw 'Explicit approved commit and current trust required' }
if ($ExpectedPublicKeyHash -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Public key differs' }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne $ApprovedCommit -or (git -C $Checkout status --porcelain)) { throw 'Use a clean approved checkout' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $Checkout merge-base --is-ancestor $ApprovedCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not on fetched main' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Binding = & $Python -B -m tools.bind_next_intcalc_request --proof $ProofInput --public-key $PublicKey --trusted-head $TrustedHead --position $Position --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Binding refused' }
$Bound = $Binding | ConvertFrom-Json
$Published = Join-Path $Checkout $ContractPath
if ($Position -ne 1 -and (Get-FileHash -LiteralPath $Published -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Bound.file_sha256) { throw 'Reviewed published bytes differ; stop for a request PR' }
# Round 1 imports the freshly verified canonical copy of its hash-bound published template.
$ImportPath = if ($Position -eq 1) { $Bound.path } else { $Published }
$JournalPath = Join-Path $Output 'verified-journal.json'
$Proof = Get-Content -LiteralPath $ProofInput -Raw | ConvertFrom-Json
$Journal = if ($Position -eq 1) { $Proof } else { $Proof.journal }
[IO.File]::WriteAllText($JournalPath, ($Journal | ConvertTo-Json -Depth 100 -Compress), [Text.UTF8Encoding]::new($false))
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract $ImportPath --journal $JournalPath --public-key $PublicKey --trusted-head $TrustedHead
if ($LASTEXITCODE -ne 0) { throw 'Import refused' }
Write-Host "Review $($Bound.queue_id) in the existing Factory UI. Howard must review and sign there."
$DecisionSha = Read-Host 'Decision SHA after Howard signs this exact queue item'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Signed decision SHA required' }
$ProofOutput = Join-Path $Output 'decision-proof.json'
$SecureToken = Read-Host 'Current Factory session token' -AsSecureString
$Token = [Net.NetworkCredential]::new('', $SecureToken).Password
try {
  $Headers = @{ Authorization = "Bearer $Token" }
  $Item = Invoke-RestMethod -Uri "$Tower/api/tower/item?id=$($Bound.queue_id)" -Headers $Headers
  if ($Item.bound.contract -ne $Bound.file_sha256) { throw 'Queue bytes differ' }
  Invoke-WebRequest -Uri "$Tower/api/tower/proof?sha256=$DecisionSha" -Headers $Headers -OutFile $ProofOutput
} finally { $Token = $null; $Headers = $null }
$NextTrustedHead = Read-Host 'Current independently verified Factory journal head after this decision'
$NextPosition = 5
$NextDirectory = Join-Path $Checkout ('docs/factory/intcalc-bound-round-' + $NextPosition)
& $Python -B -m tools.bind_next_intcalc_request --proof $ProofOutput --public-key $PublicKey --trusted-head $NextTrustedHead --position $NextPosition --output $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Next request refused; stop' }
$Branch = "codex/intcalc-bound-round-$NextPosition"
git switch -c $Branch
if ($LASTEXITCODE -ne 0) { throw 'New request branch failed' }
git add -- $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
git -c commit.gpgsign=false commit -m "Publish unsigned INTCALC round $NextPosition request"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed' }
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'Push outcome must be reconciled before retry' }
gh pr create --draft --base main --head $Branch --title "Unsigned INTCALC round $NextPosition binding" --body "Unsigned request bound to the verified predecessor; exact final green SHA requires Howard approval before merge and intake."
if ($LASTEXITCODE -ne 0) { throw 'PR outcome must be reconciled before retry' }
Write-Host 'STOP: CI, exact-SHA Howard approval and reviewed merge must finish before the next round.'
```

## Round 5

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<clean-reviewed-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$ApprovedCommit = '<exact-final-green-commit-approved-by-Howard>'
$ContractPath = '<repository-relative-published-request-for-this-round>'
$ProofInput = '<current-journal-export-for-round-1-or-predecessor-proof-for-later-round>'
$PublicKey = '<existing-Factory-public-key.pem>'
$ExpectedPublicKeyHash = '<independently-pinned-64-hex-public-key-file-hash>'
$TrustedHead = Read-Host 'Independently verified current Factory journal head'
$Tower = 'http://localhost:8769'
$Position = 5
$Output = '<new-temporary-binding-directory>'
if (-not (Test-Path -LiteralPath $FactoryRoot -PathType Container)) { throw 'Existing Factory root required' }
if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or $TrustedHead -notmatch '^[0-9a-f]{64}$') { throw 'Explicit approved commit and current trust required' }
if ($ExpectedPublicKeyHash -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Public key differs' }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne $ApprovedCommit -or (git -C $Checkout status --porcelain)) { throw 'Use a clean approved checkout' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $Checkout merge-base --is-ancestor $ApprovedCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not on fetched main' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Binding = & $Python -B -m tools.bind_next_intcalc_request --proof $ProofInput --public-key $PublicKey --trusted-head $TrustedHead --position $Position --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Binding refused' }
$Bound = $Binding | ConvertFrom-Json
$Published = Join-Path $Checkout $ContractPath
if ($Position -ne 1 -and (Get-FileHash -LiteralPath $Published -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Bound.file_sha256) { throw 'Reviewed published bytes differ; stop for a request PR' }
# Round 1 imports the freshly verified canonical copy of its hash-bound published template.
$ImportPath = if ($Position -eq 1) { $Bound.path } else { $Published }
$JournalPath = Join-Path $Output 'verified-journal.json'
$Proof = Get-Content -LiteralPath $ProofInput -Raw | ConvertFrom-Json
$Journal = if ($Position -eq 1) { $Proof } else { $Proof.journal }
[IO.File]::WriteAllText($JournalPath, ($Journal | ConvertTo-Json -Depth 100 -Compress), [Text.UTF8Encoding]::new($false))
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract $ImportPath --journal $JournalPath --public-key $PublicKey --trusted-head $TrustedHead
if ($LASTEXITCODE -ne 0) { throw 'Import refused' }
Write-Host "Review $($Bound.queue_id) in the existing Factory UI. Howard must review and sign there."
$DecisionSha = Read-Host 'Decision SHA after Howard signs this exact queue item'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Signed decision SHA required' }
$ProofOutput = Join-Path $Output 'decision-proof.json'
$SecureToken = Read-Host 'Current Factory session token' -AsSecureString
$Token = [Net.NetworkCredential]::new('', $SecureToken).Password
try {
  $Headers = @{ Authorization = "Bearer $Token" }
  $Item = Invoke-RestMethod -Uri "$Tower/api/tower/item?id=$($Bound.queue_id)" -Headers $Headers
  if ($Item.bound.contract -ne $Bound.file_sha256) { throw 'Queue bytes differ' }
  Invoke-WebRequest -Uri "$Tower/api/tower/proof?sha256=$DecisionSha" -Headers $Headers -OutFile $ProofOutput
} finally { $Token = $null; $Headers = $null }
$NextTrustedHead = Read-Host 'Current independently verified Factory journal head after this decision'
$NextPosition = 6
$NextDirectory = Join-Path $Checkout ('docs/factory/intcalc-bound-round-' + $NextPosition)
& $Python -B -m tools.bind_next_intcalc_request --proof $ProofOutput --public-key $PublicKey --trusted-head $NextTrustedHead --position $NextPosition --output $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Next request refused; stop' }
$Branch = "codex/intcalc-bound-round-$NextPosition"
git switch -c $Branch
if ($LASTEXITCODE -ne 0) { throw 'New request branch failed' }
git add -- $NextDirectory
if ($LASTEXITCODE -ne 0) { throw 'Staging failed' }
git -c commit.gpgsign=false commit -m "Publish unsigned INTCALC round $NextPosition request"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed' }
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'Push outcome must be reconciled before retry' }
gh pr create --draft --base main --head $Branch --title "Unsigned INTCALC round $NextPosition binding" --body "Unsigned request bound to the verified predecessor; exact final green SHA requires Howard approval before merge and intake."
if ($LASTEXITCODE -ne 0) { throw 'PR outcome must be reconciled before retry' }
Write-Host 'STOP: CI, exact-SHA Howard approval and reviewed merge must finish before the next round.'
```

## Round 6

```powershell
$ErrorActionPreference = 'Stop'
$Checkout = '<clean-reviewed-Windows-checkout>'
$FactoryRoot = '<existing-Windows-Factory-root>'
$Python = '<installed-Windows-Tower-Python>'
$ApprovedCommit = '<exact-final-green-commit-approved-by-Howard>'
$ContractPath = '<repository-relative-published-request-for-this-round>'
$ProofInput = '<current-journal-export-for-round-1-or-predecessor-proof-for-later-round>'
$PublicKey = '<existing-Factory-public-key.pem>'
$ExpectedPublicKeyHash = '<independently-pinned-64-hex-public-key-file-hash>'
$TrustedHead = Read-Host 'Independently verified current Factory journal head'
$Tower = 'http://localhost:8769'
$Position = 6
$Output = '<new-temporary-binding-directory>'
if (-not (Test-Path -LiteralPath $FactoryRoot -PathType Container)) { throw 'Existing Factory root required' }
if ($ApprovedCommit -notmatch '^[0-9a-f]{40}$' -or $TrustedHead -notmatch '^[0-9a-f]{64}$') { throw 'Explicit approved commit and current trust required' }
if ($ExpectedPublicKeyHash -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath $PublicKey -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPublicKeyHash) { throw 'Public key differs' }
if ((git -C $Checkout rev-parse HEAD).Trim() -ne $ApprovedCommit -or (git -C $Checkout status --porcelain)) { throw 'Use a clean approved checkout' }
git -C $Checkout fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $Checkout merge-base --is-ancestor $ApprovedCommit origin/main
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not on fetched main' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONUTF8 = '1'
$Binding = & $Python -B -m tools.bind_next_intcalc_request --proof $ProofInput --public-key $PublicKey --trusted-head $TrustedHead --position $Position --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Binding refused' }
$Bound = $Binding | ConvertFrom-Json
$Published = Join-Path $Checkout $ContractPath
if ($Position -ne 1 -and (Get-FileHash -LiteralPath $Published -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Bound.file_sha256) { throw 'Reviewed published bytes differ; stop for a request PR' }
# Round 1 imports the freshly verified canonical copy of its hash-bound published template.
$ImportPath = if ($Position -eq 1) { $Bound.path } else { $Published }
$JournalPath = Join-Path $Output 'verified-journal.json'
$Proof = Get-Content -LiteralPath $ProofInput -Raw | ConvertFrom-Json
$Journal = if ($Position -eq 1) { $Proof } else { $Proof.journal }
[IO.File]::WriteAllText($JournalPath, ($Journal | ConvertTo-Json -Depth 100 -Compress), [Text.UTF8Encoding]::new($false))
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract $ImportPath --journal $JournalPath --public-key $PublicKey --trusted-head $TrustedHead
if ($LASTEXITCODE -ne 0) { throw 'Import refused' }
Write-Host "Review $($Bound.queue_id) in the existing Factory UI. Howard must review and sign there."
$DecisionSha = Read-Host 'Decision SHA after Howard signs this exact queue item'
if ($DecisionSha -notmatch '^[0-9a-f]{64}$') { throw 'Signed decision SHA required' }
$ProofOutput = Join-Path $Output 'decision-proof.json'
$SecureToken = Read-Host 'Current Factory session token' -AsSecureString
$Token = [Net.NetworkCredential]::new('', $SecureToken).Password
try {
  $Headers = @{ Authorization = "Bearer $Token" }
  $Item = Invoke-RestMethod -Uri "$Tower/api/tower/item?id=$($Bound.queue_id)" -Headers $Headers
  if ($Item.bound.contract -ne $Bound.file_sha256) { throw 'Queue bytes differ' }
  Invoke-WebRequest -Uri "$Tower/api/tower/proof?sha256=$DecisionSha" -Headers $Headers -OutFile $ProofOutput
} finally { $Token = $null; $Headers = $null }
Write-Host 'Sixth proof exported. Separate verification and release checklist still apply. No activation or Phase 2 execution.'
```
