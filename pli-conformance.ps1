param([ValidateSet("build", "verify")][string]$Command = "verify")
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = "$(Join-Path $ProjectDir 'extensions\runtime')$([IO.Path]::PathSeparator)$(Join-Path $ProjectDir 'src')"
. (Join-Path $ProjectDir "python-runtime.ps1")

function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
function Build-Coverage([string]$Output) {
  if (Test-Path $Output) { Remove-Item -Recurse -Force $Output }
  New-Item -ItemType Directory -Force $Output | Out-Null
  Run-Python -m lightyear_extensions build-pli-conformance `
    --graph (Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz") `
    --corpus-root (Join-Path $ProjectDir "extensions\pli\conformance\corpus") `
    --manifest (Join-Path $ProjectDir "extensions\pli\conformance\corpus\manifest.json") `
    --support-matrix (Join-Path $ProjectDir "extensions\pli\conformance\support-matrix.json") `
    --repository-root $ProjectDir `
    --golden-output (Join-Path $Output "golden-results.json") `
    --receipt (Join-Path $Output "coverage.receipt.json")
}

$Canonical = Join-Path $ProjectDir "extensions\pli\conformance"
$Generated = Join-Path $ProjectDir "work\pli-conformance-$Command"
Build-Coverage $Generated
if ($Command -eq "build") {
  Copy-Item (Join-Path $Generated "golden-results.json") $Canonical -Force
  Copy-Item (Join-Path $Generated "coverage.receipt.json") $Canonical -Force
} else {
  Run-Python -m unittest extensions.tests.test_pli_conformance -v
  foreach ($Name in @("golden-results.json", "coverage.receipt.json")) {
    if ((Get-FileHash (Join-Path $Canonical $Name)).Hash -ne (Get-FileHash (Join-Path $Generated $Name)).Hash) {
      throw "Generated PL/I conformance artifact differs: $Name"
    }
  }
}
Run-Python -m lightyear_extensions validate-pli-conformance `
  --graph (Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz") `
  --golden (Join-Path $Canonical "golden-results.json") `
  --receipt (Join-Path $Canonical "coverage.receipt.json")
Write-Host "PL/I supported-subset coverage is deterministic and explicit; compiler and runtime equivalence remain blocked."
