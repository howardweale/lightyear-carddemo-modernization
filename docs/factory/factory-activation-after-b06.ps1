# AFTER B06 CLEANUP IS SEALED ONLY. Save operator-selected paths; do not reuse B06.
param(
  [Parameter(Mandatory=$true)][string]$Checkout,
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$FactoryRoot,
  [Parameter(Mandatory=$true)][string]$FactoryAuthority,
  [Parameter(Mandatory=$true)][string]$CleanupSeal,
  [string]$SnapshotCommit = 'b582d3ebb0a01464f20120c38760b9f97b0f1927'
)
$ErrorActionPreference = 'Stop'
if ($CleanupSeal -notmatch '^[0-9a-f]{64}$') { throw 'Supply the independently verified B06 cleanup seal' }
if ((Read-Host 'Confirm B06 actual absence and authenticated cleanup verified; type SEALED') -cne 'SEALED') { throw 'Cleanup not confirmed' }
if ((Get-NetTCPConnection -LocalPort 8769 -State Listen -ErrorAction SilentlyContinue)) { throw '8769 already occupied; do not restart it' }
if (Test-Path -LiteralPath $FactoryRoot) { throw 'Snapshot destination must be new' }
if (Test-Path -LiteralPath $FactoryAuthority) { throw 'Existing authority: stop and use its reviewed reuse procedure; never replace' }
$FactoryFull = [IO.Path]::GetFullPath($FactoryRoot)
$AuthorityFull = [IO.Path]::GetFullPath($FactoryAuthority)
if ($FactoryFull -match '(?i)b06' -or $AuthorityFull -match '(?i)b06') { throw 'Factory paths must be separate from B06' }
if ($AuthorityFull.StartsWith($FactoryFull.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Authority must be outside data root' }
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH='src;.'; $env:PYTHONUTF8='1'
if ((git rev-parse HEAD).Trim() -ne $SnapshotCommit) { throw 'Use the reviewed snapshot checkout; no checkout changes here' }
# Public snapshot only; no authority, credential, service or execution mutation by importer.
$TrustText = & $Python -B tools/import_factory_tower_snapshot.py --repository $Checkout --commit $SnapshotCommit --root $FactoryRoot
if ($LASTEXITCODE -ne 0) { throw 'Snapshot import refused' }
$TrustText
if ((Read-Host 'Independently verify the printed index hash against the reviewed snapshot; type VERIFIED') -cne 'VERIFIED') { throw 'Trust not installed' }
& $Python -B -m lightyear_control_tower provision --authority $FactoryAuthority --scope factory --operator-id howard --operator-name Howard
if ($LASTEXITCODE -ne 0) { throw 'Provision refused' }
# Keep provisioned individual credential with Howard; do not paste it into chat/logs.
$TrustPath = Join-Path (Split-Path -Parent $FactoryAuthority) 'factory-evidence-trust.json'
if (Test-Path -LiteralPath $TrustPath) { throw 'Trust already exists' }
[IO.File]::WriteAllText($TrustPath,($TrustText -join "`n"),[Text.UTF8Encoding]::new($false))
& $Python -B -m lightyear_control_tower grant-roles --root $FactoryRoot --authority $FactoryAuthority --operator-id howard --roles operator qualification-approver campaign-authorizer business-owner --workloads factory:INTCALC factory:POSTTRAN factory:B06 factory:B07 factory:factory --reason 'Factory public development review after B06 cleanup'
if ($LASTEXITCODE -ne 0) { throw 'Role grant refused' }
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract docs/factory/tower-backfill-request-2026-10-12.json
if ($LASTEXITCODE -ne 0) { throw 'Backfill import refused' }
& $Python -B -m lightyear_control_tower.factory_import --repository $Checkout --root $FactoryRoot --contract docs/factory/tower-posttran-review-request-2026-10-12.json
if ($LASTEXITCODE -ne 0) { throw 'POSTTRAN request import refused' }
# Terminal A, foreground operator service; port 8768 is never referenced or changed.
& $Python -B -m lightyear_control_tower serve --root $FactoryRoot --authority $FactoryAuthority --port 8769
# Terminal B: open the human signing UI. No CLI credential/private-key extraction.
Start-Process 'http://127.0.0.1:8769/'
Read-Host 'Howard: sign in with your individual credential; Work queue -> factory-decision-backfill. Review every dated record/hash/condition; accept once. Confirm signed Decision history before pressing Enter'
Read-Host 'Howard: Work queue -> POSTTRAN twin-human-review. Review source-bound rows; enter an explicit outcome and reason for EACH item; sign once. Confirm signed Decision history before pressing Enter'
# Keep the signed proof exports and current journal head. Signing is human-only.
# A separately verified factory-consumer-trust/1 file is required to enable signed-only consumption.
# Do not set LIGHTYEAR_FACTORY_AUTHORITY until that proof, contract and trusted head are verified.
# This fixed snapshot omits later unmerged decisions; import an explicitly reviewed later snapshot
# separately rather than changing this command's head silently. No native/spend/release is activated.
