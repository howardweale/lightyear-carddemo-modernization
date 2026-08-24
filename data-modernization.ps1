param(
  [ValidateSet("build", "verify", "live", "live-postgres", "live-oracle", "live-all", "sign")][string]$Command = "verify",
  [string]$LegacyRoot = $env:CARDDEMO_UPSTREAM_ROOT
)
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
if ([string]::IsNullOrWhiteSpace($LegacyRoot)) { $LegacyRoot = Join-Path (Split-Path $ProjectDir -Parent) "carddemo-upstream" }
function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }

if ($Command -eq "build") {
  Run-Python -m lightyear_data build --legacy-root $LegacyRoot --output-root $ProjectDir
} elseif ($Command -eq "verify") {
  $Output = Join-Path $ProjectDir "work\data-modernization-verify"
  if (Test-Path $Output) { Remove-Item -Recurse -Force $Output }
  Run-Python -m lightyear_data build --legacy-root $LegacyRoot --output-root $Output
  Run-Python -m lightyear_data validate --project-root $Output
  Run-Python -m lightyear_data verify-offline --project-root $Output
  $Expected = Get-ChildItem (Join-Path $ProjectDir "data-modernization") -Recurse -File
  foreach ($File in $Expected) {
    $Relative = $File.FullName.Substring((Join-Path $ProjectDir "data-modernization").Length).TrimStart('\')
    $Actual = Join-Path (Join-Path $Output "data-modernization") $Relative
    if (-not (Test-Path $Actual) -or (Get-FileHash $File.FullName).Hash -ne (Get-FileHash $Actual).Hash) { throw "Generated data artifact differs: $Relative" }
  }
  Write-Host "AUTHFRDS canonical model, PostgreSQL/Oracle mappings, fixtures, and signed development receipts are deterministic."
} elseif ($Command -in @("live", "live-postgres")) {
  Run-Python -m lightyear_data verify-docker --target postgresql --project-root $ProjectDir
} elseif ($Command -eq "live-oracle") {
  Run-Python -m lightyear_data verify-docker --target oracle --project-root $ProjectDir
} elseif ($Command -eq "live-all") {
  Run-Python -m lightyear_data verify-docker --target all --project-root $ProjectDir
} else {
  if ([string]::IsNullOrWhiteSpace($env:FACTORYDARK_DATA_EQUIVALENCE_KEY)) { throw "Set FACTORYDARK_DATA_EQUIVALENCE_KEY" }
  $Receipt = Join-Path $ProjectDir "work\data-modernization\live-multi-target.receipt.json"
  $Output = Join-Path $ProjectDir "work\data-modernization\live-multi-target.signed.receipt.json"
  if (-not (Test-Path $Receipt)) {
    $Receipt = Join-Path $ProjectDir "work\data-modernization\live-postgresql.receipt.json"
    $Output = Join-Path $ProjectDir "work\data-modernization\live-postgresql.signed.receipt.json"
  }
  Run-Python -m lightyear_data sign --receipt $Receipt --output $Output
}
