param(
    [Parameter(Mandatory = $true)][string]$InputsRoot,
    [string]$Python = (Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe'),
    [string]$OutputRoot = (Join-Path $env:USERPROFILE ('ms67-network-' + [guid]::NewGuid().ToString('N'))),
    [string]$RecoveryState,
    [switch]$OriginalProcessStopped
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$tool = Join-Path $repo 'tools\cloudbank_network_enforcement.py'
$inputsPath = (Resolve-Path -LiteralPath $InputsRoot).Path
foreach ($file in @($Python, $tool, "$inputsPath\image-lock.json", "$inputsPath\ms64-receipt.json", "$inputsPath\platform-profile.json")) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing file: $file" }
}
if (Test-Path -LiteralPath $OutputRoot) { throw 'OutputRoot must be a new directory' }
if ($RecoveryState -and (-not $OriginalProcessStopped -or -not (Test-Path -LiteralPath $RecoveryState -PathType Leaf))) {
    throw 'Recovery needs the signed state file and -OriginalProcessStopped after the original process has stopped'
}
$null = Get-Command gcloud -ErrorAction Stop
$null = Get-Command kubectl -ErrorAction Stop
$env:CLOUDSDK_CORE_ACCOUNT = 'howard.weale@gmail.com'
$env:CLOUDSDK_CORE_PROJECT = 'lightyear-ms67-nonproduction'
$env:PYTHONPATH = Join-Path $repo 'src'
$env:LIGHTYEAR_NON_PRODUCTION_ACK = 'I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS'
gcloud container clusters get-credentials cloudbank-ms67 --region us-west1 --project lightyear-ms67-nonproduction
if ($LASTEXITCODE -ne 0) { throw 'Cluster credentials failed' }
$common = @('--project', 'lightyear-ms67-nonproduction', '--region', 'us-west1',
    '--cluster', 'cloudbank-ms67', '--namespace', 'cloudbank-ms67', '--signer', 'howard.weale@gmail.com',
    '--evidence-bucket', 'gs://lightyear-ms67-nonproduction-ms67-evidence/network-enforcement',
    '--image-lock', "$inputsPath\image-lock.json", '--ms64-receipt', "$inputsPath\ms64-receipt.json",
    '--platform-profile', "$inputsPath\platform-profile.json", '--source-instance', 'cloudbank-ms67-postgres')
Write-Output "MS67_NETWORK_RUN=$OutputRoot"
if ($RecoveryState) {
    & $Python $tool recover @common --output-root $OutputRoot --recovery-state $RecoveryState --original-process-stopped
    if ($LASTEXITCODE -ne 0) { throw 'Network recovery stopped; inspect the saved result' }
    Write-Output 'MS67_NETWORK_RECOVERY=PASSED'
} else {
    & $Python $tool run @common --output-root $OutputRoot
    if ($LASTEXITCODE -ne 0) { throw 'Network checks stopped; inspect the saved reason and recovery status' }
    & $Python $tool verify @common --observation "$OutputRoot\network-enforcement.observation.json"
    if ($LASTEXITCODE -ne 0) { throw 'Independent network verification failed' }
    Write-Output 'MS67_NETWORK_VERIFICATION=PASSED'
}
