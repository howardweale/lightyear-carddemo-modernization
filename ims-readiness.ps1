param(
  [ValidateSet("build", "verify", "template", "compare")]
  [string]$Action = "verify",
  [string]$OutputDir = "work/ims-readiness",
  [string]$ZosCapture = ""
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

if ($Action -eq "template") {
  Run-Python @("-m", "lightyear_readiness.ims", "capture-template", "--output", (Join-Path $OutputDir "zos-capture.template.json"))
  exit 0
}

if ($Action -eq "compare") {
  if (-not $ZosCapture) { throw "A z/OS IMS capture path is required for compare." }
  Run-Python @("-m", "lightyear_readiness.ims", "local-capture", "--project-root", $ProjectDir, "--output", (Join-Path $OutputDir "local-capture.json"))
  Run-Python @("-m", "lightyear_readiness.ims", "validate-capture", "--capture", $ZosCapture)
  Run-Python @("-m", "lightyear_readiness.ims", "compare", "--baseline", $ZosCapture, "--candidate", (Join-Path $OutputDir "local-capture.json"), "--output", (Join-Path $OutputDir "comparison.json"))
  Run-Python @("-m", "lightyear_readiness.ims", "issue", "--comparison", (Join-Path $OutputDir "comparison.json"), "--output", (Join-Path $OutputDir "readiness-receipt.json"))
  exit 0
}

Run-Python @("-m", "lightyear_factory.ims_private")
Run-Python @("-m", "lightyear_readiness.ims", "local-capture", "--project-root", $ProjectDir, "--output", (Join-Path $OutputDir "local-capture.json"))
Run-Python @("-m", "lightyear_readiness.ims", "validate-capture", "--capture", (Join-Path $OutputDir "local-capture.json"))
Run-Python @("-m", "lightyear_readiness.ims", "compare", "--baseline", (Join-Path $OutputDir "local-capture.json"), "--candidate", (Join-Path $OutputDir "local-capture.json"), "--output", (Join-Path $OutputDir "comparison.json"))
Run-Python @("-m", "lightyear_readiness.ims", "issue", "--comparison", (Join-Path $OutputDir "comparison.json"), "--output", (Join-Path $OutputDir "readiness-receipt.json"))
Run-Python @("-m", "lightyear_readiness.ims", "validate-receipt", "--receipt", (Join-Path $OutputDir "readiness-receipt.json"))
Run-Python @("-m", "lightyear_readiness.ims", "capture-template", "--output", (Join-Path $OutputDir "zos-capture.template.json"))
Run-Python @("-m", "lightyear_readiness.ims_qualification", "build", "--project-root", $ProjectDir, "--output-root", $OutputDir)

if ($Action -eq "verify") {
  foreach ($Name in @("local-capture.json", "comparison.json", "readiness-receipt.json", "zos-capture.template.json", "conformance.receipt.json", "compatibility-ledger.json", "qualification.json")) {
    $Expected = Join-Path $ProjectDir "readiness/ims-expiry/$Name"
    $Actual = Join-Path $OutputDir $Name
    if ((Get-FileHash $Expected -Algorithm SHA256).Hash -ne (Get-FileHash $Actual -Algorithm SHA256).Hash) {
      throw "$Name differs from the canonical artifact."
    }
  }
  Run-Python @("-m", "lightyear_readiness.ims_qualification", "verify", "--project-root", $ProjectDir)
}

Write-Host "IMS bounded qualification passed; native execution and recovery equivalence remain fail-closed."
