$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
function Run-Python { Invoke-FactoryDarkPython @args }
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }

$Base = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
$Slices = Join-Path $ProjectDir "reference-estates\idempiere\business-slices.json"
$Inventory = Join-Path $ProjectDir "reference-estates\idempiere\inventory.json"
$SourcePin = Join-Path $ProjectDir "reference-estates\idempiere\source-pin.json"
$Fragment = Join-Path $ProjectDir "reference-estates\idempiere\oracle-customer-large.fragment.json"
$Receipt = Join-Path $ProjectDir "reference-estates\idempiere\oracle-customer-large.receipt.json"

function Build-Projection([string]$OutputFragment, [string]$OutputReceipt) {
    Run-Python -m lightyear_knowledge_graph build-oracle-reference `
        --base-graph $Base --slices $Slices --inventory $Inventory --source-pin $SourcePin `
        --output $OutputFragment --receipt $OutputReceipt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Action -eq "build") {
    Build-Projection $Fragment $Receipt
    exit 0
}

if ($Action -eq "verify") {
    $Generated = Join-Path $ProjectDir "work\oracle-reference-estate-verify"
    New-Item -ItemType Directory -Force -Path $Generated | Out-Null
    $GeneratedFragment = Join-Path $Generated "oracle-customer-large.fragment.json"
    $GeneratedReceipt = Join-Path $Generated "oracle-customer-large.receipt.json"
    Build-Projection $GeneratedFragment $GeneratedReceipt
    if ((Get-FileHash $Fragment -Algorithm SHA256).Hash -ne (Get-FileHash $GeneratedFragment -Algorithm SHA256).Hash) {
        throw "Oracle reference fragment is stale"
    }
    if ((Get-FileHash $Receipt -Algorithm SHA256).Hash -ne (Get-FileHash $GeneratedReceipt -Algorithm SHA256).Hash) {
        throw "Oracle reference receipt is stale"
    }
    Run-Python -m lightyear_knowledge_graph validate-oracle-reference `
        --base-graph $Base --slices $Slices --inventory $Inventory --source-pin $SourcePin `
        --fragment $Fragment
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output "Oracle Customer (Large) reference projection is deterministic and current."
    exit 0
}

Write-Error "Usage: .\oracle-reference-estate.ps1 [build|verify]"
exit 2
