param(
    [Parameter(Mandatory = $true)][string]$InputsRoot,
    [string]$Python = (Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\platform\bundledpython\python.exe'),
    [string]$OutputRoot = (Join-Path $env:USERPROFILE ('ms67-runtime-identity-' + [guid]::NewGuid().ToString('N')))
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$tool = Join-Path $repo 'tools\cloudbank_runtime_identity.py'
$inputsPath = (Resolve-Path -LiteralPath $InputsRoot).Path
foreach ($file in @($Python, $tool, "$inputsPath\image-lock.json", "$inputsPath\ms64-receipt.json", "$inputsPath\platform-profile.json")) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing file: $file" }
}
if (Test-Path -LiteralPath $OutputRoot) { throw 'OutputRoot must be a new directory' }
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
    '--evidence-bucket', 'gs://lightyear-ms67-nonproduction-ms67-evidence/runtime-identity',
    '--image-lock', "$inputsPath\image-lock.json", '--ms64-receipt', "$inputsPath\ms64-receipt.json",
    '--platform-profile', "$inputsPath\platform-profile.json")
Write-Output "MS67_RUNTIME_IDENTITY_RUN=$OutputRoot"
# The run checks all eight services before submitting its first patch.
& $Python $tool run @common --output-root $OutputRoot
if ($LASTEXITCODE -ne 0) { throw 'Runtime identity rollout stopped; inspect its reason and phase' }
& $Python $tool verify @common --observation "$OutputRoot\runtime-identity.observation.json"
if ($LASTEXITCODE -ne 0) { throw 'Independent runtime identity verification failed' }
Write-Output 'MS67_RUNTIME_IDENTITY_VERIFICATION=PASSED'
