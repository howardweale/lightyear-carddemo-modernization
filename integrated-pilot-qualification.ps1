param(
  [ValidateSet("build", "verify")]
  [string]$Action = "verify",
  [string]$OutputDir = "work/integrated-pilot-qualification"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
$OutputDir = [System.IO.Path]::GetFullPath((Join-Path $ProjectDir $OutputDir))
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Run-Python([string[]]$Arguments) {
  Invoke-FactoryDarkPython @Arguments
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Run-Python @("-m", "lightyear_pilot.integrated_qualification", "build", "--project-root", $ProjectDir, "--output-root", $OutputDir)

if ($Action -eq "verify") {
  foreach ($Name in @("conformance.receipt.json", "evidence-matrix.json", "compatibility-ledger.json", "qualification.json")) {
    $Expected = Join-Path $ProjectDir "pilot/integrated-qualification/$Name"
    $Actual = Join-Path $OutputDir $Name
    if ((Get-FileHash $Expected -Algorithm SHA256).Hash -ne (Get-FileHash $Actual -Algorithm SHA256).Hash) {
      throw "$Name differs from the canonical artifact."
    }
  }
  Run-Python @("-m", "lightyear_pilot.integrated_qualification", "verify", "--project-root", $ProjectDir)
}

Write-Host "Integrated pilot Wave 2 development qualification passed; dispatch, native execution, and production release remain blocked."
