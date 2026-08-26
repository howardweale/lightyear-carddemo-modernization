param([ValidateSet("build", "verify")][string]$Command = "verify")
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$env:PYTHONPATH = "$(Join-Path $ProjectDir 'extensions\runtime')$([IO.Path]::PathSeparator)$(Join-Path $ProjectDir 'src')"
. (Join-Path $ProjectDir "python-runtime.ps1")

$Graph = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
$Spec = Join-Path $ProjectDir "extensions\adapters\fixtures\zosmf-intcalc.simulated.spec.json"

function Run-Python { Invoke-FactoryDarkPython @args; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
function Build-Outputs([string]$Root) {
  New-Item -ItemType Directory -Force (Join-Path $Root "adapters"), (Join-Path $Root "pli") | Out-Null
  Run-Python -m lightyear_extensions catalog --output (Join-Path $Root "catalog.json")
  Run-Python -m lightyear_extensions build-fixture-capture --spec $Spec --graph $Graph --output (Join-Path $Root "adapters\capture.json")
  Run-Python -m lightyear_extensions replay --capture (Join-Path $Root "adapters\capture.json") --graph $Graph --output (Join-Path $Root "adapters\replay.json")
  Run-Python -m lightyear_extensions build-pli --graph $Graph --source-root (Join-Path $ProjectDir "extensions\pli\reference") --repository-root $ProjectDir --output (Join-Path $Root "pli\fragment.json") --receipt (Join-Path $Root "pli\receipt.json")
}

if ($Command -eq "build") {
  $Output = Join-Path $ProjectDir "work\extension-foundation-build"
  Build-Outputs $Output
  Copy-Item (Join-Path $Output "catalog.json") (Join-Path $ProjectDir "extensions\catalog.json") -Force
  Copy-Item (Join-Path $Output "adapters\capture.json") (Join-Path $ProjectDir "extensions\adapters\fixtures\zosmf-intcalc.simulated.capture.json") -Force
  Copy-Item (Join-Path $Output "adapters\replay.json") (Join-Path $ProjectDir "extensions\adapters\fixtures\zosmf-intcalc.simulated.replay.json") -Force
  Copy-Item (Join-Path $Output "pli\fragment.json") (Join-Path $ProjectDir "extensions\pli\pli.fragment.json") -Force
  Copy-Item (Join-Path $Output "pli\receipt.json") (Join-Path $ProjectDir "extensions\pli\pli.fragment.receipt.json") -Force
} else {
  $Output = Join-Path $ProjectDir "work\extension-foundation-verify"
  if (Test-Path $Output) { Remove-Item -Recurse -Force $Output }
  Build-Outputs $Output
  Run-Python -m unittest discover -s (Join-Path $ProjectDir "extensions\tests") -p "test_*.py" -v
  Run-Python -m lightyear_extensions validate-capture --capture (Join-Path $Output "adapters\capture.json") --graph $Graph
  Run-Python -m lightyear_extensions validate-capture --capture (Join-Path $Output "adapters\replay.json") --graph $Graph
  Run-Python -m lightyear_extensions validate-pli --fragment (Join-Path $Output "pli\fragment.json") --graph $Graph
  $Pairs = @(
    @((Join-Path $ProjectDir "extensions\catalog.json"), (Join-Path $Output "catalog.json")),
    @((Join-Path $ProjectDir "extensions\adapters\fixtures\zosmf-intcalc.simulated.capture.json"), (Join-Path $Output "adapters\capture.json")),
    @((Join-Path $ProjectDir "extensions\adapters\fixtures\zosmf-intcalc.simulated.replay.json"), (Join-Path $Output "adapters\replay.json")),
    @((Join-Path $ProjectDir "extensions\pli\pli.fragment.json"), (Join-Path $Output "pli\fragment.json")),
    @((Join-Path $ProjectDir "extensions\pli\pli.fragment.receipt.json"), (Join-Path $Output "pli\receipt.json"))
  )
  foreach ($Pair in $Pairs) {
    if ((Get-FileHash $Pair[0]).Hash -ne (Get-FileHash $Pair[1]).Hash) { throw "Generated extension artifact differs: $($Pair[0])" }
  }
  Write-Host "Trusted adapter evidence, record/replay, and PL/I graph extension are deterministic."
}
