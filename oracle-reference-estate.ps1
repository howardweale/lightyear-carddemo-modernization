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

function Build-Projection([string]$OutputFragment, [string]$OutputReceipt, [string]$InputInventory = $Inventory) {
    Run-Python -m lightyear_knowledge_graph build-oracle-reference `
        --base-graph $Base --slices $Slices --inventory $InputInventory --source-pin $SourcePin `
        --output $OutputFragment --receipt $OutputReceipt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Action -eq "build-full") {
    if ($args.Count -lt 2) {
        Write-Error "Pinned iDempiere upstream checkout is required for build-full."
        exit 2
    }
    $Generated = Join-Path $ProjectDir "work\reference-estates\idempiere"
    New-Item -ItemType Directory -Force -Path $Generated | Out-Null
    $GeneratedInventory = Join-Path $Generated "inventory.json"
    $GeneratedFragment = Join-Path $Generated "oracle-reference.fragment.json.gz"
    $GeneratedReceipt = Join-Path $Generated "oracle-reference.receipt.json"
    Run-Python (Join-Path $ProjectDir "tools\inventory_idempiere_reference.py") `
        --source-root $args[1] --output $GeneratedInventory
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Build-Projection $GeneratedFragment $GeneratedReceipt $GeneratedInventory
    Run-Python -m lightyear_knowledge_graph validate-oracle-reference `
        --base-graph $Base --slices $Slices --inventory $GeneratedInventory --source-pin $SourcePin `
        --fragment $GeneratedFragment
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output "Full iDempiere reference projection built in work/reference-estates/idempiere."
    exit 0
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
    Write-Output "The bounded iDempiere reference projection is deterministic and current."
    exit 0
}

Write-Error "Usage: .\oracle-reference-estate.ps1 [build|verify|build-full IDEMPIERE_ROOT]"
exit 2
