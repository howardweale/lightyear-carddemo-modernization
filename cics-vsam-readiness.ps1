$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$env:LIGHTYEAR_CICS_VSAM_WORKSPACE = $ProjectDir
. (Join-Path $ProjectDir "python-runtime.ps1")
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }
$OutputDir = if ($args.Count -gt 1) { $args[1] } else { Join-Path $ProjectDir "work\cics-vsam-readiness" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }

if ($Action -eq "template") {
  Run-Python -m lightyear_readiness capture-template --output (Join-Path $OutputDir "zos-capture.template.json")
} elseif ($Action -eq "verify" -or $Action -eq "build") {
  Run-Python -m lightyear_factory.cics_vsam_private
  Run-Python -m lightyear_readiness local-capture --project-root $ProjectDir --output (Join-Path $OutputDir "local-capture.json")
  Run-Python -m lightyear_readiness validate-capture --capture (Join-Path $OutputDir "local-capture.json")
  Run-Python -m lightyear_readiness compare --baseline (Join-Path $OutputDir "local-capture.json") --candidate (Join-Path $OutputDir "local-capture.json") --output (Join-Path $OutputDir "comparison.json")
  Run-Python -m lightyear_readiness issue --comparison (Join-Path $OutputDir "comparison.json") --output (Join-Path $OutputDir "readiness-receipt.json")
  Run-Python -m lightyear_readiness validate-receipt --receipt (Join-Path $OutputDir "readiness-receipt.json")
  Run-Python -m lightyear_readiness capture-template --output (Join-Path $OutputDir "zos-capture.template.json")
  Run-Python -m lightyear_readiness.cics_vsam_qualification build --project-root $ProjectDir --output-root $OutputDir
  if ($Action -eq "verify") {
    foreach ($Name in @("local-capture.json", "comparison.json", "readiness-receipt.json", "zos-capture.template.json", "conformance.receipt.json", "compatibility-ledger.json", "qualification.json")) {
      if ((Get-FileHash (Join-Path $ProjectDir "readiness\cics-vsam\$Name")).Hash -ne (Get-FileHash (Join-Path $OutputDir $Name)).Hash) { throw "$Name is stale" }
    }
    Run-Python -m lightyear_readiness.cics_vsam_qualification verify --project-root $ProjectDir
  }
} elseif ($Action -eq "compare") {
  if ($args.Count -lt 3) { throw "Usage: .\cics-vsam-readiness.ps1 compare OUTPUT_DIR ZOS_CAPTURE" }
  $Baseline = $args[2]
  Run-Python -m lightyear_readiness local-capture --project-root $ProjectDir --output (Join-Path $OutputDir "local-capture.json")
  Run-Python -m lightyear_readiness validate-capture --capture $Baseline
  Run-Python -m lightyear_readiness compare --baseline $Baseline --candidate (Join-Path $OutputDir "local-capture.json") --output (Join-Path $OutputDir "comparison.json")
  Run-Python -m lightyear_readiness issue --comparison (Join-Path $OutputDir "comparison.json") --output (Join-Path $OutputDir "readiness-receipt.json")
} else {
  throw "Usage: .\cics-vsam-readiness.ps1 [build|verify|template|compare] [output-dir] [zos-capture]"
}
