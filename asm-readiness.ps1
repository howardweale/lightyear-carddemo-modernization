param(
  [ValidateSet("build", "verify", "template", "compare")]
  [string]$Action = "verify",
  [string]$OutputDir = "work/asm-readiness",
  [string]$ZosCapture = ""
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$PyArgs = @()
if ($Python -eq "py") {
  $Selected = $null
  foreach ($Version in @("3.13", "3.12", "3.11", "3.14")) {
    try {
      & py "-$Version" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { $Selected = "-$Version"; break }
    } catch {}
  }
  if (-not $Selected) { throw "FactoryDark requires Python 3.11 or newer." }
  $PyArgs = @($Selected)
}
$OutputDir = [System.IO.Path]::GetFullPath((Join-Path $ProjectDir $OutputDir))
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Run-Python([string[]]$Arguments) {
  & $Python @PyArgs @Arguments
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Action -eq "template") {
  Run-Python @("-m", "lightyear_readiness.asm", "capture-template", "--output", (Join-Path $OutputDir "zos-capture.template.json"))
  exit 0
}

if ($Action -eq "compare") {
  if (-not $ZosCapture) { throw "A z/OS capture path is required for compare." }
  Run-Python @("-m", "lightyear_readiness.asm", "local-capture", "--project-root", $ProjectDir, "--output", (Join-Path $OutputDir "local-capture.json"))
  Run-Python @("-m", "lightyear_readiness.asm", "validate-capture", "--capture", $ZosCapture)
  Run-Python @("-m", "lightyear_readiness.asm", "compare", "--baseline", $ZosCapture, "--candidate", (Join-Path $OutputDir "local-capture.json"), "--output", (Join-Path $OutputDir "comparison.json"))
  Run-Python @("-m", "lightyear_readiness.asm", "issue", "--comparison", (Join-Path $OutputDir "comparison.json"), "--output", (Join-Path $OutputDir "readiness-receipt.json"))
  exit 0
}

Run-Python @("-m", "lightyear_factory.asm_private")
Run-Python @("-m", "lightyear_readiness.asm", "local-capture", "--project-root", $ProjectDir, "--output", (Join-Path $OutputDir "local-capture.json"))
Run-Python @("-m", "lightyear_readiness.asm", "validate-capture", "--capture", (Join-Path $OutputDir "local-capture.json"))
Run-Python @("-m", "lightyear_readiness.asm", "compare", "--baseline", (Join-Path $OutputDir "local-capture.json"), "--candidate", (Join-Path $OutputDir "local-capture.json"), "--output", (Join-Path $OutputDir "comparison.json"))
Run-Python @("-m", "lightyear_readiness.asm", "issue", "--comparison", (Join-Path $OutputDir "comparison.json"), "--output", (Join-Path $OutputDir "readiness-receipt.json"))
Run-Python @("-m", "lightyear_readiness.asm", "validate-receipt", "--receipt", (Join-Path $OutputDir "readiness-receipt.json"))
Run-Python @("-m", "lightyear_readiness.asm", "capture-template", "--output", (Join-Path $OutputDir "zos-capture.template.json"))

if ($Action -eq "verify") {
  foreach ($Name in @("local-capture.json", "comparison.json", "readiness-receipt.json", "zos-capture.template.json")) {
    $Expected = Join-Path $ProjectDir "readiness/asm-date/$Name"
    $Actual = Join-Path $OutputDir $Name
    if ((Get-FileHash $Expected -Algorithm SHA256).Hash -ne (Get-FileHash $Actual -Algorithm SHA256).Hash) {
      throw "$Name differs from the canonical artifact."
    }
  }
}

Write-Host "HLASM development proof passed; live z/OS equivalence remains fail-closed."
