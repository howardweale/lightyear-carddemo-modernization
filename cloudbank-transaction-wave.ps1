$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }
$Tool = Join-Path $ProjectDir "tools\cloudbank_transaction_wave.py"

if ($Action -eq "build" -or $Action -eq "verify") {
    Invoke-FactoryDarkPython $Tool $Action --project-root $ProjectDir
    exit $LASTEXITCODE
}
if ($Action -eq "verify-source") {
    if ($args.Count -ne 2) { throw "verify-source requires SOURCE_ROOT" }
    Invoke-FactoryDarkPython $Tool verify-source --source-root $args[1]
    exit $LASTEXITCODE
}
if ($Action -eq "admit") {
    if ($args.Count -ne 5) { throw "admit requires SOURCE_ROOT MS57_RECEIPT OUTPUT SIGNER" }
    Invoke-FactoryDarkPython $Tool admit --project-root $ProjectDir --source-root $args[1] `
        --ms57-receipt $args[2] --output $args[3] --signer $args[4]
    exit $LASTEXITCODE
}
if ($Action -eq "verify-receipt") {
    if ($args.Count -ne 2) { throw "verify-receipt requires RECEIPT" }
    Invoke-FactoryDarkPython $Tool verify-receipt --project-root $ProjectDir --receipt $args[1]
    exit $LASTEXITCODE
}
throw "Usage: .\cloudbank-transaction-wave.ps1 [build|verify|verify-source SOURCE_ROOT|admit SOURCE_ROOT MS57_RECEIPT OUTPUT SIGNER|verify-receipt RECEIPT]"
