$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$OutputDir = Join-Path $ProjectDir "work/factory-benchmark-$Stamp"

$env:PYTHONPATH = Join-Path $ProjectDir "src"
Set-Location $ProjectDir
& py -3.11 -m lightyear_factory benchmark `
  --project-root $ProjectDir `
  --output-root $OutputDir `
  @args
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "Factory benchmark artifacts: $OutputDir"
