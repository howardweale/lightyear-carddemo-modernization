$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ProjectDir "python-runtime.ps1")
function Run-Python { Invoke-FactoryDarkPython @args }
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }

$Base = Join-Path $ProjectDir "knowledge\graph.snapshot.json.gz"
$Workloads = Join-Path $ProjectDir "reference-estates\cloudbank\workloads.json"
$Inventory = Join-Path $ProjectDir "reference-estates\cloudbank\inventory.json"
$SourcePin = Join-Path $ProjectDir "reference-estates\cloudbank\source-pin.json"
$Fragment = Join-Path $ProjectDir "reference-estates\cloudbank\cloudbank-reference.fragment.json"
$Receipt = Join-Path $ProjectDir "reference-estates\cloudbank\cloudbank-reference.receipt.json"

function Build-Projection([string]$OutputFragment, [string]$OutputReceipt) {
    Run-Python -m lightyear_knowledge_graph build-cloudbank-reference `
        --base-graph $Base --workloads $Workloads --inventory $Inventory --source-pin $SourcePin `
        --output $OutputFragment --receipt $OutputReceipt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($Action -eq "inventory" -or $Action -eq "verify-inventory") {
    if ($args.Count -lt 2) {
        Write-Error "CloudBank upstream checkout is required for $Action."
        exit 2
    }
    $InventoryArgs = @(
        (Join-Path $ProjectDir "tools\inventory_cloudbank_reference.py"),
        "--source-root", $args[1], "--output", $Inventory
    )
    if ($Action -eq "verify-inventory") { $InventoryArgs += "--verify" }
    Run-Python @InventoryArgs
    exit $LASTEXITCODE
}
if ($Action -eq "build") {
    Build-Projection $Fragment $Receipt
    exit 0
}
if ($Action -eq "verify") {
    $Generated = Join-Path $ProjectDir "work\cloudbank-reference-estate-verify"
    New-Item -ItemType Directory -Force -Path $Generated | Out-Null
    $GeneratedFragment = Join-Path $Generated "cloudbank-reference.fragment.json"
    $GeneratedReceipt = Join-Path $Generated "cloudbank-reference.receipt.json"
    Build-Projection $GeneratedFragment $GeneratedReceipt
    if ((Get-FileHash $Fragment -Algorithm SHA256).Hash -ne (Get-FileHash $GeneratedFragment -Algorithm SHA256).Hash) {
        throw "CloudBank reference fragment is stale"
    }
    if ((Get-FileHash $Receipt -Algorithm SHA256).Hash -ne (Get-FileHash $GeneratedReceipt -Algorithm SHA256).Hash) {
        throw "CloudBank reference receipt is stale"
    }
    Run-Python -m lightyear_knowledge_graph validate-cloudbank-reference `
        --base-graph $Base --workloads $Workloads --inventory $Inventory --source-pin $SourcePin `
        --fragment $Fragment
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output "CloudBank modern Oracle reference projection is deterministic and current."
    exit 0
}

Write-Error "Usage: .\cloudbank-reference-estate.ps1 [inventory SOURCE_ROOT|verify-inventory SOURCE_ROOT|build|verify]"
exit 2
