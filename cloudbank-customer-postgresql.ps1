$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }

if ($Action -eq "build" -or $Action -eq "verify") {
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_customer_postgresql.py") `
        $Action --project-root $ProjectDir
    exit $LASTEXITCODE
}
if ($Action -eq "verify-source") {
    if ($args.Count -ne 2) { throw "verify-source requires SOURCE_ROOT" }
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_customer_postgresql.py") `
        verify-source --source-root $args[1]
    exit $LASTEXITCODE
}
if ($Action -eq "native-postgresql") {
    if ($args.Count -ne 6) { throw "native-postgresql requires SOURCE_ROOT ORACLE_RECEIPT IMAGE_ID_SHA256 OUTPUT SIGNER" }
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_customer_postgresql.py") `
        native-postgresql --source-root $args[1] --oracle-receipt $args[2] `
        --postgresql-image-id-sha256 $args[3] --output $args[4] --signer $args[5]
    exit $LASTEXITCODE
}
if ($Action -eq "verify-receipt") {
    if ($args.Count -ne 2) { throw "verify-receipt requires RECEIPT" }
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_customer_postgresql.py") `
        verify-receipt --receipt $args[1]
    exit $LASTEXITCODE
}
throw "Usage: .\cloudbank-customer-postgresql.ps1 [build|verify|verify-source SOURCE_ROOT|native-postgresql SOURCE_ROOT ORACLE_RECEIPT IMAGE_ID_SHA256 OUTPUT SIGNER|verify-receipt RECEIPT]"
