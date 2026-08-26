param([ValidateSet("build", "verify")][string]$Command = "verify")
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = "$(Join-Path $ProjectDir 'extensions\runtime')$([IO.Path]::PathSeparator)$(Join-Path $ProjectDir 'src')"
. (Join-Path $ProjectDir "python-runtime.ps1")

function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
function Build-Proof([string]$Output) {
  if (Test-Path $Output) { Remove-Item -Recurse -Force $Output }
  Run-Python -m lightyear_extensions build-pli-proof --project-root $ProjectDir `
    --graph (Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz") `
    --fragment (Join-Path $ProjectDir "extensions\pli\pli.fragment.json") --output-root $Output
}

$Canonical = Join-Path $ProjectDir "extensions\pli\modernization"
$Generated = Join-Path $ProjectDir "work\pli-modernization-$Command"
Build-Proof $Generated
if ($Command -eq "build") {
  New-Item -ItemType Directory -Force $Canonical | Out-Null
  Copy-Item (Join-Path $Generated "*.json") $Canonical -Force
} else {
  Run-Python -m unittest extensions.tests.test_pli_modernization -v
  Get-ChildItem $Canonical -Filter *.json | ForEach-Object {
    $Actual = Join-Path $Generated $_.Name
    if ((Get-FileHash $_.FullName).Hash -ne (Get-FileHash $Actual).Hash) { throw "Generated PL/I artifact differs: $($_.Name)" }
  }
}
Run-Python -m lightyear_extensions validate-pli-proof --project-root $ProjectDir `
  --graph (Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz") `
  --fragment (Join-Path $ProjectDir "extensions\pli\pli.fragment.json") `
  --receipt (Join-Path $Canonical "development.receipt.json")
Write-Host "Mixed PL/I, COBOL-call, and Db2 development proof is deterministic; live z/OS equivalence remains blocked."
