$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$LegacyCommit = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }
$LegacyRoot = if ($args.Count -gt 1) { $args[1] } elseif ($env:CARDDEMO_UPSTREAM_ROOT) { $env:CARDDEMO_UPSTREAM_ROOT } else { "" }

if (-not $LegacyRoot -and (Test-Path (Join-Path $ProjectDir "..\carddemo-upstream\app"))) {
    $LegacyRoot = (Resolve-Path (Join-Path $ProjectDir "..\carddemo-upstream")).Path
}
if (-not $LegacyRoot) {
    $LegacyRoot = Join-Path $ProjectDir "work\carddemo-upstream"
    if (-not (Test-Path (Join-Path $LegacyRoot ".git"))) {
        & git clone --filter=blob:none --no-checkout `
            https://github.com/aws-samples/aws-mainframe-modernization-carddemo.git `
            $LegacyRoot
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & git -C $LegacyRoot checkout --detach $LegacyCommit
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Manifest = Join-Path $ProjectDir "knowledge\mappings\carddemo-intcalc.json"
$Snapshot = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
$Receipt = Join-Path $ProjectDir "knowledge\graph.receipt.json"

if ($Action -eq "build") {
    & py -3.11 -m lightyear_knowledge_graph build `
        --legacy-root $LegacyRoot --modern-root $ProjectDir --manifest $Manifest `
        --output $Snapshot --receipt $Receipt --legacy-commit $LegacyCommit `
        --modern-commit repository-content
    exit $LASTEXITCODE
}
if ($Action -eq "verify") {
    $Generated = Join-Path $ProjectDir "work\knowledge-graph-verify"
    New-Item -ItemType Directory -Force -Path $Generated | Out-Null
    $GeneratedSnapshot = Join-Path $Generated "graph.snapshot.json.gz"
    $GeneratedReceipt = Join-Path $Generated "graph.receipt.json"
    & py -3.11 -m lightyear_knowledge_graph build `
        --legacy-root $LegacyRoot --modern-root $ProjectDir --manifest $Manifest `
        --output $GeneratedSnapshot --receipt $GeneratedReceipt --legacy-commit $LegacyCommit `
        --modern-commit repository-content
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & py -3.11 -m lightyear_knowledge_graph validate --graph $GeneratedSnapshot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & py -3.11 -m lightyear_knowledge_graph gaps --graph $GeneratedSnapshot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & py -3.11 -m lightyear_knowledge_graph compare-snapshots `
        --expected $Snapshot --actual $GeneratedSnapshot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ((Get-FileHash $Receipt).Hash -ne (Get-FileHash $GeneratedReceipt).Hash) {
        throw "Knowledge graph receipt is stale; run .\knowledge-graph.ps1 build"
    }
    Write-Host "Knowledge graph snapshot is deterministic, current, and policy-complete."
    exit 0
}
Write-Error "Usage: .\knowledge-graph.ps1 [build|verify] [optional-carddemo-upstream-root]"
exit 2
