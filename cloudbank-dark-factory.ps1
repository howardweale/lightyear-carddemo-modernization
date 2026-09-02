$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
. (Join-Path $ProjectDir "python-runtime.ps1")
$env:PYTHONPATH = Join-Path $ProjectDir "src"
$Action = if ($args.Count -gt 0) { $args[0] } else { "verify" }

if ($Action -eq "build" -or $Action -eq "verify") {
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_dark_factory.py") `
        $Action --project-root $ProjectDir
    exit $LASTEXITCODE
}
if ($Action -eq "verify-source") {
    if ($args.Count -ne 2) { throw "verify-source requires SOURCE_ROOT" }
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_dark_factory.py") `
        verify-source --source-root $args[1]
    exit $LASTEXITCODE
}
if ($Action -eq "run") {
    if ($args.Count -ne 6) { throw "run requires SOURCE_ROOT ORACLE_RECEIPT POSTGRESQL_RECEIPT OUTPUT_ROOT SIGNER" }
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_dark_factory.py") run `
        --project-root $ProjectDir --source-root $args[1] --oracle-receipt $args[2] `
        --postgresql-receipt $args[3] --output-root $args[4] --signer $args[5]
    exit $LASTEXITCODE
}
if ($Action -eq "verify-receipt") {
    if ($args.Count -ne 2) { throw "verify-receipt requires RECEIPT" }
    Invoke-FactoryDarkPython (Join-Path $ProjectDir "tools\cloudbank_dark_factory.py") verify-receipt `
        --project-root $ProjectDir --receipt $args[1]
    exit $LASTEXITCODE
}
throw "Usage: .\cloudbank-dark-factory.ps1 [build|verify|verify-source SOURCE_ROOT|run SOURCE_ROOT ORACLE_RECEIPT POSTGRESQL_RECEIPT OUTPUT_ROOT SIGNER|verify-receipt RECEIPT]"
