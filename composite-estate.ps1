$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }
$LegacyRoot = if ($args.Count -gt 1) { $args[1] } elseif ($env:CARDDEMO_UPSTREAM_ROOT) { $env:CARDDEMO_UPSTREAM_ROOT } else { "" }
if (-not $LegacyRoot -and (Test-Path (Join-Path $ProjectDir "..\carddemo-upstream\app"))) {
    $LegacyRoot = (Resolve-Path (Join-Path $ProjectDir "..\carddemo-upstream")).Path
}
if (-not $LegacyRoot -and (Test-Path (Join-Path $ProjectDir "work\carddemo-upstream\app"))) {
    $LegacyRoot = (Resolve-Path (Join-Path $ProjectDir "work\carddemo-upstream")).Path
}
if (-not $LegacyRoot) {
    Write-Error "CardDemo upstream is required. Set CARDDEMO_UPSTREAM_ROOT or pass its path."
    exit 2
}

$env:PYTHONPATH = Join-Path $ProjectDir "src"
. (Join-Path $ProjectDir "python-runtime.ps1")
function Run-Python { Invoke-FactoryDarkPython @args }

$Base = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
$Fragment = Join-Path $ProjectDir "extensions\pli\pli.fragment.json"
$OracleFragment = if ($env:LIGHTYEAR_ORACLE_REFERENCE_FRAGMENT) { $env:LIGHTYEAR_ORACLE_REFERENCE_FRAGMENT } else { Join-Path $ProjectDir "reference-estates\idempiere\oracle-customer-large.fragment.json" }
$CloudBankFragment = if ($env:LIGHTYEAR_CLOUDBANK_REFERENCE_FRAGMENT) { $env:LIGHTYEAR_CLOUDBANK_REFERENCE_FRAGMENT } else { Join-Path $ProjectDir "reference-estates\cloudbank\cloudbank-reference.fragment.json" }
$Capabilities = Join-Path $ProjectDir "knowledge\capabilities\mainframe-readiness.json"
$CanonicalDir = Join-Path $ProjectDir "knowledge\composite"

function Build-Projection([string]$OutputDir) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    Run-Python -m lightyear_knowledge_graph build-composite `
        --base-graph $Base --fragment $Fragment --fragment $OracleFragment --fragment $CloudBankFragment --capabilities $Capabilities `
        --legacy-root $LegacyRoot --modern-root $ProjectDir `
        --output (Join-Path $OutputDir "estate.snapshot.json.gz") `
        --receipt (Join-Path $OutputDir "estate.receipt.json") `
        --evidence-pack (Join-Path $OutputDir "source.pack.json.gz") `
        --evidence-receipt (Join-Path $OutputDir "source.receipt.json")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Action -eq "build-working") {
    $WorkingDir = Join-Path $ProjectDir "work\composite-estate"
    Build-Projection $WorkingDir
    Run-Python -m lightyear_knowledge_graph validate-composite `
        --graph (Join-Path $WorkingDir "estate.snapshot.json.gz") `
        --base-graph $Base --fragment $Fragment --fragment $OracleFragment --fragment $CloudBankFragment --capabilities $Capabilities `
        --evidence-pack (Join-Path $WorkingDir "source.pack.json.gz")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output "Working composite built in work/composite-estate."
    exit 0
}
if ($Action -eq "build") {
    Build-Projection $CanonicalDir
    Run-Python -m lightyear_knowledge_graph validate-composite `
        --graph (Join-Path $CanonicalDir "estate.snapshot.json.gz") `
        --base-graph $Base --fragment $Fragment --fragment $OracleFragment --fragment $CloudBankFragment --capabilities $Capabilities `
        --evidence-pack (Join-Path $CanonicalDir "source.pack.json.gz")
    exit $LASTEXITCODE
}
if ($Action -eq "verify") {
    $Generated = Join-Path $ProjectDir "work\composite-estate-verify"
    Build-Projection $Generated
    Run-Python -m lightyear_knowledge_graph validate-composite `
        --graph (Join-Path $Generated "estate.snapshot.json.gz") `
        --base-graph $Base --fragment $Fragment --fragment $OracleFragment --fragment $CloudBankFragment --capabilities $Capabilities `
        --evidence-pack (Join-Path $Generated "source.pack.json.gz")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph compare-snapshots `
        --expected (Join-Path $CanonicalDir "estate.snapshot.json.gz") `
        --actual (Join-Path $Generated "estate.snapshot.json.gz")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Run-Python -m lightyear_knowledge_graph compare-evidence-packs `
        --expected (Join-Path $CanonicalDir "source.pack.json.gz") `
        --actual (Join-Path $Generated "source.pack.json.gz")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    foreach ($Name in @("estate.receipt.json", "source.receipt.json")) {
        if ((Get-FileHash (Join-Path $CanonicalDir $Name)).Hash -ne (Get-FileHash (Join-Path $Generated $Name)).Hash) {
            throw "Composite estate artifact is stale: $Name"
        }
    }
    Write-Host "Composite estate is deterministic, current, read-only, and evidence-bound."
    exit 0
}
Write-Error "Usage: .\composite-estate.ps1 [build|build-working|verify] [optional-carddemo-upstream-root]"
exit 2
