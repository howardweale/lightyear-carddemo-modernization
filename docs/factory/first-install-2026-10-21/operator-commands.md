# Howard-only terminal commands: do not run during installation
These are instructions for Howard AFTER exact-commit installation approval and
successful disabled installation. Codex must not execute these commands, collect
their output, read the credential/private key, or open a signing endpoint.
Use your own non-transcribed, non-elevated terminal. Do not enable shell tracing,
PowerShell transcription, screen recording or terminal capture for this procedure.
If organizational logging cannot be disabled, arrange a private operator session
before creating identity/key material. Never paste credentials or private keys into
chat, Git, command arguments or environment variables.

The provision command creates the identity credential AND Ed25519 key files.
It will not recover the unverified old private key. There is no silent migration.
Runtime and operator handoff are separate; the installer invokes none of this.

First obtain the exact CI bundle using [download and staging commands](bundle-download.md).
That separate procedure stops before installation.

## 1. Set paths, verify installed commit, prepare public snapshot
Use a separate clean public repository checkout, never the dirty working trees.

    $ErrorActionPreference = 'Stop'
    $Runtime = 'C:\ProgramData\Lightyear\FactoryRuntime-v1'
    $Container = 'C:\ProgramData\Lightyear\FactoryData-v1'
    $Root = Join-Path $Container 'snapshot'
    $Authority = 'C:\ProgramData\Lightyear\FactoryAuthority\authority.json'
    $AuthorityFolder = Split-Path $Authority
    $Python = Join-Path $Runtime 'python\python.exe'
    $Entry = Join-Path $Runtime 'app\tools\factory_install\entry.py'
    $Repo = '<clean-public-checkout>'
    $Commit = '<exact-approved-installation-commit>'
    $Receipt = Get-Content (Join-Path $Container 'installation-receipt.json') -Raw | ConvertFrom-Json
    if ($Receipt.source_commit -ne $Commit -or $Receipt.operator_sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { throw 'Wrong installation or identity' }
    if ((git -C $Repo rev-parse HEAD).Trim() -ne $Commit -or (git -C $Repo status --porcelain)) { throw 'Wrong or dirty public checkout' }
    if (Test-Path -LiteralPath $Root) { throw 'Snapshot already exists; preserve it' }
    $SnapshotTrustText = (& $Python -I -B $Entry snapshot --repository $Repo --commit $Commit --root $Root) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0) { throw 'Public snapshot refused' }
    $SnapshotTrust = $SnapshotTrustText | ConvertFrom-Json
    if ($SnapshotTrust.schema -ne 'factory-evidence-trust/1') { throw 'Wrong public snapshot receipt' }
    if ((Get-FileHash -LiteralPath (Join-Path $Root 'work/control-tower/factory-evidence-index.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $SnapshotTrust.index_sha256) { throw 'Public index digest differs' }

Compare the public index digest against the imported index and exact reviewed
source. Read the additive MS-106 correction alongside the original historical
records. The snapshot tool's legacy evidence list does not itself apply this
correction to every UI or generated status field; such fields remain historical
until separately reconciled. Do not treat a UI activation label as proof.

## 2. Create your identity and keys; install public evidence trust
The authority folder should be empty and Howard-only. Stop if any authority/key
already exists. Do not overwrite or regenerate. The CLI creates a credential file;
it does not print the credential or private key. Suppress its status output too.

    if (@(Get-ChildItem -LiteralPath $AuthorityFolder -Force).Count -ne 0) { throw 'Authority directory is not empty' }
    & $Python -I -B $Entry tower provision --authority $Authority --scope factory --operator-id howard --operator-name Howard | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Provisioning failed; inspect privately, never retry blindly' }
    $TrustPath = Join-Path $AuthorityFolder 'factory-evidence-trust.json'
    if (Test-Path -LiteralPath $TrustPath) { throw 'Trust file already exists' }
    [IO.File]::WriteAllText($TrustPath,$SnapshotTrustText,[Text.UTF8Encoding]::new($false))
    & $Python -I -B $Entry tower grant-roles --root $Root --authority $Authority --operator-id howard --roles operator qualification-approver campaign-authorizer business-owner --workloads factory:INTCALC factory:POSTTRAN factory:B06 factory:B07 factory:factory --reason 'Howard first-install setup; no run or spending approval' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Role assignment failed' }

Keep your credential and private-key backup under your own encrypted/offline custody.
No assistant will inspect or record key output. When ready, YOU deliberately submit
only authority.public.pem through the separate reviewed public-key handoff. Do not
submit authority.json, authority.key.pem or authority.credential.txt. No login or
key output is included in installation receipts or uploaded CI assets.

## 3. Prepare and import a new unsigned seven-record contract
Do not import the old mixed-source/superseded October 12/14 request. The current
importer requires one committed source snapshot and the complete historical
inventory. This command reconstructs that inventory without signing anything.

    $ContractPath = Join-Path $Container 'backfill-contract-first-install.json'
    & $Python -I -B $Entry prepare-backfill --repository $Repo --commit $Commit --output $ContractPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unsigned historical inventory refused' }
    $Contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json
    if ($Contract.details.records.Count -ne 7) { throw 'Inventory changed; obtain review' }
    & $Python -I -B $Entry import --repository $Repo --root $Root --contract $ContractPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Import refused; preserve all records' }

Review all seven records listed in ms106-correction.md, source hashes, original
dates and conditions. Accepting historical chat decisions today does not attest
that MS-106 installation, prior signatures or signed-only mode happened in October.

## 4. Start manually and sign the reviewed backfill yourself
In a second private non-elevated terminal, start the server in the foreground:

    & 'C:\ProgramData\Lightyear\FactoryRuntime-v1\Start-FactoryTower.ps1'

Verify the process listens on 127.0.0.1:8769 only using Get-NetTCPConnection;
stop it with Ctrl+C if the address, executable or task identity differs.
No firewall command is needed. Back in the first private terminal, authenticate
without echoing the credential or session token. The following operations write
your journal and create your signature; they are never installation checks.

    $Tower = 'http://127.0.0.1:8769/api/tower'
    $Session = $null
    $Headers = $null
    try {
        $LoginBody = @{credential=[IO.File]::ReadAllText((Join-Path $AuthorityFolder 'authority.credential.txt')).Trim()} | ConvertTo-Json -Compress
        $Session = Invoke-RestMethod -Method Post -Uri "$Tower/session" -ContentType 'application/json' -Body $LoginBody
        $LoginBody = $null
        $Headers = @{Authorization=('Bearer '+$Session.token)}
        $Queue = Invoke-RestMethod -Uri "$Tower/queue" -Headers $Headers
        $Items = @($Queue.items | Where-Object kind -eq 'factory-decision-backfill')
        if ($Items.Count -ne 1 -or !$Items[0].decidable) { throw 'Select and review exact backfill; do not guess' }
        $Review = Invoke-RestMethod -Method Post -Uri "$Tower/review" -Headers $Headers -ContentType 'application/json' -Body (@{id=$Items[0].id}|ConvertTo-Json)
        $ExpectedContractSHA = (Get-FileHash -LiteralPath $ContractPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Review.bound.contract -ne $ExpectedContractSHA) { throw 'Reviewed contract differs from the seven-record file' }
        if ($Review.latest_decision) { throw 'A decision already exists; inspect it instead of signing again' }
        # Inspect only PUBLIC review data, not $Session, $Headers or login/key files.
        $Review.evidence_view
        $Reason = Read-Host 'Your reason after reviewing all seven exact historical records'
        if ((Read-Host 'Type SIGN SEVEN HISTORICAL RECORDS to accept them now') -cne 'SIGN SEVEN HISTORICAL RECORDS') { throw 'No signature requested' }
        $DecisionBody = @{
            item_id=$Review.id;bound=$Review.bound;previous_decision_sha256=$null
            outcome='accept';reason=$Reason;request_id=[guid]::NewGuid().ToString()
        } | ConvertTo-Json -Depth 30 -Compress
        $Decision = Invoke-RestMethod -Method Post -Uri "$Tower/decide" -Headers $Headers -ContentType 'application/json' -Body $DecisionBody
        $ProofPath = Join-Path $Container 'backfill-proof-first-install.json'
        if (Test-Path -LiteralPath $ProofPath) { throw 'Preserve existing proof; do not overwrite' }
        # This GET countersigns journal material: Howard intentionally performs it.
        Invoke-WebRequest -UseBasicParsing -Uri "$Tower/proof?sha256=$($Decision.content_sha256)" -Headers $Headers -OutFile $ProofPath
        $Proof = Get-Content -LiteralPath $ProofPath -Raw | ConvertFrom-Json
        $Current = Invoke-RestMethod -Uri "$Tower/queue" -Headers $Headers
        $PublicKey = Join-Path $AuthorityFolder 'authority.public.pem'
        $HeadLines = @(& $Python -I -B (Join-Path $Runtime 'app\tools\factory_install\journal_head.py') --root $Root --public-key $PublicKey)
        if ($LASTEXITCODE -ne 0 -or $HeadLines.Count -ne 1) { throw 'Local journal signature verification refused' }
        $TrustedHead = $HeadLines[0].Trim()
        if ($TrustedHead -notmatch '^[0-9a-f]{64}$' -or $Current.journal_head_sha256 -ne $TrustedHead -or $Proof.journal.journal_head_sha256 -ne $TrustedHead) { throw 'Head differs; obtain a new reviewed public proof' }
    } finally {
        $LoginBody=$null; $Headers=$null; $Session=$null
    }

Do not rerun a decision after timeout/unknown response: inspect Decision history
first. The current request UUID prevents duplicate identical submissions, but this
example intentionally contains no retry. The journal-head command reads only the
Factory ownership binding, public key and a read-only SQLite snapshot. It checks
every event's sequence, previous digest, content digest and Ed25519 signature,
then emits only the computed head. It never initializes a service, reads private
keys, signs, authenticates or calls Tower. Missing/empty/wrong-key/tampered journals
fail closed. A changed head refuses the old proof; inspect privately before
obtaining a fresh proof. This verifies the local chain, not an external rollback
anchor. Do not obtain proofs automatically as routine health/status checks.

## 5. Verify and enable signed-only in your own terminal
The consumer configuration embeds PUBLIC proof/contract JSON objects (not filenames).
Create it only after the above succeeds; no private key or login belongs in it.

    $PublicKey = Join-Path $AuthorityFolder 'authority.public.pem'
    $ConsumerPath = Join-Path $AuthorityFolder 'factory-consumer-trust.json'
    if (Test-Path -LiteralPath $ConsumerPath) { throw 'Preserve existing consumer trust' }
    $Config = @{
        schema='factory-consumer-trust/1';public_key=$PublicKey;trusted_head=$TrustedHead
        backfill_proof=$Proof;backfill_contract=$Contract;evidence_root=$Root
    } | ConvertTo-Json -Depth 100
    [IO.File]::WriteAllText($ConsumerPath,$Config,[Text.UTF8Encoding]::new($false))
    $PreviousSetting=$env:LIGHTYEAR_FACTORY_AUTHORITY
    $env:LIGHTYEAR_FACTORY_AUTHORITY=$ConsumerPath
    & $Python -I -B $Entry check-consumer | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $env:LIGHTYEAR_FACTORY_AUTHORITY=$PreviousSetting
        throw 'Verification refused; preserve config for inspection, no persistent activation'
    }
    if ((Read-Host 'Type ENABLE SIGNED ONLY after verification') -cne 'ENABLE SIGNED ONLY') {
        $env:LIGHTYEAR_FACTORY_AUTHORITY=$PreviousSetting
        throw 'Persistent activation not requested'
    }
    [Environment]::SetEnvironmentVariable('LIGHTYEAR_FACTORY_AUTHORITY',$ConsumerPath,'User')

Restart each consumer from a new Howard session and verify that it picks up this
setting. This does not configure CI or other accounts. Once configured, missing,
invalid or stale proofs must fail rather than fall back. Refresh proof/current head
together after later journal decisions; keep previous snapshots for audit.

After stopping the foreground server with Ctrl+C, enable your login task and
start it yourself (do not start two copies):

    Enable-ScheduledTask -TaskName 'Lightyear-FactoryTower-Howard' | Out-Null
    Start-ScheduledTask -TaskName 'Lightyear-FactoryTower-Howard'

Inspect the task principal, executable and loopback listener again. Record only
public operational acceptance facts if you choose to publish them; never login or
key output. POSTTRAN still waits for fresh new-key preparation and your separate
exact-request signature. This procedure gives no model, native-run or spend approval.