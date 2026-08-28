param(
  [ValidateSet("build", "verify")][string]$Command = "verify",
  [string]$LegacyRoot = $env:CARDDEMO_UPSTREAM_ROOT
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
if ([string]::IsNullOrWhiteSpace($LegacyRoot)) {
  $LegacyRoot = Join-Path (Split-Path $ProjectDir -Parent) "carddemo-upstream"
}
function Run-Python {
  Invoke-FactoryDarkPython @args
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Command -eq "build") {
  $Rehearsal = Join-Path $ProjectDir "data-modernization\rehearsal"
  foreach ($Name in @("plan.json", "cutover.approval.json", "checkpoint.json", "receipt.json")) {
    $Path = Join-Path $Rehearsal $Name
    if (Test-Path $Path) { Remove-Item -Force $Path }
  }
  Run-Python -m lightyear_data rehearse-offline --project-root $ProjectDir --output-root $ProjectDir
  exit 0
}

$Output = Join-Path $ProjectDir "work\migration-rehearsal-verify"
if (Test-Path $Output) { Remove-Item -Recurse -Force $Output }
New-Item -ItemType Directory -Force -Path $Output | Out-Null
Run-Python -m lightyear_data build --legacy-root $LegacyRoot --output-root $Output
Run-Python -m lightyear_data rehearse-offline --project-root $Output --output-root $Output
Run-Python -m lightyear_data validate-rehearsal --project-root $Output
foreach ($Name in @("plan.json", "cutover.approval.json", "checkpoint.json", "receipt.json")) {
  $Expected = Join-Path $ProjectDir "data-modernization\rehearsal\$Name"
  $Actual = Join-Path $Output "data-modernization\rehearsal\$Name"
  if (-not (Test-Path $Actual) -or (Get-FileHash $Expected).Hash -ne (Get-FileHash $Actual).Hash) {
    throw "Generated migration rehearsal artifact differs: $Name"
  }
}
Run-Python -m unittest tests.test_migration_rehearsal -v
Write-Host "AUTHFRDS offline CDC, resume, dual-target reconciliation, cutover, and rollback rehearsal is deterministic."
